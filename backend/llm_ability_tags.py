"""
用 Claude Batch API 為每個 course_code 標注「需要哪 5 種能力 (各 0-100)」。

設計:
- 以 course_code 為單位 (跨學期 / 教師合併,取最新 serial_no 當代表),約 5249 個
- 用 Batches API + Prompt caching,系統提示走 1h ephemeral cache
- 輸出 backend/data/course_ability.csv (course_code, logic, writing, coding, humanities, teamwork)
- Resumable: 既有 CSV 內的 course_code 會跳過

之後跑 backend/scripts/ingest_ability_tags.py 把 CSV 載入 SQLite。

需要環境變數 ANTHROPIC_API_KEY。
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request
from pydantic import BaseModel, Field, ValidationError

DATA_DIR = Path(__file__).resolve().parent / "data"
DB_PATH = DATA_DIR / "app.db"
OUTPUT_CSV = DATA_DIR / "course_ability.csv"
BATCH_STATE_FILE = DATA_DIR / ".ability_batch_state.json"

DEFAULT_MODEL = "claude-haiku-4-5-20251001"  # ability tagging 用 Haiku 夠用、便宜 5x
MAX_TOKENS = 256
CONTENT_CHAR_CAP = 2500

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ability")


# ----------------------------- Schema -----------------------------


class AbilityTag(BaseModel):
    logic: int = Field(ge=0, le=100, description="這門課需要的數理邏輯能力 (0-100)")
    writing: int = Field(ge=0, le=100, description="這門課需要的文字表達能力 (0-100)")
    coding: int = Field(ge=0, le=100, description="這門課需要的程式實作能力 (0-100)")
    humanities: int = Field(ge=0, le=100, description="這門課需要的人文素養 (0-100)")
    teamwork: int = Field(ge=0, le=100, description="這門課需要的團隊協作 (0-100)")


SYSTEM_PROMPT = """你是台大課程能力分析助手。輸入是一門課的課名、開課系所、課程目標、課程概述、評量方式。請為這門課的 5 個能力軸打分 (0-100),代表「修這門課最需要這項能力的程度」。

5 個能力軸定義:
- logic:      數理邏輯 — 數學、機率、統計、證明、演算分析、形式推理
- writing:    文字表達 — 寫作、論文、長篇報告、文本分析
- coding:     程式實作 — 寫程式、debug、系統設計、軟體工程
- humanities: 人文素養 — 哲學、歷史、文化、藝術、宗教、社會學
- teamwork:   團隊協作 — 分組專題、小組報告、工作坊、共同創作

評分準則:
- 0  = 完全不需要這項能力
- 30 = 偶爾用到 / 不是主要能力
- 60 = 是這門課的重要能力之一
- 90 = 是這門課的核心 / 必要能力
- 100 = 整堂課圍繞這項能力

注意:
- 不是「該系所通常需要什麼」,而是「這門課實際需要什麼」。例如「機器學習」課對資工系跟商管系學生都一樣需要 coding + logic。
- 評量方式很重要: 有期末 paper → writing 拉高;有程式作業 → coding 拉高;有 group project → teamwork 拉高。
- 多選必修 / 通識課給分相對溫和,但能力需求依內容判斷。
- 通常一門課會有 1-3 項顯著 (>50),其他項可以給較低分數,不要全部給 50。

輸出規則:
- 只輸出一個 JSON 物件,五個 key: logic, writing, coding, humanities, teamwork
- 每個 value 都是 0-100 的整數
- 不要 markdown code fence,不要任何前後說明文字"""


def build_user_message(name: str, dept: str, obj: str, ov: str, grading: str) -> str:
    def cap(s: str, n: int = CONTENT_CHAR_CAP // 3) -> str:
        s = (s or "").strip()
        return s[:n] + (" [截斷]" if len(s) > n else "")

    return (
        f"課名: {name}\n"
        f"開課系所: {dept}\n"
        f"課程目標: {cap(obj)}\n"
        f"課程概述: {cap(ov)}\n"
        f"評量方式: {cap(grading, 600)}"
    )


# ----------------------------- IO helpers -----------------------------


OUTPUT_COLUMNS = [
    "course_code",
    "course_name",
    "logic",
    "writing",
    "coding",
    "humanities",
    "teamwork",
    "error",
]


def load_courses(db_path: Path) -> list[dict[str, str]]:
    """從 app.db 讀每個 course_code 的代表性 row (最新 serial_no)。"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT c.course_code, c.course_name, c.department, c.objectives,
               c.overview, c.grading
        FROM courses c
        JOIN (
            SELECT course_code, MAX(serial_no) AS max_sn
            FROM courses
            GROUP BY course_code
        ) m ON m.course_code = c.course_code AND m.max_sn = c.serial_no
        """
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def load_done_codes(path: Path) -> set[str]:
    if not path.exists():
        return set()
    done: set[str] = set()
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("course_code") and not r.get("error"):
                done.add(r["course_code"])
    return done


def open_writer(path: Path):
    new_file = not path.exists()
    f = path.open("a", encoding="utf-8", newline="")
    w = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
    if new_file:
        w.writeheader()
        f.flush()
    return f, w


def save_state(state: dict) -> None:
    BATCH_STATE_FILE.write_text(json.dumps(state, indent=2))


# ----------------------------- Batch ops -----------------------------


def make_custom_id(course_code: str) -> str:
    safe = re.sub(r"\W+", "_", course_code)[:60]
    return f"ability__{safe}"


def build_requests(courses: list[dict[str, str]], model: str) -> list[Request]:
    cached_system = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        }
    ]
    reqs = []
    for c in courses:
        user_msg = build_user_message(
            c["course_name"], c["department"] or "", c["objectives"] or "",
            c["overview"] or "", c["grading"] or "",
        )
        reqs.append(
            Request(
                custom_id=make_custom_id(c["course_code"]),
                params=MessageCreateParamsNonStreaming(
                    model=model,
                    max_tokens=MAX_TOKENS,
                    system=cached_system,
                    messages=[{"role": "user", "content": user_msg}],
                ),
            )
        )
    return reqs


def submit_batch(client: anthropic.Anthropic, requests: list[Request]) -> str:
    log.info("送出 batch (%d 筆)...", len(requests))
    batch = client.messages.batches.create(requests=requests)
    log.info("batch_id=%s status=%s", batch.id, batch.processing_status)
    return batch.id


def poll_batch(client: anthropic.Anthropic, batch_id: str, interval: int = 60) -> Any:
    while True:
        b = client.messages.batches.retrieve(batch_id)
        rc = b.request_counts
        log.info(
            "status=%s | succeeded=%d errored=%d processing=%d",
            b.processing_status, rc.succeeded, rc.errored, rc.processing,
        )
        if b.processing_status == "ended":
            return b
        time.sleep(interval)


def parse_response_text(text: str) -> AbilityTag:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    obj = json.loads(t)
    return AbilityTag.model_validate(obj)


def write_results(
    client: anthropic.Anthropic,
    batch_id: str,
    courses: list[dict[str, str]],
    writer,
    f_handle,
) -> tuple[int, int]:
    by_id = {make_custom_id(c["course_code"]): c for c in courses}
    ok = err = 0
    for result in client.messages.batches.results(batch_id):
        cid = result.custom_id
        meta = by_id.get(cid, {})
        row = {
            "course_code": meta.get("course_code", ""),
            "course_name": meta.get("course_name", ""),
            "logic": "", "writing": "", "coding": "",
            "humanities": "", "teamwork": "", "error": "",
        }
        if result.result.type != "succeeded":
            row["error"] = f"{result.result.type}"
            err += 1
        else:
            msg = result.result.message
            text = next((b.text for b in msg.content if b.type == "text"), "")
            try:
                parsed = parse_response_text(text)
                row.update({
                    "logic": parsed.logic, "writing": parsed.writing,
                    "coding": parsed.coding, "humanities": parsed.humanities,
                    "teamwork": parsed.teamwork,
                })
                ok += 1
            except (json.JSONDecodeError, ValidationError) as e:
                row["error"] = f"parse_error: {e}"
                err += 1
        writer.writerow(row)
    f_handle.flush()
    return ok, err


# ----------------------------- Main -----------------------------


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=DB_PATH)
    ap.add_argument("--output", type=Path, default=OUTPUT_CSV)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 筆 (測試用)")
    ap.add_argument("--resume", type=str, default="", help="復原既有 batch_id")
    ap.add_argument("--poll-interval", type=int, default=60)
    args = ap.parse_args()

    log.info("db=%s output=%s model=%s", args.db, args.output, args.model)
    all_courses = load_courses(args.db)
    done_codes = load_done_codes(args.output)
    todo = [c for c in all_courses if c["course_code"] not in done_codes]
    log.info("總 %d 個 course_code / 已做 %d / 待做 %d",
             len(all_courses), len(done_codes), len(todo))

    if args.limit and len(todo) > args.limit:
        todo = todo[: args.limit]
        log.info("受 --limit 限制,只處理前 %d", args.limit)

    if not todo and not args.resume:
        log.info("沒有要做的 — 結束")
        return

    client = anthropic.Anthropic()

    if args.resume:
        batch_id = args.resume
    else:
        reqs = build_requests(todo, args.model)
        batch_id = submit_batch(client, reqs)
        save_state({"batch_id": batch_id, "model": args.model, "count": len(reqs)})

    poll_batch(client, batch_id, interval=args.poll_interval)

    f, writer = open_writer(args.output)
    try:
        ok, err = write_results(client, batch_id, todo, writer, f)
        log.info("完成: 成功 %d、失敗 %d → %s", ok, err, args.output)
    finally:
        f.close()

    log.info("接著跑: python backend/scripts/ingest_ability_tags.py")


if __name__ == "__main__":
    main()
