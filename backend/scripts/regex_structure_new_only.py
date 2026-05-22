"""
只對「raw 裡 post_url 不在 structured 裡」的新貼文跑 regex_structure_reviews,
然後 append 到 ntu_reviews_structured.csv。
不覆蓋既有(可能由 LLM 標的)結構化資料。

用於 PTT 重爬後補結構化(LLM-free / 免 API key)。
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from regex_structure_reviews import (  # noqa: E402
    OUTPUT_COLUMNS,
    estimate_sweetness,
    estimate_workload,
    make_custom_id,
    parse_recommendation,
    parse_year_term,
    post_tag,
    split_sections,
    truncate,
)

DATA_DIR = BACKEND_DIR / "data"
RAW_CSV = DATA_DIR / "ntu_reviews_raw.csv"
STRUCT_CSV = DATA_DIR / "ntu_reviews_structured.csv"


def main() -> None:
    raw = pd.read_csv(RAW_CSV, dtype=str).fillna("")
    struct = pd.read_csv(STRUCT_CSV, dtype=str).fillna("")
    print(f"raw rows: {len(raw)}, structured rows: {len(struct)}")

    done_keys = set(zip(struct["post_url"], struct["course_id"]))

    rows = []
    template_count = rec_hits = sweet_hits = load_hits = 0
    for _, r in raw.iterrows():
        if (r["post_url"], r["course_id"]) in done_keys:
            continue
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

    print(f"新增 structured: {len(rows)} 筆")
    if not rows:
        return
    print(f"  模板貼文: {template_count} ({100*template_count/len(rows):.0f}%)")
    print(f"  推薦命中: {rec_hits} | 甜度命中: {sweet_hits} | loading 命中: {load_hits}")

    with STRUCT_CSV.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        for row in rows:
            w.writerow({k: row.get(k, "") for k in OUTPUT_COLUMNS})
    print(f"已追加到 {STRUCT_CSV}")


if __name__ == "__main__":
    main()
