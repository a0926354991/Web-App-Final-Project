"""
台大課程網「課程詳情頁」爬蟲 v2 — 補長文 (課程概述/目標/要求/評量方式/備註/預期時數)。

跟舊 Web-crawler.py 的差別:
- 舊版 _extract_sections 的 Regex 針對舊版 DOM,課程網改版 (v3.x) 後抓不到長文 → 全空。
- 本版按新版頁面實際的 section 標題順序純文字切分:
  課程概述 → 課程目標 → 課程要求 → 預期每週課前或/與課後學習時數 →
  Office Hour → 指定閱讀 → 參考書目 → 評量方式 → 針對學生困難... → 補課資訊 → 課程進度
  每段內容 = 該標題到「下一個實際出現的標題」之間 (空段 = 兩標題相鄰)。

輸入: v2 列表 CSV (含 詳情頁URL 欄),省掉重新滾動收集 URL。
輸出: 同名 _detail.csv,欄位 = 流水號 + 各長文段 (供之後用流水號 merge 回 app.db)。
支援 resume: 既有輸出 CSV 內的流水號會跳過。

用法:
    python backend/detail_crawler_v2.py --input backend/data/ntu_list_data_114-2_v2.csv --semester 114-2
    python backend/detail_crawler_v2.py --input ... --semester 114-2 --max-count 20 --show-browser
"""

from __future__ import annotations

import argparse
import asyncio
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
from playwright.async_api import async_playwright, Page

GOTO_TIMEOUT_MS = 90_000
DETAIL_WAIT_MS = 2500
CHECKPOINT_EVERY = 50
BROWSER_RECYCLE = 300  # 每 N 頁重建 browser,避免長跑記憶體累積崩潰

# section 標題依新版頁面 DOM 順序。最後一段用「結尾雜訊」當邊界。
_SECTION_ORDER = [
    "課程概述", "課程目標", "課程要求",
    "預期每週課前或/與課後學習時數", "Office Hour", "指定閱讀", "參考書目",
    "評量方式", "針對學生困難提供學生調整方式", "補課資訊", "課程進度",
]
# 評量方式段常被頁面 footer / 制度說明污染,這些當作評量方式的提早結束點
_EVAL_NOISE_ENDS = ("針對學生困難", "補課資訊", "課程進度", "特別贊助", "臺大課程網", "Copyright")

OUTPUT_COLS = ["流水號", "開課系所", "課程概述", "課程目標", "課程要求", "評量方式", "預期學習時數"]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _slice(text: str, start_label: str, end_labels: tuple[str, ...]) -> str:
    """取 start_label 之後到最近的 end_label 之間的內容。"""
    i = text.find(start_label)
    if i == -1:
        return ""
    j = i + len(start_label)
    while j < len(text) and text[j] in " ：:\t\n\r":
        j += 1
    end = len(text)
    for lab in end_labels:
        k = text.find(lab, j)
        if k != -1 and k < end:
            end = k
    return text[j:end].strip()


def _extract_sections(full_text: str) -> dict[str, str]:
    i0 = full_text.find("課程概述")
    region = full_text[i0:] if i0 != -1 else full_text

    def after(label: str) -> tuple[str, ...]:
        idx = _SECTION_ORDER.index(label)
        return tuple(_SECTION_ORDER[idx + 1:])

    overview = _slice(region, "課程概述", after("課程概述"))
    goals = _slice(region, "課程目標", after("課程目標"))
    requirements = _slice(region, "課程要求", after("課程要求"))
    hours = _slice(region, "預期每週課前或/與課後學習時數", after("預期每週課前或/與課後學習時數"))
    eval_text = _slice(region, "評量方式", _EVAL_NOISE_ENDS)

    # 評量方式若只剩制度樣板 (本校尚無訂定 A+...),視為無真實內容
    if eval_text and eval_text.startswith("本校尚無訂定") and "本校採用等第制" in eval_text:
        eval_text = ""

    return {
        "課程概述": overview,
        "課程目標": goals,
        "課程要求": requirements,
        "評量方式": eval_text,
        "預期學習時數": hours,
    }


def _extract_dept(text: str) -> str:
    """開課系所: 學分後一組,或 '必帶/必修/選修' 下一行。"""
    m = re.search(r"(\d+)\s*學分\s*\n\s*(必帶|必修|選修)\s*\n\s*([^\n\r]+)", text)
    if m:
        return m.group(3).strip()
    return ""


async def scrape_detail(page: Page, url: str) -> dict[str, str]:
    await page.goto(url, wait_until="networkidle", timeout=GOTO_TIMEOUT_MS)
    await page.wait_for_timeout(DETAIL_WAIT_MS)
    text = await page.locator("body").inner_text()

    serial = ""
    m = re.search(r"流水號\s*\n?\s*(\d{5})\b", text)
    if m:
        serial = m.group(1)
    if not serial:
        m = re.search(r"/courses/[^/]+/(\d{5})", url)
        serial = m.group(1) if m else ""

    sec = _extract_sections(text)
    return {
        "流水號": serial,
        "開課系所": _extract_dept(text),
        "課程概述": sec["課程概述"],
        "課程目標": sec["課程目標"],
        "課程要求": sec["課程要求"],
        "評量方式": sec["評量方式"],
        "預期學習時數": sec["預期學習時數"],
    }


def _load_done(csv_path: Path) -> set[str]:
    if not csv_path.exists():
        return set()
    try:
        df = pd.read_csv(csv_path, dtype=str, usecols=["流水號"]).fillna("")
        return {s for s in df["流水號"] if s}
    except Exception:
        return set()


def _flush(rows: list[dict], csv_path: Path) -> None:
    if not rows:
        return
    df = pd.DataFrame(rows)[OUTPUT_COLS]
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, mode="a", index=False, header=not csv_path.exists(), encoding="utf-8-sig")


async def run(input_csv: Path, output_csv: Path, max_count: int, headless: bool, slow_mo: int) -> None:
    df_in = pd.read_csv(input_csv, dtype=str).fillna("")
    urls = [u for u in df_in["詳情頁URL"].tolist() if u.strip()]
    done = _load_done(output_csv)
    if done:
        print(f"[{_now()}] resume: 已有 {len(done)} 筆,會跳過")

    # 用流水號判斷是否跳過
    pending = []
    for _, r in df_in.iterrows():
        sn = r["流水號"].strip()
        url = r["詳情頁URL"].strip()
        if not url or sn in done:
            continue
        pending.append(url)
        if len(pending) >= max_count:
            break

    print(f"[{_now()}] input={input_csv.name} 待抓 {len(pending)} 筆 → {output_csv.name}")

    buffer: list[dict] = []
    written = 0
    total = len(pending)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, slow_mo=slow_mo)
        page = await (await browser.new_context(locale="zh-TW")).new_page()
        for idx, url in enumerate(pending, 1):
            # 每頁 retry 2 次;失敗就重建 page (常見:單頁 timeout / context 壞掉)
            data = None
            for attempt in range(2):
                try:
                    data = await scrape_detail(page, url)
                    break
                except Exception as e:
                    if attempt == 0:
                        try:
                            await page.close()
                        except Exception:
                            pass
                        page = await (await browser.new_context(locale="zh-TW")).new_page()
                    else:
                        print(f"[{_now()}] [{idx}/{total}] 跳過(retry 後仍失敗): {url} — {e!s}")
            if data is not None:
                buffer.append(data)

            if idx % 100 == 0:
                ov = sum(1 for b in buffer if b["課程概述"])
                print(f"[{_now()}]   [{idx}/{total}] (本批已抓概述 {ov}/{len(buffer)})")
            if len(buffer) >= CHECKPOINT_EVERY:
                _flush(buffer, output_csv); written += len(buffer); buffer.clear()

            # 每 BROWSER_RECYCLE 頁重建 browser,避免長跑記憶體累積導致 chromium 崩潰
            if idx % BROWSER_RECYCLE == 0:
                try:
                    await browser.close()
                except Exception:
                    pass
                browser = await p.chromium.launch(headless=headless, slow_mo=slow_mo)
                page = await (await browser.new_context(locale="zh-TW")).new_page()
                print(f"[{_now()}]   ↻ 重建 browser @ {idx}")

        try:
            await browser.close()
        except Exception:
            pass
    if buffer:
        _flush(buffer, output_csv); written += len(buffer)
    print(f"[{_now()}] 完成,本次新增 {written} 筆 → {output_csv}")


def main() -> None:
    ap = argparse.ArgumentParser(description="台大課程詳情頁爬蟲 v2 (補長文)")
    ap.add_argument("--input", type=Path, required=True, help="v2 列表 CSV (含 詳情頁URL 欄)")
    ap.add_argument("--semester", default=None, help="僅用於預設輸出檔名")
    ap.add_argument("--output", type=Path, default=None)
    ap.add_argument("--max-count", type=int, default=99999)
    ap.add_argument("--show-browser", action="store_true")
    ap.add_argument("--slow-mo", type=int, default=0)
    args = ap.parse_args()

    output = args.output or args.input.with_name(args.input.stem.replace("_v2", "") + "_detail_v2.csv")
    asyncio.run(run(args.input, output, args.max_count, headless=not args.show_browser, slow_mo=args.slow_mo))


if __name__ == "__main__":
    main()
