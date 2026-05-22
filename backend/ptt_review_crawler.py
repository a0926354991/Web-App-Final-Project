"""
PTT NTUcourse 板評價爬蟲。

策略：
1. 從 ntu_detailed_data.csv 讀出 (課名, 教師, 課號)。
2. 以「教師名」為 query 去 PTT NTUcourse 搜尋（一位教師通常開多門課，
   一次搜尋可同時涵蓋多門課，比 per-course 搜尋省一個量級的 request）。
3. 對搜尋結果裡的每篇貼文，抓 metadata + 內文。
4. 比對該教師名下哪些課名出現在標題或內文 → 寫一列到 ntu_reviews_raw.csv。
5. 重跑時依輸出檔已存在的 (post_url, course_id) 去重，可斷點續跑。

只用 requests + BeautifulSoup（PTT 是純 HTML，無需 JS）。
"""

from __future__ import annotations

import argparse
import csv
import logging
import random
import re
import time
from pathlib import Path
from urllib.parse import quote_plus, urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

PTT_BASE = "https://www.ptt.cc"
BOARD_SEARCH = PTT_BASE + "/bbs/NTUcourse/search"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
}
REQUEST_TIMEOUT = 20
SLEEP_RANGE = (0.6, 1.2)  # 友善延遲，避免被擋

DATA_DIR = Path(__file__).resolve().parent / "data"
INPUT_CSV = DATA_DIR / "ntu_detailed_data.csv"
EXTRA_INPUT_DEFAULT = DATA_DIR / "ntu_detailed_data_114-1.csv"
OUTPUT_CSV = DATA_DIR / "ntu_reviews_raw.csv"

OUTPUT_COLUMNS = [
    "course_id",      # 課號
    "course_name",    # 課名
    "teacher",        # 教師
    "post_url",
    "post_title",
    "post_author",
    "post_date",
    "content",
    "source",         # 固定 "ptt/NTUcourse"
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ptt")


# ----------------------------- HTTP helpers -----------------------------


def _polite_sleep() -> None:
    time.sleep(random.uniform(*SLEEP_RANGE))


def _get(session: requests.Session, url: str, *, retries: int = 3) -> str | None:
    for attempt in range(1, retries + 1):
        try:
            r = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            log.warning("GET %s 失敗 (%d/%d): %s", url, attempt, retries, e)
            time.sleep(2 * attempt)
    return None


# ----------------------------- Search & post parsing -----------------------------


def search_posts(session: requests.Session, query: str, max_pages: int = 5) -> list[tuple[str, str]]:
    """搜尋 NTUcourse 板，回傳 [(post_url, post_title), ...]（已去重保序）。"""
    results: list[tuple[str, str]] = []
    seen: set[str] = set()
    for page in range(1, max_pages + 1):
        url = f"{BOARD_SEARCH}?q={quote_plus(query)}&page={page}"
        html = _get(session, url)
        _polite_sleep()
        if not html:
            break
        soup = BeautifulSoup(html, "html.parser")
        entries = soup.select("div.r-ent div.title a[href]")
        if not entries:
            break
        for a in entries:
            href = a.get("href") or ""
            title = a.get_text(strip=True)
            if not href or href in seen:
                continue
            seen.add(href)
            results.append((urljoin(PTT_BASE, href), title))
        if not soup.select_one("a.btn.wide:-soup-contains('上頁')"):
            break
    return results


# 標題若帶這些 tag，視為「值得抓」(評價/心得/問題類)；其他 tag 多半是徵人/公告/閒聊。
_RELEVANT_TAG_RE = re.compile(
    r"\[(評價|心得|問題|課程|加簽|討論|分享|News|求救|徵詢|請益|筆記)\]"
)


def is_relevant_title(title: str, course_names: list[str]) -> bool:
    """貼文標題是否值得進一步抓內文。

    判準：(a) 標題帶白名單 tag，或 (b) 標題已包含其中一個課名。
    其他（[徵人]/[公告]/Re: 無 tag…）一律跳過。
    """
    if _RELEVANT_TAG_RE.search(title):
        return True
    norm = _normalize(title)
    for cname in course_names:
        n = _normalize(cname)
        if len(n) >= 2 and n in norm:
            return True
    return False


_META_KEYS = {"作者": "author", "標題": "title", "時間": "date"}


def parse_post(html: str) -> dict | None:
    """解析 PTT 貼文 HTML → {title, author, date, content}。"""
    soup = BeautifulSoup(html, "html.parser")
    main = soup.select_one("#main-content")
    if not main:
        return None

    meta: dict[str, str] = {}
    for row in main.select("div.article-metaline, div.article-metaline-right"):
        tag = row.select_one(".article-meta-tag")
        val = row.select_one(".article-meta-value")
        if tag and val and tag.get_text(strip=True) in _META_KEYS:
            meta[_META_KEYS[tag.get_text(strip=True)]] = val.get_text(strip=True)
        row.decompose()

    # 移除推文、簽名檔以下、引用標頭
    for el in main.select("div.push"):
        el.decompose()

    text = main.get_text("\n", strip=False)
    # 砍簽名檔（PTT 慣例：「--」單獨一行之後是簽名）
    text = re.split(r"\n--\n", text, maxsplit=1)[0]
    # 砍 ※ 發信站 / 文章網址等系統訊息
    text = re.sub(r"※ 發信站:.*", "", text)
    text = re.sub(r"※ 文章網址:.*", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    return {
        "title": meta.get("title", ""),
        "author": meta.get("author", ""),
        "date": meta.get("date", ""),
        "content": text,
    }


# ----------------------------- Matching -----------------------------


def _normalize(s: str) -> str:
    """簡化比對：移除空白與常見全形括號內附註，方便子字串匹配。"""
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[（(][^）)]*[)）]", "", s)
    return s


def match_courses(post_title: str, post_content: str, courses: list[dict]) -> list[dict]:
    """回傳出現在貼文裡的課程列表（限於該教師目前的開課）。"""
    haystack = _normalize(post_title + "\n" + post_content)
    matched = []
    for c in courses:
        needle = _normalize(c["course_name"])
        if len(needle) >= 2 and needle in haystack:
            matched.append(c)
    return matched


def load_full_catalog(detail_paths: list[Path]) -> tuple[list[str], dict[str, dict]]:
    """載入全 NTU 課程目錄（可合併多學期），回傳 (依長度遞減排序的 normalized 課名, 課名 → 課程 dict)。"""
    name_to_course: dict[str, dict] = {}
    for detail_path in detail_paths:
        if not detail_path.exists():
            continue
        df = pd.read_csv(detail_path, dtype=str).fillna("")
        for _, r in df.iterrows():
            name = r["課名"].strip()
            cid = r["課號"].strip()
            if not name or not cid:
                continue
            norm = _normalize(name)
            if len(norm) < 3:
                continue  # 太短（民法/數學）模糊比對風險太高
            if norm not in name_to_course:
                name_to_course[norm] = {"course_name": name, "course_id": cid}
    names_desc = sorted(name_to_course.keys(), key=len, reverse=True)
    return names_desc, name_to_course


def extract_catalog_courses(
    text: str,
    names_desc: list[str],
    name_to_course: dict[str, dict],
) -> list[dict]:
    """從文字（通常是標題）抽出全目錄裡有的課名，採 longest-match、避免 sub-match 重複。"""
    norm = _normalize(text)
    found: list[tuple[str, dict]] = []
    for nname in names_desc:
        if nname not in norm:
            continue
        # 已經被更長的匹配涵蓋 → 跳過（例如 "資料結構" 是 "資料結構與演算法" 的子字串）
        if any(nname in f_name for f_name, _ in found):
            continue
        found.append((nname, name_to_course[nname]))
    return [c for _, c in found]


# ----------------------------- IO -----------------------------


_CJK_NAME_RE = re.compile(r"[一-鿿·．]{2,5}")


def _clean_teacher(raw: str) -> list[str]:
    """從 CSV 教師欄抽出一到多個合法人名。

    範例：
      "郭琬媛。與黃玉萍合授" → ["郭琬媛", "黃玉萍"]
      "林軒田" → ["林軒田"]
      "20" → []
      "彭文孝、陳永昇、謝秉均。同步遠距課程。" → ["彭文孝","陳永昇","謝秉均"]
    """
    if not raw:
        return []
    # 切到第一個句號前（後面通常是時間/備註）
    head = re.split(r"[。．]", raw, maxsplit=1)[0]
    parts = re.split(r"[,，、/與及和]", head)
    out: list[str] = []
    for p in parts:
        p = p.strip()
        m = _CJK_NAME_RE.match(p)
        if m and m.group() == p:
            out.append(p)
    return out


def load_courses(paths: list[Path]) -> pd.DataFrame:
    rows = []
    for path in paths:
        if not path.exists():
            log.warning("跳過不存在的目錄檔: %s", path)
            continue
        log.info("讀 %s", path.name)
        df = pd.read_csv(path, dtype=str).fillna("")
        df = df[["課名", "教師", "課號"]].rename(
            columns={"課名": "course_name", "教師": "teacher", "課號": "course_id"}
        )
        for _, r in df.iterrows():
            cname = r["course_name"].strip()
            cid = r["course_id"].strip()
            if not cname:
                continue
            for t in _clean_teacher(r["teacher"]):
                rows.append({"course_name": cname, "teacher": t, "course_id": cid})
    return pd.DataFrame(rows).drop_duplicates(subset=["course_name", "teacher", "course_id"])


def load_seen_keys(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    try:
        seen = pd.read_csv(path, usecols=["post_url", "course_id"], dtype=str).fillna("")
        return set(zip(seen["post_url"], seen["course_id"]))
    except Exception as e:
        log.warning("讀取既有輸出失敗，將從頭寫: %s", e)
        return set()


def teachers_from_detail(path: Path) -> set[str]:
    """從一個 detailed CSV 抽出所有 teachers（用於 --skip-teachers-from）。"""
    out: set[str] = set()
    if not path.exists():
        return out
    df = pd.read_csv(path, dtype=str).fillna("")
    for raw in df["教師"]:
        for t in _clean_teacher(raw):
            out.add(t)
    return out


def open_writer(path: Path):
    new_file = not path.exists()
    f = path.open("a", encoding="utf-8", newline="")
    w = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
    if new_file:
        w.writeheader()
        f.flush()
    return f, w


# ----------------------------- Main -----------------------------


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-teachers", type=int, default=0,
                    help="只處理前 N 位教師（測試用，0 = 全部）")
    ap.add_argument("--sample", type=int, default=0,
                    help="隨機抽樣 N 位教師（測試用，會覆蓋 --limit-teachers）")
    ap.add_argument("--seed", type=int, default=42, help="隨機抽樣種子")
    ap.add_argument("--teacher", type=str, default="",
                    help="只處理指定教師（測試用，會覆蓋 --limit-teachers/--sample）")
    ap.add_argument("--max-pages", type=int, default=5,
                    help="每位教師搜尋頁數上限")
    ap.add_argument("--input", action="append", type=Path, default=None,
                    help="課程目錄 CSV (可重複指定多個學期);省略 = 預設 114-2 + 114-1")
    ap.add_argument("--skip-teachers-from", action="append", type=Path, default=None,
                    help="跳過這些 CSV 裡已有的教師（用於只跑新學期多出來的教師）")
    ap.add_argument("--output", type=Path, default=OUTPUT_CSV)
    args = ap.parse_args()

    input_paths = args.input or [INPUT_CSV, EXTRA_INPUT_DEFAULT]
    log.info("讀取課程表 (%d 個): %s", len(input_paths), [p.name for p in input_paths])
    courses_df = load_courses(input_paths)
    log.info("合併後 %d 筆 (課,師) 組合 / %d 位教師",
             len(courses_df), courses_df["teacher"].nunique())

    # 全 NTU 課程目錄（用於從標題抽取教師「現在沒在開」的舊課）
    cat_names_desc, cat_name_to_course = load_full_catalog(input_paths)
    log.info("全目錄載入：%d 個獨立課名（用於標題抽取）", len(cat_name_to_course))

    seen = load_seen_keys(args.output)
    log.info("既有輸出已寫入 %d 筆，將略過", len(seen))

    skip_teachers: set[str] = set()
    for p in args.skip_teachers_from or []:
        s = teachers_from_detail(p)
        log.info("--skip-teachers-from %s: %d 位", p.name, len(s))
        skip_teachers |= s

    if args.teacher:
        teachers = [args.teacher]
    else:
        teachers = sorted(courses_df["teacher"].unique())
        if skip_teachers:
            before = len(teachers)
            teachers = [t for t in teachers if t not in skip_teachers]
            log.info("跳過 %d 位已搜尋過的教師 → 剩 %d 位",
                     before - len(teachers), len(teachers))
        if args.sample:
            rng = random.Random(args.seed)
            teachers = rng.sample(teachers, min(args.sample, len(teachers)))
        elif args.limit_teachers:
            teachers = teachers[: args.limit_teachers]

    f, writer = open_writer(args.output)
    session = requests.Session()
    post_cache: dict[str, dict | None] = {}  # url -> 解析後 post（跨教師重用，None = 抓失敗）
    total_rows = 0
    stats = {"searched": 0, "filtered_skipped": 0, "fetched": 0, "cache_hits": 0}

    try:
        for i, teacher in enumerate(teachers, 1):
            tcourses = courses_df[courses_df["teacher"] == teacher].to_dict("records")
            cnames = [c["course_name"] for c in tcourses]

            try:
                results = search_posts(session, teacher, max_pages=args.max_pages)
            except Exception as e:
                log.error("搜尋 %s 出錯: %s", teacher, e)
                continue
            stats["searched"] += len(results)
            if not results:
                continue

            # 標題預濾：只留下 tag 或標題含課名的
            relevant = [(u, t) for u, t in results if is_relevant_title(t, cnames)]
            stats["filtered_skipped"] += len(results) - len(relevant)
            log.info("[%d/%d] %s（%d 門）: 搜到 %d / 過濾後 %d",
                     i, len(teachers), teacher, len(tcourses), len(results), len(relevant))
            if not relevant:
                continue

            for url, _title in relevant:
                if url in post_cache:
                    post = post_cache[url]
                    stats["cache_hits"] += 1
                else:
                    html = _get(session, url)
                    _polite_sleep()
                    post = parse_post(html) if html else None
                    post_cache[url] = post
                    stats["fetched"] += 1

                if not post:
                    continue

                # 合併兩個 matcher：(a) 該教師目前的課全文比對 (b) 標題抽取對全目錄
                merged: dict[str, dict] = {}
                for c in match_courses(post["title"], post["content"], tcourses):
                    merged[c["course_id"]] = c
                for c in extract_catalog_courses(post["title"], cat_names_desc, cat_name_to_course):
                    merged.setdefault(c["course_id"], c)

                for c in merged.values():
                    key = (url, c["course_id"])
                    if key in seen:
                        continue
                    writer.writerow({
                        "course_id": c["course_id"],
                        "course_name": c["course_name"],
                        "teacher": teacher,
                        "post_url": url,
                        "post_title": post["title"],
                        "post_author": post["author"],
                        "post_date": post["date"],
                        "content": post["content"],
                        "source": "ptt/NTUcourse",
                    })
                    seen.add(key)
                    total_rows += 1
                f.flush()
            if i % 25 == 0:
                log.info("  進度: 累積寫入 %d 列 / 搜尋 %d / 過濾 %d / 抓 %d / 命中 cache %d",
                         total_rows, stats["searched"], stats["filtered_skipped"],
                         stats["fetched"], stats["cache_hits"])
    finally:
        f.close()
        log.info("結束。本次新增 %d 列 → %s", total_rows, args.output)


if __name__ == "__main__":
    main()
