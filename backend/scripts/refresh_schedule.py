"""
針對既有 ntu_detailed_data.csv 中 schedule_time 為空的課,
重新訪問該課的詳情頁,用更新版的 _extract_schedule_time 重抽。

策略:
- 讀 CSV → 過濾出 schedule_time 為空的列
- 逐筆 (或小 batch) 訪問該列的「詳情頁URL」
- 更新該列的 schedule_time
- 寫回 CSV (in-place)

支援:
- --limit N : 只處理前 N 筆 (測試用)
- --start N : 從第 N 筆開始 (續跑用)

Resumable: 跑完一筆立刻 flush CSV,中斷再跑時自動跳過已有 schedule 的行。

執行:
    python -m backend.scripts.refresh_schedule --limit 20      # 試 20 筆
    python -m backend.scripts.refresh_schedule                  # 全部
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sys
from pathlib import Path

import pandas as pd
from playwright.async_api import async_playwright

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CSV_PATH = DATA_DIR / "ntu_detailed_data.csv"

DETAIL_EXTRA_WAIT_MS = 2500
GOTO_TIMEOUT_MS = 60_000


# 從 backend/Web-crawler.py 借出 _extract_schedule_time
def _load_extract_fn():
    spec = importlib.util.spec_from_file_location(
        "webc", Path(__file__).resolve().parent.parent / "Web-crawler.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._extract_schedule_time


extract_schedule = _load_extract_fn()


async def fetch_schedule(page, url: str) -> str:
    try:
        await page.goto(url, wait_until="networkidle", timeout=GOTO_TIMEOUT_MS)
        await page.wait_for_timeout(DETAIL_EXTRA_WAIT_MS)
        text = await page.evaluate("document.body.innerText")
        return extract_schedule(text)
    except Exception as e:
        print(f"  ⚠ goto/extract 失敗: {e}", file=sys.stderr)
        return ""


async def main(start: int, limit: int | None) -> None:
    df = pd.read_csv(CSV_PATH, dtype=str).fillna("")

    # 哪些 row 要 refresh: 已有 schedule_time 的跳過
    empty_mask = df["上課時間"].str.strip() == ""
    candidates = df[empty_mask].copy()
    candidates = candidates.iloc[start:]
    if limit:
        candidates = candidates.head(limit)

    total = len(candidates)
    print(f"待處理: {total} 筆 (CSV 共 {len(df)} 筆,{empty_mask.sum()} 筆空)")
    if total == 0:
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for i, (idx, row) in enumerate(candidates.iterrows(), start=1):
            url = row["詳情頁URL"]
            if not url:
                continue
            sched = await fetch_schedule(page, url)
            if sched:
                df.at[idx, "上課時間"] = sched
                # 每筆都寫回 CSV (resumable)
                df.to_csv(CSV_PATH, index=False)
                print(f"  [{i}/{total}] {row['課名'][:18]} → {sched!r}")
            else:
                print(f"  [{i}/{total}] {row['課名'][:18]} → (沒抓到)")

        await browser.close()
    print("done.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    asyncio.run(main(args.start, args.limit))
