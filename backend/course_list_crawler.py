"""
台大課程網「快速搜尋」列表爬蟲 (DOM-based)。

跟舊版 Web-crawler.py 的差別:
- 舊版逐筆進「課程詳情頁」用整頁純文字 + Regex 猜行抓欄位,
  上課時間/地點常錯位或混入合授老師、括號殘渣 (地點覆蓋率僅 ~13%)。
- 本版直接從搜尋頁列表的 DOM 結構抓:每門課是一個 <li class="group">,
  其中 .order-3 容器內的 span.z-10 依序是「教師 / 上課時間 / 上課地點」。
  沒固定時段的課 (服務學習 / 專題研究 / 論文) 只有教師一個 span,不會錯位。

注意: 列表是虛擬捲動 (virtual list),DOM 同時只保留約 14-28 個 <li>,
滑出視窗的會被回收。所以必須邊 scroll 邊抓,用流水號去重即時收集。

只抓列表頁就有的欄位 (含正確的時間/地點)。需要課程概述/目標/評量等長文,
仍要走詳情頁 (見 Web-crawler.py)。兩者可用流水號 join 後合併。

用法:
    python backend/course_list_crawler.py --semester 114-2
    python backend/course_list_crawler.py --semester 114-2 --max-count 10 --show-browser
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from pathlib import Path

import pandas as pd
from playwright.async_api import async_playwright, Page

SEARCH_URL_TEMPLATE = "https://course.ntu.edu.tw/search/quick?s={semester}"
DEFAULT_SEARCH_URL = "https://course.ntu.edu.tw/search/quick"
_DATA_DIR = Path(__file__).resolve().parent / "data"

DEFAULT_MAX_COUNT = 9999
SCROLL_STEP_PX = 6000
SCROLL_PAUSE_MS = 1200
MAX_STALE_ROUNDS = 30  # 連續這麼多輪沒新增就停 (到底了)

# 列表卡片每筆會抓出的欄位 → CSV 欄名 (跟 Web-crawler.py 的 OUTPUT_COLS 對齊,
# 方便之後 join / ingest;列表頁沒有的長文欄位留空)
OUTPUT_COLS = [
    "課名", "教師", "流水號", "課號", "課程識別碼", "必選修",
    "開課系所", "上課時間", "上課地點", "加簽類別", "授課語言",
    "學分", "修課人數上限", "詳情頁URL",
]

# 在瀏覽器端解析每個 <li> 卡片 → 結構化欄位。
# 回傳 list[dict]。靠 DOM 結構 (span 順序) 抓,不靠純文字猜行。
_EXTRACT_JS = r"""
() => {
  const lis = [...document.querySelectorAll('ul li.group')];
  const out = [];
  for (const li of lis) {
    const link = li.querySelector('a[href*="/courses/"]');
    if (!link) continue;
    const href = link.getAttribute('href') || '';
    const name = (link.textContent || '').trim();

    // .order-3 容器內的「chip」是 div.z-10.inline-flex (不是 span),依序:
    //   [0]=教師, [1]=上課時間(可選), [2]=上課地點(可選)。
    // 沒固定時段的課 (服務學習/專題/論文) 只有教師一個 chip,不會錯位。
    const info = li.querySelector('.order-3');
    let teacher = '', schedule = '', location = '';
    if (info) {
      const chips = [...info.querySelectorAll('div.z-10.inline-flex')];
      if (chips[0]) teacher = (chips[0].textContent || '').trim();
      // 時間欄含 weekday + 節次;地點欄不含。用內容判斷,避免只有其一時錯位。
      const looksLikeTime = t => /[一二三四五六日]\s*[\dA-D]/.test(t) || /密集|另訂|彈性|時間另訂/.test(t);
      for (const c of chips.slice(1)) {
        const t = (c.textContent || '').trim();
        if (!t) continue;
        if (!schedule && looksLikeTime(t)) { schedule = t; continue; }
        if (!location) { location = t; }
      }
    }

    // 流水號 / 課號 / 課程識別碼: 在 .text-muted-foreground 那排 div.z-10,
    // 每格 textContent = 中文 label + value (e.g. "流水號18496")。去掉 label 即 value。
    const stripLabel = (label) => {
      const cells = [...li.querySelectorAll('div.z-10')];
      for (const c of cells) {
        const txt = (c.textContent || '').trim();
        if (txt.startsWith(label)) return txt.slice(label.length).trim();
      }
      return '';
    };
    const serial = stripLabel('流水號');
    const code = stripLabel('課號');
    const uid = stripLabel('課程識別碼');

    // 學分 / 加簽類別 / 必選修: 在 .order-4 的 chip 列, 文字如「必帶3 學分2 類50 人領域專長」
    const chipBox = li.querySelector('.order-4');
    let credits = '', signup = '', reqType = '';
    if (chipBox) {
      const chips = [...chipBox.children].map(c => (c.textContent || '').trim()).filter(Boolean);
      for (const c of chips) {
        let m;
        if (!credits && (m = c.match(/^(\d+)\s*學分/))) credits = m[1];
        else if (!signup && (m = c.match(/^(\d+)\s*類/))) signup = m[1] + ' 類';
        else if (!reqType && /^(必帶|必修|選修)/.test(c)) reqType = c;
      }
    }

    out.push({
      name, teacher, serial, code, uid,
      schedule, location, credits, signup, reqType, href,
    });
  }
  return out;
};
"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


async def crawl(page: Page, max_count: int) -> dict[str, dict]:
    """邊 scroll 邊抓,用流水號去重。回傳 {serial: row}。"""
    collected: dict[str, dict] = {}
    stale = 0
    scrolls = 0

    while len(collected) < max_count and stale < MAX_STALE_ROUNDS:
        before = len(collected)
        cards = await page.evaluate(_EXTRACT_JS)
        for c in cards:
            sn = c.get("serial")
            if not sn or sn in collected:
                continue
            collected[sn] = {
                "課名": c["name"],
                "教師": c["teacher"],
                "流水號": sn,
                "課號": c["code"],
                "課程識別碼": c["uid"],
                "必選修": c["reqType"],
                "開課系所": "",  # 列表頁無 (詳情頁才有);留空待 join
                "上課時間": c["schedule"],
                "上課地點": c["location"],
                "加簽類別": c["signup"],
                "授課語言": "",  # 列表頁無
                "學分": c["credits"],
                "修課人數上限": "",  # 列表頁的 chip 是「N 人」,但與已選上混排,留待詳情頁
                "詳情頁URL": ("https://course.ntu.edu.tw" + c["href"]) if c["href"].startswith("/") else c["href"],
            }
            if len(collected) >= max_count:
                break

        if len(collected) == before:
            stale += 1
        else:
            stale = 0

        scrolls += 1
        if scrolls % 10 == 0:
            print(f"[{_now()}]   scroll #{scrolls}: 已收集 {len(collected)} 筆 (stale={stale})")

        if len(collected) >= max_count:
            break
        await page.mouse.wheel(0, SCROLL_STEP_PX)
        await page.wait_for_timeout(SCROLL_PAUSE_MS)

    print(f"[{_now()}] 收集完成: {len(collected)} 筆 (scroll {scrolls} 次)")
    return collected


async def run(semester: str | None, output_csv: Path, max_count: int,
              headless: bool, slow_mo: int) -> None:
    start_url = SEARCH_URL_TEMPLATE.format(semester=semester) if semester else DEFAULT_SEARCH_URL
    print(f"[{_now()}] start_url = {start_url}")
    print(f"[{_now()}] output    = {output_csv}")
    print(f"[{_now()}] max_count = {max_count}, headless = {headless}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, slow_mo=slow_mo)
        context = await browser.new_context(locale="zh-TW")
        page = await context.new_page()
        await page.goto(start_url, wait_until="networkidle", timeout=90_000)
        await page.wait_for_timeout(3000)
        try:
            await page.wait_for_selector("ul li.group", timeout=60_000)
        except Exception:
            print(f"[{_now()}] 找不到課程列表,頁面結構可能改版。")
            await browser.close()
            return

        rows = await crawl(page, max_count)
        await browser.close()

    if not rows:
        print(f"[{_now()}] 沒抓到任何資料。")
        return

    df = pd.DataFrame(list(rows.values()))[OUTPUT_COLS]
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False, encoding="utf-8-sig")

    n_time = (df["上課時間"].str.strip() != "").sum()
    n_loc = (df["上課地點"].str.strip() != "").sum()
    print(f"[{_now()}] 寫入 {len(df)} 筆 → {output_csv}")
    print(f"[{_now()}] 有上課時間: {n_time} ({n_time/len(df)*100:.1f}%) / 有地點: {n_loc} ({n_loc/len(df)*100:.1f}%)")


def _default_output(semester: str | None) -> Path:
    suffix = f"_{semester.replace('/', '_')}" if semester else ""
    return _DATA_DIR / f"ntu_list_data{suffix}.csv"


def main() -> None:
    ap = argparse.ArgumentParser(description="台大課程網快速搜尋列表爬蟲 (DOM-based,正確抓時間/地點)")
    ap.add_argument("--semester", default=None, help="學年期 (e.g. 114-2);省略 = 站方預設")
    ap.add_argument("--output", type=Path, default=None, help="輸出 CSV 路徑")
    ap.add_argument("--max-count", type=int, default=DEFAULT_MAX_COUNT, help=f"最多抓取筆數 (預設 {DEFAULT_MAX_COUNT})")
    ap.add_argument("--show-browser", action="store_true", help="開瀏覽器視窗 (預設 headless)")
    ap.add_argument("--slow-mo", type=int, default=0, help="Playwright slow_mo (ms)")
    args = ap.parse_args()

    output = args.output or _default_output(args.semester)
    asyncio.run(run(args.semester, output, args.max_count,
                    headless=not args.show_browser, slow_mo=args.slow_mo))


if __name__ == "__main__":
    main()
