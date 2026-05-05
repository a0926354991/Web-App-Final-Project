"""
用 Claude 把 ntu_reviews_raw.csv 的原始 PTT 貼文結構化成評分/優缺點/摘要等欄位。

設計：
- 用 Batches API：~2000 筆非即時，省 50% 費用
- 用 Prompt caching (1h TTL)：system prompt 一次寫快取，每筆 request 都讀
- Resumable：依 output CSV 既有 custom_id 跳過已處理列
- 流程：submit batch → poll 到完成 → 寫入 ntu_reviews_structured.csv

需要環境變數 ANTHROPIC_API_KEY。
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import anthropic
import pandas as pd
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request
from pydantic import BaseModel, Field, ValidationError

DATA_DIR = Path(__file__).resolve().parent / "data"
INPUT_CSV = DATA_DIR / "ntu_reviews_raw.csv"
OUTPUT_CSV = DATA_DIR / "ntu_reviews_structured.csv"
BATCH_STATE_FILE = DATA_DIR / ".batch_state.json"

DEFAULT_MODEL = "claude-opus-4-7"  # claude-api skill 規範。要省錢可改 claude-haiku-4-5
MAX_TOKENS = 1024  # output 上限：每筆結構化結果通常 < 500 tokens
CONTENT_CHAR_CAP = 4000  # 過長貼文截斷（罕見：> 4000 字的 PTT 文）

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("structure")


# ----------------------------- Schema -----------------------------


class StructuredReview(BaseModel):
    """單篇 PTT 課程貼文的結構化結果。"""

    is_review: bool = Field(
        description="此貼文是否為實質的課程評價（False = 徵組員/求救/News/問問題等非評價內容）"
    )
    sentiment: str = Field(description="positive | mixed | neutral | negative")
    sweetness: int | None = Field(
        default=None, description="甜度 1-5（給分寬鬆度，越高越甜）；未提及則 null"
    )
    workload: int | None = Field(
        default=None, description="loading 1-5（課業負擔，越高越重）；未提及則 null"
    )
    pros: list[str] = Field(default_factory=list, description="優點短句，最多 5 條")
    cons: list[str] = Field(default_factory=list, description="缺點短句，最多 5 條")
    summary: str = Field(description="1-2 句中文整體摘要")
    confidence: str = Field(description="low | medium | high — 此次抽取的可信度")


# ----------------------------- Prompt -----------------------------


SYSTEM_PROMPT = """你是台大課程評價分析助手。輸入是一篇來自 PTT NTUcourse 板的貼文（包含課名、教師名、原文）。請抽取結構化資訊。

輸出規則：
- 只輸出一個 JSON 物件，不要加 markdown code fence、不要前後空白文字。
- 欄位定義：
  - is_review (bool): 此貼文是否為「實質的課程評價」。若是 [徵組員]/[徵助理]/[求救]/[News]/[加簽公告]/問問題（非評價）等內容 → false。
  - sentiment (string): positive | mixed | neutral | negative，反映作者整體口氣。
  - sweetness (int 1-5 或 null): 甜度，台大用語，越高代表給分越寬鬆/分數越好拿。文中未提及給分傾向則 null。
  - workload (int 1-5 或 null): 作業/loading，越高代表越重/花時間。未提及則 null。
  - pros (string array, 最多 5): 優點短句，每條 ≤ 30 字，從原文歸納，不要直接抄整段。
  - cons (string array, 最多 5): 缺點短句，同上規則。
  - summary (string): 1-2 句中文摘要，描述這門課/這位老師的整體印象。
  - confidence (string): low | medium | high。短文/缺乏細節 → low；標準評價文且資訊充足 → high。

判斷示例：
- 標題 [評價] 110-2 林軒田 資料結構與演算法，內文詳細談 loading、給分、教學 → is_review=true, confidence=high
- 標題 [徵組員] 軟體工程 想找組員 → is_review=false, sentiment=neutral, sweetness=null, workload=null, summary="徵求課程組員，非評價內容"
- 標題 [問題] 想請問這門課要修嗎 → is_review=false, confidence=low

若無法判斷某欄位，sweetness/workload 用 null，pros/cons 用空陣列，sentiment 用 neutral。"""


def build_user_message(course_name: str, teacher: str, content: str) -> str:
    body = content.strip()
    if len(body) > CONTENT_CHAR_CAP:
        body = body[:CONTENT_CHAR_CAP] + "\n[內容過長，已截斷]"
    return f"課程：{course_name}\n教師：{teacher}\n\n--- 原文 ---\n{body}"


# ----------------------------- IO helpers -----------------------------


OUTPUT_COLUMNS = [
    "custom_id",
    "course_id",
    "course_name",
    "teacher",
    "post_url",
    "is_review",
    "sentiment",
    "sweetness",
    "workload",
    "pros",
    "cons",
    "summary",
    "confidence",
    "error",
]


def make_custom_id(post_url: str, course_id: str) -> str:
    """穩定 ID（≤64 char）：取 post_url 的 PTT 檔名 + course_id。"""
    m = re.search(r"/(M\.\d+\.[A-Z]\.[A-Z0-9]+)\.html", post_url)
    stem = m.group(1) if m else re.sub(r"\W+", "_", post_url)[-40:]
    return f"{stem}__{course_id}"[:64]


def load_input(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str).fillna("")
    df["custom_id"] = df.apply(
        lambda r: make_custom_id(r["post_url"], r["course_id"]), axis=1
    )
    # 同 custom_id 去重（理論上 raw csv 已 unique）
    df = df.drop_duplicates(subset=["custom_id"]).reset_index(drop=True)
    return df


def load_done_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        d = pd.read_csv(path, usecols=["custom_id"], dtype=str).fillna("")
        return set(d["custom_id"])
    except Exception as e:
        log.warning("讀取既有輸出失敗: %s", e)
        return set()


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


def load_state() -> dict:
    if BATCH_STATE_FILE.exists():
        return json.loads(BATCH_STATE_FILE.read_text())
    return {}


# ----------------------------- Batch ops -----------------------------


def build_requests(df: pd.DataFrame, model: str) -> list[Request]:
    cached_system = [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        }
    ]
    reqs = []
    for _, r in df.iterrows():
        user_msg = build_user_message(r["course_name"], r["teacher"], r["content"])
        reqs.append(
            Request(
                custom_id=r["custom_id"],
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
    log.info("送出 batch（%d 筆）...", len(requests))
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


def parse_response_text(text: str) -> StructuredReview:
    # 寬容處理：去掉可能的 ```json fence
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.S)
    obj = json.loads(t)
    return StructuredReview.model_validate(obj)


def write_results(
    client: anthropic.Anthropic,
    batch_id: str,
    df: pd.DataFrame,
    writer,
    f_handle,
) -> tuple[int, int]:
    by_id = {r["custom_id"]: r for _, r in df.iterrows()}
    ok = err = 0
    for result in client.messages.batches.results(batch_id):
        cid = result.custom_id
        meta = by_id.get(cid, {})
        row = {
            "custom_id": cid,
            "course_id": meta.get("course_id", ""),
            "course_name": meta.get("course_name", ""),
            "teacher": meta.get("teacher", ""),
            "post_url": meta.get("post_url", ""),
            "is_review": "",
            "sentiment": "",
            "sweetness": "",
            "workload": "",
            "pros": "",
            "cons": "",
            "summary": "",
            "confidence": "",
            "error": "",
        }
        if result.result.type != "succeeded":
            row["error"] = f"{result.result.type}:{getattr(result.result, 'error', '')}"
            err += 1
        else:
            msg = result.result.message
            text = next((b.text for b in msg.content if b.type == "text"), "")
            try:
                parsed = parse_response_text(text)
                row.update({
                    "is_review": parsed.is_review,
                    "sentiment": parsed.sentiment,
                    "sweetness": parsed.sweetness if parsed.sweetness is not None else "",
                    "workload": parsed.workload if parsed.workload is not None else "",
                    "pros": "|".join(parsed.pros),
                    "cons": "|".join(parsed.cons),
                    "summary": parsed.summary,
                    "confidence": parsed.confidence,
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
    ap.add_argument("--input", type=Path, default=INPUT_CSV)
    ap.add_argument("--output", type=Path, default=OUTPUT_CSV)
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help="claude-opus-4-7 (預設) 或 claude-haiku-4-5（~5x 便宜）")
    ap.add_argument("--limit", type=int, default=0,
                    help="只處理前 N 筆（測試用）")
    ap.add_argument("--resume", type=str, default="",
                    help="復原既有 batch_id（跳過 submit，直接抓結果）")
    ap.add_argument("--poll-interval", type=int, default=60)
    args = ap.parse_args()

    log.info("input=%s output=%s model=%s", args.input, args.output, args.model)
    raw_df = load_input(args.input)
    done_ids = load_done_ids(args.output)
    todo_df = raw_df[~raw_df["custom_id"].isin(done_ids)].reset_index(drop=True)
    log.info("總 %d 列 / 已處理 %d / 待做 %d",
             len(raw_df), len(done_ids), len(todo_df))

    if args.limit and len(todo_df) > args.limit:
        todo_df = todo_df.head(args.limit)
        log.info("受 --limit 限制，只處理前 %d", args.limit)

    if len(todo_df) == 0 and not args.resume:
        log.info("沒有要做的 — 結束")
        return

    client = anthropic.Anthropic()

    if args.resume:
        batch_id = args.resume
        log.info("resume batch_id=%s", batch_id)
    else:
        reqs = build_requests(todo_df, args.model)
        batch_id = submit_batch(client, reqs)
        save_state({"batch_id": batch_id, "model": args.model, "count": len(reqs)})

    poll_batch(client, batch_id, interval=args.poll_interval)

    f, writer = open_writer(args.output)
    try:
        ok, err = write_results(client, batch_id, todo_df, writer, f)
        log.info("完成：成功 %d、失敗 %d → %s", ok, err, args.output)
    finally:
        f.close()


if __name__ == "__main__":
    main()
