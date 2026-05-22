"""
台大課程網 (course.ntu.edu.tw) Playwright 爬蟲：搜尋頁蒐集詳情連結 → 逐筆抓取欄位 → 輸出 CSV。
"""

from __future__ import annotations

import argparse
import asyncio
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import pandas as pd
from playwright.async_api import async_playwright, Page

# --- 可調參數 ---
DEFAULT_MAX_COUNT = 9899
# 站方搜尋頁路由 (?s=114-1 切學期);課程詳情為 /courses/{學期}/{流水號}
SEARCH_URL_TEMPLATE = "https://course.ntu.edu.tw/search/quick?s={semester}"
DEFAULT_SEARCH_URL = "https://course.ntu.edu.tw/zh-TW/search/quick"  # 不指定 semester → 站方預設
_DATA_DIR = Path(__file__).resolve().parent / "data"
SCROLL_PAUSE_MS = 1800
DETAIL_EXTRA_WAIT_MS = 2500
GOTO_TIMEOUT_MS = 90_000
CHECKPOINT_EVERY = 100  # 每 N 筆 flush 一次 CSV,避免長時間跑掛掉全沒

def _now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize_course_url(href: str, base: str) -> str | None:
    if not href:
        return None
    full = urljoin(base, href)
    path = urlparse(full).path
    # 台大課程詳情路徑為 /courses/ 或 /zh-TW/courses/（舊版可能有 /course/）
    if "/courses/" not in path and "/course/" not in path:
        return None
    # 去掉 hash；保留 query 若站方需要（多數課程頁可省略）
    return full.split("#")[0]


def _extract_serial(text: str) -> str:
    m = re.search(r"流水號\s*[：:]\s*(\d{5})\b", text)
    if m:
        return m.group(1)
    m = re.search(r"\b流水號\s*(\d{5})\b", text)
    if m:
        return m.group(1)
    # 後備：獨立出現的 5 位數（避免誤抓學年等，要求前後非數字）
    m = re.search(r"(?<!\d)(\d{5})(?!\d)", text)
    return m.group(1) if m else ""


def _extract_credits(text: str) -> str:
    m = re.search(r"(\d+)\s*學分", text)
    return m.group(1) if m else ""


def _teacher_from_search_quick_href(href: str | None) -> str:
    """從「搜尋教師開設的課程」連結的 k= 參數還原姓名。"""
    if not href:
        return ""
    q = parse_qs(urlparse(href).query)
    raw = (q.get("k") or [""])[0]
    return unquote(raw).strip() if raw else ""


def _extract_teacher(text: str) -> str:
    for pat in (
        r"授課教師\s*[：:]\s*([^\n\r]+?)(?=\n|$)",
        r"教師\s*[：:]\s*([^\n\r]+?)(?=\n|$)",
        r"主責教師\s*[：:]\s*([^\n\r]+?)(?=\n|$)",
    ):
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()
    # 新版頁面常為「姓名」單獨一行，下一行為「…學院 …學系」
    m = re.search(r"[\r\n]+([\u4e00-\u9fff·．]{2,12})\s*[\r\n]+[^\r\n]{0,30}學院[^\r\n]*學系", text)
    if m:
        return m.group(1).strip()
    return ""


def _extract_enrollment_cap(text: str) -> str:
    """從「修課總人數」區塊以 Regex 取得修課人數上限。"""
    idx = text.find("修課總人數")
    window = text[idx : idx + 1200] if idx != -1 else text

    m = re.search(r"修課總人數\s*(\d+)\s*人", window)
    if m:
        return m.group(1)

    m = re.search(r"修課人數上限\s*[：:]\s*(\d+)", window)
    if m:
        return m.group(1)

    m = re.search(r"人數上限\s*[：:]\s*(\d+)", window)
    if m:
        return m.group(1)

    # 常見：已選/上限 如 22/30 → 分母為上限
    ratios = list(re.finditer(r"(\d+)\s*/\s*(\d+)", window))
    if ratios:
        # 取第一個合理比例（分母通常為上限）
        for r in ratios:
            a, b = int(r.group(1)), int(r.group(2))
            if 0 < b <= 2000 and a <= b:
                return str(b)

    m = re.search(r"上限\s*[：:]\s*(\d+)", window)
    if m:
        return m.group(1)

    return ""


def _meta_sidebar_slice(text: str) -> str:
    """左欄 metadata 大致區間：流水號之後到「備註」區塊之前。"""
    i = text.find("流水號")
    if i == -1:
        i = 0
    j = text.find("備註")
    if j != -1 and j > i:
        return text[i:j]
    j2 = text.find("課程概述")
    if j2 != -1 and j2 > i:
        return text[i:j2]
    return text[i:]


def _extract_course_code(text: str) -> str:
    m = re.search(r"課號\s*\n\s*([A-Za-z0-9]+)", text)
    if m:
        return m.group(1).strip()
    m = re.search(r"課號\s*[：:]\s*([A-Za-z0-9]+)", text)
    return m.group(1).strip() if m else ""


def _extract_course_uid(text: str) -> str:
    m = re.search(r"課程識別碼\s*\n\s*([0-9A-Za-z\s]+)", text)
    if m:
        return re.sub(r"\s+", " ", m.group(1).strip())
    m = re.search(r"課程識別碼\s*[：:]\s*([0-9A-Za-z\s]+)", text)
    return re.sub(r"\s+", " ", m.group(1).strip()) if m else ""


def _extract_req_type_and_dept(text: str) -> tuple[str, str]:
    """必帶／必修／選修 與 開課系所（學分下一組區塊）。"""
    m = re.search(
        r"(\d+)\s*學分\s*\n\s*(必帶|必修|選修)\s*\n\s*([^\n\r]+)",
        text,
    )
    if m:
        return m.group(2).strip(), m.group(3).strip()
    m = re.search(
        r"(必帶|必修|選修)\s*\n\s*([^\n\r]+)",
        _meta_sidebar_slice(text),
    )
    if m:
        dept = m.group(2).strip()
        if dept and not re.match(r"^\d+$", dept):
            return m.group(1).strip(), dept
    return "", ""


def _extract_schedule_time(text: str) -> str:
    # 1. label-based:有的頁面有「(上課)時間」label
    for pat in (
        r"時間\s*\n\s*([^\n\r]+)",
        r"上課時間\s*\n\s*([^\n\r]+)",
        r"上課時間\s*[：:]\s*([^\n\r]+)",
    ):
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()

    # 2. 找「整行只有 weekday + 數字/A-D + 分隔符」的純 schedule 行
    #    很多頁面這欄沒 label,就是一行 "一 3, 4 / 四 1" 這種樣子
    for line in text.split("\n"):
        line = line.strip()
        if not line or not re.match(r"^[一二三四五六日]", line):
            continue
        # 整行只能由 weekday、數字、A-D、空白、逗號、斜線、頓號等組成
        if not re.fullmatch(r"[一二三四五六日\d\sA-D,，/、·\-~～]+", line):
            continue
        if not re.search(r"\d|[A-D]", line):
            continue
        return line

    # 3. fallback (原版):「N 類」前一行如果是 weekday 開頭
    m = re.search(r"\n([一二三四五六日天][^\n\r]{0,48})\s*\n\s*\d+\s*類", text)
    if m:
        line = m.group(1).strip()
        if re.search(r"\d", line):
            return line
    return ""


def _extract_location(text: str) -> str:
    for pat in (
        r"地點\s*\n\s*([^\n\r]+)",
        r"教室\s*\n\s*([^\n\r]+)",
        r"地點\s*[：:]\s*([^\n\r]+)",
    ):
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()
    # 無標題時：若「節次」下一行為教室／館舍描述（再下一行才是「N 類」）
    m = re.search(
        r"\n[一二三四五六日天][^\n\r]+\n\s*([^\n\r]{2,50})\s*\n\s*\d+\s*類",
        text,
    )
    if m:
        cand = m.group(1).strip()
        if re.search(r"(館|教室|樓|室|院|區|棟|Building)", cand):
            return cand
    return ""


def _extract_signup_class(text: str) -> str:
    """加簽類別，例如「1 類」「2 類」。"""
    m = re.search(r"請洽系所辦\s*\n\s*(\d+)\s*類", text)
    if m:
        return f"{m.group(1)} 類"
    block = _meta_sidebar_slice(text)
    m = re.search(r"\n(\d+)\s*類\s*\n", block)
    if m:
        return f"{m.group(1)} 類"
    m = re.search(r"(\d+)\s*類\s*\n\s*[^\n]*加簽", text)
    if m:
        return f"{m.group(1)} 類"
    return ""


def _extract_instruction_language(text: str) -> str:
    m = re.search(r"(中文授課|英文授課|英語授課|全英語授課|其他語言)", text)
    if m:
        return m.group(1).strip()
    m = re.search(r"授課語言\s*\n\s*([^\n\r]+)", text)
    if m:
        return m.group(1).strip()
    return ""


def _slice_between_labels(text: str, start: str, end_candidates: tuple[str, ...]) -> str:
    i = text.find(start)
    if i == -1:
        return ""
    j = i + len(start)
    # 略過標題後的冒號空白
    while j < len(text) and text[j] in " ：:\t\n\r":
        j += 1
    end_pos = len(text)
    for cand in end_candidates:
        k = text.find(cand, j)
        if k != -1 and k < end_pos:
            end_pos = k
    return text[j:end_pos].strip()


def _overview_slice(text: str) -> str:
    """課程概述之後的長文區（課程目標、評量方式等多在此區）。"""
    i = text.find("課程概述")
    return text[i:] if i != -1 else text


def _extract_sections(full_text: str) -> dict[str, str]:
    """依台大課程網實際 DOM 順序，以標題文字切分欄位。"""
    overview = _overview_slice(full_text)

    # 備註：頁面上方「備註」→「修課限制／課程概述」
    remark = _slice_between_labels(
        full_text,
        "備註",
        ("修課限制", "本校選課狀況", "課程概述", "課程目標"),
    )

    # 課程概述：「課程概述」→「課程目標」（右欄介紹段落）
    course_intro = _slice_between_labels(overview, "課程概述", ("課程目標",))

    # 課程目標：「課程目標」→「課程要求」
    goals = _slice_between_labels(overview, "課程目標", ("課程要求", "預期每週課前", "評量方式"))

    # 課程要求：「課程要求」→「預期每週…／評量方式」
    requirements = _slice_between_labels(
        overview,
        "課程要求",
        (
            "預期每週課前或/與課後學習時數",
            "預期每週課前",
            "評量方式",
            "Office Hour",
        ),
    )

    # 預期學習時數：站方標題為「預期每週課前或/與課後學習時數」
    hours_label = "預期每週課前或/與課後學習時數"
    hours = ""
    if hours_label in overview:
        hours = _slice_between_labels(
            overview,
            hours_label,
            ("Office Hour", "指定閱讀", "參考書目", "評量方式"),
        )
    else:
        hours = _slice_between_labels(overview, "預期學習時數", ("Office Hour", "指定閱讀", "評量方式"))

    # 評量方式：→「補課資訊／課程進度／針對學生」
    eval_text = _slice_between_labels(
        overview,
        "評量方式",
        ("補課資訊", "課程進度", "針對學生困難", "先修科目", "教材"),
    )

    return {
        "課程概述": course_intro,
        "課程目標": goals,
        "課程要求": requirements,
        "評量方式": eval_text,
        "備註": remark,
        "預期學習時數": hours,
    }


async def collect_detail_urls(page: Page, need: int, start_url: str) -> list[str]:
    print(f"[{_now_ts()}] 開搜尋頁 {start_url} ...")
    await page.goto(start_url, wait_until="networkidle", timeout=GOTO_TIMEOUT_MS)
    await page.wait_for_timeout(2000)
    base_url = page.url
    try:
        await page.wait_for_selector('a[href*="/courses/"]', timeout=60_000)
    except Exception:
        pass
    print(f"[{_now_ts()}] 搜尋頁已載入,開始 scroll 收集 URL...")

    seen: dict[str, None] = {}
    stale_rounds = 0
    scroll_count = 0
    last_logged = 0

    while len(seen) < need and stale_rounds < 25:
        before = len(seen)
        # 一次取得目前 DOM 內所有 href，避免虛擬列表下對 nth(i).get_attribute 逐一等待而逾時
        hrefs = await page.locator('a[href*="/courses/"]').evaluate_all(
            "els => els.map(e => e.getAttribute('href'))"
        )
        for href in hrefs:
            u = _normalize_course_url(href or "", base_url)
            if u:
                seen.setdefault(u, None)

        if len(seen) >= need:
            break
        if len(seen) == before:
            stale_rounds += 1
        else:
            stale_rounds = 0

        await page.mouse.wheel(0, 6000)
        await page.wait_for_timeout(SCROLL_PAUSE_MS)
        scroll_count += 1

        # 每 10 次 scroll 或新增 ≥500 個 URL 就 log 一次進度
        if scroll_count % 10 == 0 or len(seen) - last_logged >= 500:
            print(f"[{_now_ts()}]   scroll #{scroll_count}: 已收集 {len(seen)}/{need} 個 URL (stale={stale_rounds})")
            last_logged = len(seen)

    print(f"[{_now_ts()}] URL 收集完成,共 {len(seen)} 個 (scroll {scroll_count} 次)")
    return list(seen.keys())[:need]


async def scrape_one_course(page: Page, url: str) -> dict[str, Any]:
    await page.goto(url, wait_until="networkidle", timeout=GOTO_TIMEOUT_MS)
    await page.wait_for_timeout(DETAIL_EXTRA_WAIT_MS)

    body_text = await page.locator("body").inner_text()
    title = await page.title()

    serial = _extract_serial(body_text)
    credits = _extract_credits(body_text)
    teacher = _extract_teacher(body_text)
    if not teacher:
        tloc = page.locator('a[href*="search/quick"][href*="k="]').filter(
            has_text=re.compile("搜尋教師")
        )
        if await tloc.count():
            teacher = _teacher_from_search_quick_href(await tloc.first.get_attribute("href"))
    cap = _extract_enrollment_cap(body_text)
    sections = _extract_sections(body_text)

    course_code = _extract_course_code(body_text)
    course_uid = _extract_course_uid(body_text)
    req_type, host_dept = _extract_req_type_and_dept(body_text)
    sched_time = _extract_schedule_time(body_text)
    location = _extract_location(body_text)
    signup_class = _extract_signup_class(body_text)
    language = _extract_instruction_language(body_text)

    # 課名：優先 title「xxx｜」或「xxx - 」；否則第一個 h1
    course_name = ""
    m = re.match(r"^(.+?)\s*[｜|]\s*", title)
    if m:
        course_name = m.group(1).strip()
    if not course_name and " - " in title:
        course_name = title.split(" - ")[0].strip()
    if not course_name:
        h1 = page.locator("h1").first
        if await h1.count():
            course_name = (await h1.inner_text()).strip()
    if not course_name:
        course_name = title.strip()

    return {
        "課名": course_name,
        "教師": teacher,
        "流水號": serial,
        "課號": course_code,
        "課程識別碼": course_uid,
        "必選修": req_type,
        "開課系所": host_dept,
        "上課時間": sched_time,
        "上課地點": location,
        "加簽類別": signup_class,
        "授課語言": language,
        "學分": credits,
        "修課人數上限": cap,
        "課程概述": sections.get("課程概述", ""),
        "課程目標": sections.get("課程目標", ""),
        "課程要求": sections.get("課程要求", ""),
        "評量方式": sections.get("評量方式", ""),
        "備註": sections.get("備註", ""),
        "預期學習時數": sections.get("預期學習時數", ""),
        "詳情頁URL": url,
    }


OUTPUT_COLS = [
    "課名", "教師", "流水號", "課號", "課程識別碼", "必選修",
    "開課系所", "上課時間", "上課地點", "加簽類別", "授課語言",
    "學分", "修課人數上限", "課程概述", "課程目標", "課程要求",
    "評量方式", "備註", "預期學習時數", "詳情頁URL",
]


def _load_done_urls(csv_path: Path) -> set[str]:
    """既有 CSV 內已抓過的 detail URL,supports resume。"""
    if not csv_path.exists():
        return set()
    try:
        df = pd.read_csv(csv_path, dtype=str, usecols=["詳情頁URL"]).fillna("")
        return {u for u in df["詳情頁URL"] if u}
    except Exception:
        return set()


def _flush_rows(rows: list[dict], csv_path: Path) -> None:
    """append-write 新 rows 進 csv;不存在則寫 header。"""
    if not rows:
        return
    df = pd.DataFrame(rows)
    df = df[[c for c in OUTPUT_COLS if c in df.columns]]
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    header = not csv_path.exists()
    df.to_csv(csv_path, mode="a", index=False, header=header, encoding="utf-8-sig")


async def run(
    semester: str | None,
    output_csv: Path,
    max_count: int,
    headless: bool,
    slow_mo: int,
) -> None:
    if semester:
        start_url = SEARCH_URL_TEMPLATE.format(semester=semester)
    else:
        start_url = DEFAULT_SEARCH_URL
    print(f"[{_now_ts()}] start_url = {start_url}")
    print(f"[{_now_ts()}] output_csv = {output_csv}")
    print(f"[{_now_ts()}] headless = {headless}, slow_mo = {slow_mo}ms")

    done_urls = _load_done_urls(output_csv)
    if done_urls:
        print(f"[{_now_ts()}] resume: 既有 {len(done_urls)} 筆,會跳過")

    buffer: list[dict[str, Any]] = []
    total_written = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, slow_mo=slow_mo)
        context = await browser.new_context(locale="zh-TW")
        page = await context.new_page()

        urls = await collect_detail_urls(page, max_count, start_url)

        if not urls:
            print(f"[{_now_ts()}] 未取得任何課程詳情連結(/courses/),請確認搜尋頁是否已載入列表。")
            await browser.close()
            return

        # 過濾掉已抓過的
        urls = [u for u in urls if u not in done_urls]
        total = len(urls)
        print(f"[{_now_ts()}] 待抓 {total} 筆 (檢索到 {total + len(done_urls)} 個 URL,跳過 {len(done_urls)} 個)")

        for idx, u in enumerate(urls, start=1):
            try:
                data = await scrape_one_course(page, u)
                buffer.append(data)
                name = data.get("課名", "")
                sn = data.get("流水號", "")
                print(f"[{_now_ts()}] [{idx}/{total}] 成功抓取:{name} ({sn})")
            except Exception as e:
                print(f"[{_now_ts()}] [{idx}/{total}] 跳過(錯誤):{u} — {e!s}")
                continue

            # 每 CHECKPOINT_EVERY 筆 flush 一次,長時間跑掛掉不會全沒
            if len(buffer) >= CHECKPOINT_EVERY:
                _flush_rows(buffer, output_csv)
                total_written += len(buffer)
                print(f"[{_now_ts()}] ★ checkpoint: 已寫入 {output_csv.name} (累計 {total_written} 筆)")
                buffer.clear()

        await browser.close()

    # 收尾 flush
    if buffer:
        _flush_rows(buffer, output_csv)
        total_written += len(buffer)

    print(f"[{_now_ts()}] 完成。本次新增 {total_written} 筆 → {output_csv}")


def _default_output_for(semester: str | None) -> Path:
    if semester:
        # 把 '114-1' 變成檔名安全的後綴
        suffix = semester.replace("/", "_")
        return _DATA_DIR / f"ntu_detailed_data_{suffix}.csv"
    return _DATA_DIR / "ntu_detailed_data.csv"


def main() -> None:
    ap = argparse.ArgumentParser(description="台大課程網爬蟲")
    ap.add_argument("--semester", default=None,
                    help="學年期 (e.g. 114-1, 114-2);省略 = 站方預設(當前學期)")
    ap.add_argument("--output", type=Path, default=None,
                    help="輸出 CSV 路徑;省略 = ntu_detailed_data[_{semester}].csv")
    ap.add_argument("--max-count", type=int, default=DEFAULT_MAX_COUNT,
                    help=f"最多抓取筆數 (預設 {DEFAULT_MAX_COUNT})")
    ap.add_argument("--show-browser", action="store_true",
                    help="開瀏覽器視窗 (預設 headless,加這個 flag 才看得到)")
    ap.add_argument("--slow-mo", type=int, default=0,
                    help="Playwright slow_mo (ms),預設 0 (最快);debug 時可設 200")
    args = ap.parse_args()

    output = args.output or _default_output_for(args.semester)
    asyncio.run(run(
        args.semester, output, args.max_count,
        headless=not args.show_browser, slow_mo=args.slow_mo,
    ))


if __name__ == "__main__":
    main()
