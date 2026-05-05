"""
對既有 ntu_reviews_raw.csv 重跑放寬版 matching，撈出「同篇貼文還能對到該教師其他課」的新匹配。

策略（保守）：
1. 既有 CSV 的 row 全保留。
2. 對每個 (post_url, teacher) 組合，把貼文內容跟「該教師所有課」做：
   (a) 原版 exact 比對 — 重複既有匹配，跳過
   (b) suffix-stripped 比對（甲乙丙丁/一二三/(上)/I-V/digit 等尾綴）
       — 只有在該教師範圍內 stripped 形唯一時才採用，避免「服務學習甲」「服務學習一」誤匹配同一句「服務學習」
3. 把新匹配寫成新 row 追加進 CSV。

不重抓 PTT，純本地計算。對撈不到 post 完全沒幫助（需要重 crawl）。
"""

from __future__ import annotations

import collections
import csv
import logging
import re
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"
INPUT_RAW = DATA_DIR / "ntu_reviews_raw.csv"
INPUT_DETAIL = DATA_DIR / "ntu_detailed_data.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("rematch")


_SUFFIX_STRIP = re.compile(
    r"(?:"
    r"[甲乙丙丁戊][一二三四五六七八九]?|"  # 甲、乙一、丙二
    r"[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|"                # 全形羅馬數字
    r"I{1,3}V?|VI{0,3}|"                  # 半形 I/II/III/IV/VI etc.
    r"[(（][一二三四五六七八九上下前後新舊][)）]|"  # (一)(下)(前) 之類
    r"\d+|"                              # 純數字
    r"[一二三四五六七八九]"               # 純 CJK 數字
    r")$"
)


def _normalize(s: str) -> str:
    s = re.sub(r"\s+", "", s or "")
    s = re.sub(r"[（(][^）)]*[)）]", "", s)
    return s


def _strip_suffix(name: str) -> str:
    return _SUFFIX_STRIP.sub("", name)


def find_new_matches(
    haystack: str,
    teacher_courses: list[dict],
    already_matched_ids: set[str],
) -> list[dict]:
    """放寬比對，回傳「不在 already_matched_ids 裡」的新匹配課程。"""
    # 在該教師範圍內計算 suffix-stripped 形的多樣性
    by_stripped: dict[str, list[dict]] = collections.defaultdict(list)
    for c in teacher_courses:
        norm = _normalize(c["course_name"])
        stripped = _strip_suffix(norm)
        if stripped != norm and len(stripped) >= 3:
            by_stripped[stripped].append(c)

    new = []
    for stripped, group in by_stripped.items():
        if len(group) > 1:
            continue  # 有兄弟課 → 模糊，跳過
        c = group[0]
        if c["course_id"] in already_matched_ids:
            continue
        if stripped in haystack:
            new.append({"course_name_form": stripped, **c})
    return new


def load_teacher_to_courses(detail_path: Path) -> dict[str, list[dict]]:
    """每位教師 → 該教師的所有課程列表。"""
    df = pd.read_csv(detail_path, dtype=str).fillna("")
    out: dict[str, list[dict]] = collections.defaultdict(list)
    for _, r in df.iterrows():
        cname = r["課名"].strip()
        cid = r["課號"].strip()
        if not cname:
            continue
        # 教師欄可能含多人或附註，重用 ptt_review_crawler 的清理邏輯（簡化版）
        head = re.split(r"[。．]", r["教師"], maxsplit=1)[0]
        for raw in re.split(r"[,，、/與及和]", head):
            t = raw.strip()
            if re.fullmatch(r"[一-鿿·．]{2,5}", t):
                out[t].append({"course_name": cname, "course_id": cid})
    return out


def main() -> None:
    log.info("讀取 raw reviews...")
    raw = pd.read_csv(INPUT_RAW, dtype=str).fillna("")
    log.info("既有 row 數: %d", len(raw))

    log.info("讀取 detailed → 教師 → 課程映射...")
    teacher_courses = load_teacher_to_courses(INPUT_DETAIL)

    # 既有 (post_url, course_id) 集合，用於去重
    seen_keys = set(zip(raw["post_url"], raw["course_id"]))

    new_rows = []
    # 依 (post_url, teacher) groupby，每組處理一次
    grouped = raw.groupby(["post_url", "teacher"], sort=False)
    log.info("共 %d 個 (post_url, teacher) 組合要 rematch", len(grouped))

    for (post_url, teacher), grp in grouped:
        teacher_all = teacher_courses.get(teacher, [])
        if len(teacher_all) <= 1:
            continue  # 該教師只有一門課就沒得撿
        # 已經匹配的課程
        already = set(grp["course_id"])
        # 取一個 row 拿 content/title/etc
        any_row = grp.iloc[0]
        content = any_row["content"]
        title = any_row["post_title"]
        haystack = _normalize(title + "\n" + content)

        new_matches = find_new_matches(haystack, teacher_all, already)
        for m in new_matches:
            key = (post_url, m["course_id"])
            if key in seen_keys:
                continue
            new_rows.append({
                "course_id": m["course_id"],
                "course_name": m["course_name"],
                "teacher": teacher,
                "post_url": post_url,
                "post_title": title,
                "post_author": any_row["post_author"],
                "post_date": any_row["post_date"],
                "content": content,
                "source": any_row["source"],
            })
            seen_keys.add(key)

    log.info("新增匹配: %d row", len(new_rows))
    if not new_rows:
        log.info("沒有新匹配 — 結束")
        return

    # append 到既有 CSV
    with INPUT_RAW.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "course_id","course_name","teacher","post_url",
            "post_title","post_author","post_date","content","source",
        ])
        w.writerows(new_rows)
    log.info("已追加到 %s", INPUT_RAW)


if __name__ == "__main__":
    main()
