"""
跑完 rematch_reviews.py 後,reviews_raw 會多出「同 post_url 但不同 course_id」的 row。
這些 raw 對應的「結構化評價」(摘要/甜度/loading 等) 跟原 row 共用同一篇貼文,
直接複製 reviews_structured 裡同 post_url 的欄位即可,免再叫 Claude。

寫進 ntu_reviews_structured.csv (append),custom_id 重算成 post_url stem + new course_id。
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_CSV = DATA_DIR / "ntu_reviews_raw.csv"
STRUCT_CSV = DATA_DIR / "ntu_reviews_structured.csv"


def make_custom_id(post_url: str, course_id: str) -> str:
    m = re.search(r"/(M\.\d+\.[A-Z]\.[A-Z0-9]+)\.html", post_url)
    stem = m.group(1) if m else re.sub(r"\W+", "_", post_url)[-40:]
    return f"{stem}__{course_id}"[:64]


def main() -> None:
    raw = pd.read_csv(RAW_CSV, dtype=str).fillna("")
    struct = pd.read_csv(STRUCT_CSV, dtype=str).fillna("")
    print(f"raw rows: {len(raw)}, structured rows: {len(struct)}")

    # 既有 structured 的 (post_url, course_id)
    done_keys = set(zip(struct["post_url"], struct["course_id"]))

    # post_url → 隨便挑一個 structured row (因為同篇貼文的結構化欄位一樣)
    by_post_url: dict[str, dict] = {}
    for _, r in struct.iterrows():
        if r["post_url"] not in by_post_url:
            by_post_url[r["post_url"]] = r.to_dict()

    new_rows = []
    skipped_no_template = 0
    for _, r in raw.iterrows():
        key = (r["post_url"], r["course_id"])
        if key in done_keys:
            continue
        template = by_post_url.get(r["post_url"])
        if not template:
            skipped_no_template += 1
            continue
        new = dict(template)
        new["custom_id"] = make_custom_id(r["post_url"], r["course_id"])
        new["course_id"] = r["course_id"]
        new["course_name"] = r["course_name"]
        new["teacher"] = r["teacher"]
        new_rows.append(new)

    print(f"新增 structured: {len(new_rows)} 筆 (raw 沒對應 structured 模板的: {skipped_no_template})")
    if not new_rows:
        return

    # append
    fields = list(struct.columns)
    with STRUCT_CSV.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        for row in new_rows:
            w.writerow({k: row.get(k, "") for k in fields})
    print(f"已追加到 {STRUCT_CSV}")


if __name__ == "__main__":
    main()
