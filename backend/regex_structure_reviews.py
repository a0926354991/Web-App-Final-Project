"""
用 regex 把 ntu_reviews_raw.csv 結構化成評分/loading/教學等欄位。

策略：
- PTT NTUcourse [評價] 文有固定模板：希臘字母 (ψ/λ/δ/Ω/η/μ/σ/ρ/ω/Ψ) 當欄位標頭。
- 切段 → 各欄位文字 → 從 Ω 段抽推薦指數（★ 數）+ σ/ω 段關鍵字推甜度/loading。
- 非模板貼文（[心得]/[問題]/Re:）多半 has_template=false，只填 raw 摘要。

LLM-free，免 API。覆蓋以 [評價] 標籤、模板格式為主。
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"
INPUT_CSV = DATA_DIR / "ntu_reviews_raw.csv"
OUTPUT_CSV = DATA_DIR / "ntu_reviews_structured.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("regex")


# ----------------------------- Section parsing -----------------------------


# 希臘字母段落標頭。順序很重要：每段從一個標頭跑到下一個標頭為止。
# 用 (key, marker_pattern) 列表 — marker 是 regex（容忍空白與括號變體）。
_SECTIONS: list[tuple[str, str]] = [
    ("teacher",            r"ψ\s*授課教師"),
    ("department",         r"λ\s*開課系所"),
    ("course_content",     r"δ\s*課程"),
    ("recommendation_raw", r"Ω\s*私心推薦"),
    ("textbook",           r"η\s*上課用書"),
    ("teaching_style",     r"μ\s*上課方式"),
    ("grading_method",     r"σ\s*評分方式"),
    ("exam_style",         r"ρ\s*考題"),
    ("other",              r"ω\s*其[他它]"),
    ("summary",            r"Ψ\s*總結"),
]
# 任意已知標頭（用來當「結束點」）
_ANY_MARKER = r"(?:" + "|".join(p for _, p in _SECTIONS) + r")"


def split_sections(content: str) -> dict[str, str]:
    """把貼文內文切成 {section_name: text}。沒出現的欄位為空字串。"""
    if not content:
        return {}
    out: dict[str, str] = {}
    for key, marker in _SECTIONS:
        pat = rf"{marker}[^\n]*\n+(.*?)(?=\n\s*{_ANY_MARKER}|\Z)"
        m = re.search(pat, content, flags=re.S)
        if m:
            out[key] = m.group(1).strip()
    return out


# ----------------------------- Field extraction -----------------------------


def parse_recommendation(raw: str) -> int | None:
    """從 Ω 段抽推薦指數 (1-5)。優先 ★ 數，退而求其次用「推/雷」字。"""
    if not raw:
        return None
    # ★/☆ 群組：模板常分多項（喜歡大自然★★★★★/剪片★★★），取平均較公允
    star_groups = re.findall(r"[★⭐]+", raw)
    if star_groups:
        avg = sum(len(g) for g in star_groups) / len(star_groups)
        return max(1, min(5, round(avg)))
    # 文字描述
    txt = raw.replace(" ", "")
    if "推推推" in txt or "超推" in txt or "強烈推薦" in txt:
        return 5
    if "推推" in txt:
        return 4
    if re.search(r"(?<!不)(?<!負)推(?!倒)", txt):
        return 4
    if "普普" in txt or "普通" in txt or "中規中矩" in txt:
        return 3
    if "不推" in txt:
        return 2
    if "雷" in txt or "負雷" in txt or "地雷" in txt:
        return 1
    return None


_SWEET_POS_STRONG = ("超甜", "很甜", "佛", "送分", "甜涼", "涼甜", "甜課", "佛心")
_SWEET_POS = ("甜", "涼", "easy", "Easy", "好過", "高分", "拿 A+", "拿A+")
_SWEET_NEG_STRONG = ("超硬", "很硬", "硬課", "嚴格給分", "壓分")
_SWEET_NEG = ("硬", "紮實", "不甜", "不涼", "硬給", "低分", "難拿")


def estimate_sweetness(grading_text: str, summary_text: str = "") -> int | None:
    """從 σ/Ψ 段關鍵字推甜度 1-5。神經兮兮地保守處理：訊號弱就回 None。"""
    text = (grading_text or "") + "\n" + (summary_text or "")
    if not text.strip():
        return None
    score = 0
    hits = 0
    for kw in _SWEET_POS_STRONG:
        if kw in text:
            score += 2; hits += 1
    for kw in _SWEET_POS:
        if kw in text:
            score += 1; hits += 1
    for kw in _SWEET_NEG_STRONG:
        if kw in text:
            score -= 2; hits += 1
    for kw in _SWEET_NEG:
        if kw in text:
            score -= 1; hits += 1
    if hits == 0:
        return None
    # 把累積分映射到 1-5（中性 = 3）
    return max(1, min(5, 3 + max(-2, min(2, score))))


_LOAD_HEAVY_STRONG = ("超重", "很重", "loading 爆", "loading爆", "爆肝", "熬夜")
_LOAD_HEAVY = ("loading 重", "loading重", "重", "作業多", "報告多", "花時間",
               "壓力大", "讀很多", "要讀")
_LOAD_LIGHT_STRONG = ("超輕", "完全沒作業", "幾乎沒作業", "loading 0", "零 loading")
_LOAD_LIGHT = ("loading 輕", "loading輕", "輕鬆", "不重", "少", "沒什麼作業",
               "輕")


def estimate_workload(grading: str, exam: str, other: str, summary: str) -> int | None:
    """從多段文字推 loading 1-5。1=輕、5=重。訊號弱回 None。"""
    text = "\n".join(filter(None, [grading, exam, other, summary]))
    if not text.strip():
        return None
    score = 0
    hits = 0
    for kw in _LOAD_HEAVY_STRONG:
        if kw in text:
            score += 2; hits += 1
    for kw in _LOAD_HEAVY:
        if kw in text:
            score += 1; hits += 1
    for kw in _LOAD_LIGHT_STRONG:
        if kw in text:
            score -= 2; hits += 1
    for kw in _LOAD_LIGHT:
        if kw in text:
            score -= 1; hits += 1
    if hits == 0:
        return None
    return max(1, min(5, 3 + max(-2, min(2, score))))


def parse_year_term(content: str) -> str:
    """抽 '學年度修課: 110-2' 之類的字串。"""
    m = re.search(r"學年度修課[：:\s]*([\d０-９]{2,3}[\-\s]*[\d１２一二上下]+)", content)
    return m.group(1).strip() if m else ""


def truncate(s: str, n: int) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s if len(s) <= n else s[:n] + "…"


# ----------------------------- Tag -----------------------------


_TAG_RE = re.compile(r"\[([^\]]+)\]")


def post_tag(title: str) -> str:
    m = _TAG_RE.search(title or "")
    return m.group(1).strip() if m else ""


# ----------------------------- Main -----------------------------


OUTPUT_COLUMNS = [
    "custom_id",
    "course_id",
    "course_name",
    "teacher",
    "post_url",
    "post_title",
    "post_date",
    "post_tag",
    "year_term",
    "has_template",
    "recommendation",   # 1-5 或空
    "sweetness",        # 1-5 或空
    "workload",         # 1-5 或空
    "teaching_style",   # 摘要文字
    "grading_method",
    "summary",
]


def make_custom_id(post_url: str, course_id: str) -> str:
    m = re.search(r"/(M\.\d+\.[A-Z]\.[A-Z0-9]+)\.html", post_url)
    stem = m.group(1) if m else re.sub(r"\W+", "_", post_url)[-40:]
    return f"{stem}__{course_id}"[:64]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=INPUT_CSV)
    ap.add_argument("--output", type=Path, default=OUTPUT_CSV)
    args = ap.parse_args()

    log.info("讀取: %s", args.input)
    df = pd.read_csv(args.input, dtype=str).fillna("")
    log.info("輸入 %d 列", len(df))

    rows = []
    template_count = 0
    rec_hits = sweet_hits = load_hits = 0

    for _, r in df.iterrows():
        content = r["content"]
        sections = split_sections(content)
        has_template = bool(sections.get("recommendation_raw") or sections.get("grading_method"))
        if has_template:
            template_count += 1

        rec = parse_recommendation(sections.get("recommendation_raw", ""))
        sweet = estimate_sweetness(sections.get("grading_method", ""), sections.get("summary", ""))
        load = estimate_workload(
            sections.get("grading_method", ""),
            sections.get("exam_style", ""),
            sections.get("other", ""),
            sections.get("summary", ""),
        )
        if rec is not None: rec_hits += 1
        if sweet is not None: sweet_hits += 1
        if load is not None: load_hits += 1

        rows.append({
            "custom_id": make_custom_id(r["post_url"], r["course_id"]),
            "course_id": r["course_id"],
            "course_name": r["course_name"],
            "teacher": r["teacher"],
            "post_url": r["post_url"],
            "post_title": r["post_title"],
            "post_date": r["post_date"],
            "post_tag": post_tag(r["post_title"]),
            "year_term": parse_year_term(content),
            "has_template": has_template,
            "recommendation": rec if rec is not None else "",
            "sweetness": sweet if sweet is not None else "",
            "workload": load if load is not None else "",
            "teaching_style": truncate(sections.get("teaching_style", ""), 300),
            "grading_method": truncate(sections.get("grading_method", ""), 300),
            "summary": truncate(sections.get("summary", "") or sections.get("course_content", ""), 300),
        })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        w.writeheader()
        w.writerows(rows)

    n = len(rows)
    log.info("輸出 %d 列 → %s", n, args.output)
    log.info("模板貼文 %d (%.1f%%)", template_count, 100 * template_count / n)
    log.info("欄位命中：推薦 %d (%.0f%%) | 甜度 %d (%.0f%%) | loading %d (%.0f%%)",
             rec_hits, 100 * rec_hits / n,
             sweet_hits, 100 * sweet_hits / n,
             load_hits, 100 * load_hits / n)


if __name__ == "__main__":
    main()
