"""
把 v2 爬蟲產出的 CSV merge 進現有 app.db,並清理已知髒資料。

背景:
- ntu_list_data_{sem}_v2.csv  ← course_list_crawler.py 產出 (含正確的上課時間/地點)
- ntu_detail_{sem}_v2.csv      ← detail_crawler_v2.py 產出 (補課程概述/目標/要求/評量/系所)

設計原則 (跟手動 merge 一致,固化成可重跑腳本):
- 用 (semester, serial_no) 當 key。
- list merge: 時間/地點「v2 有值就覆蓋」(v2 地點品質優於舊資料);空值不覆蓋,不清掉舊有。
- detail merge: 長文「只填 DB 為空的欄位」(--fill-empty,預設);
  加 --overwrite 才連已有長文一起覆蓋。
- clean: 修正課名髒值 (｜臺大課程網 → 用 v2 列表的正確課名);
  切掉 location 尾部的「與...合授」雜訊,只留地點。
- 每次動 DB 前自動備份 app.db。

用法:
    # merge 列表資料 (時間/地點)
    python backend/scripts/merge_crawl_data.py list --semester 114-2
    # merge 詳情長文 (只填空)
    python backend/scripts/merge_crawl_data.py detail --semester 114-2
    # 清理髒資料
    python backend/scripts/merge_crawl_data.py clean --semester 114-2
    # 一次跑全部 (list → detail → clean)
    python backend/scripts/merge_crawl_data.py all --semester 114-2
"""

from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "app.db"


def _backup_db() -> Path:
    dst = DB_PATH.with_name(f"app.db.bak.{datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(DB_PATH, dst)
    print(f"[backup] {DB_PATH.name} → {dst.name}")
    return dst


def _list_csv(sem: str) -> Path:
    return DATA_DIR / f"ntu_list_data_{sem}_v2.csv"


def _detail_csv(sem: str) -> Path:
    return DATA_DIR / f"ntu_detail_{sem}_v2.csv"


def merge_list(conn: sqlite3.Connection, sem: str) -> None:
    """v2 列表 → 覆蓋時間/地點 (空值不覆蓋);列表頁新課則 INSERT。"""
    path = _list_csv(sem)
    if not path.exists():
        print(f"[list] 找不到 {path.name},跳過")
        return
    df = pd.read_csv(path, dtype=str).fillna("")
    existing = {r[0] for r in conn.execute("SELECT serial_no FROM courses WHERE semester=?", (sem,))}

    upd_t = upd_l = ins = 0
    for _, r in df.iterrows():
        sn = r["流水號"].strip()
        if not sn:
            continue
        sched, loc = r["上課時間"].strip(), r["上課地點"].strip()
        if sn in existing:
            sets, args = [], []
            if sched:
                sets.append("schedule_time=?"); args.append(sched); upd_t += 1
            if loc:
                sets.append("location=?"); args.append(loc); upd_l += 1
            if sets:
                conn.execute(f"UPDATE courses SET {','.join(sets)} WHERE semester=? AND serial_no=?",
                             [*args, sem, sn])
        else:
            conn.execute(
                """INSERT INTO courses (semester,serial_no,course_code,course_identifier,
                   course_name,teacher,req_type,department,schedule_time,location,signup_class,credits)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (sem, sn, r["課號"].strip(), r["課程識別碼"].strip(), r["課名"].strip(),
                 r["教師"].strip(), r["必選修"].strip(), r["開課系所"].strip(),
                 sched, loc, r["加簽類別"].strip(), r["學分"].strip()))
            ins += 1
    conn.commit()
    print(f"[list] {sem}: 補時間 {upd_t:,} / 補地點 {upd_l:,} / 新課 INSERT {ins:,}")


def merge_detail(conn: sqlite3.Connection, sem: str, overwrite: bool) -> None:
    """v2 詳情 → 填長文。預設只填 DB 為空的欄位;--overwrite 才覆蓋既有。"""
    path = _detail_csv(sem)
    if not path.exists():
        print(f"[detail] 找不到 {path.name},跳過")
        return
    df = pd.read_csv(path, dtype=str).fillna("")
    # CSV 欄 → DB 欄
    field_map = {
        "課程概述": "overview", "課程目標": "objectives", "課程要求": "requirements",
        "評量方式": "grading", "預期學習時數": "expected_hours", "開課系所": "department",
    }
    counts = {db: 0 for db in field_map.values()}
    for _, r in df.iterrows():
        sn = r["流水號"].strip()
        if not sn:
            continue
        cur = conn.execute(
            "SELECT overview,objectives,requirements,grading,expected_hours,department "
            "FROM courses WHERE semester=? AND serial_no=?", (sem, sn)).fetchone()
        if cur is None:
            continue
        existing_vals = dict(zip(
            ["overview", "objectives", "requirements", "grading", "expected_hours", "department"], cur))
        sets, args = [], []
        for zh, db in field_map.items():
            val = r.get(zh, "").strip()
            if not val:
                continue
            if overwrite or not (existing_vals[db] or "").strip():
                sets.append(f"{db}=?"); args.append(val); counts[db] += 1
        if sets:
            conn.execute(f"UPDATE courses SET {','.join(sets)} WHERE semester=? AND serial_no=?",
                         [*args, sem, sn])
    conn.commit()
    mode = "覆蓋" if overwrite else "只填空"
    print(f"[detail] {sem} ({mode}): " + " / ".join(f"{db}+{n:,}" for db, n in counts.items()))
    if any(counts[f] for f in ("overview", "objectives", "grading")):
        print("[detail] ⚠ 補了課程長文 → 請重啟 API server,讓興趣 TF-IDF 索引重建 "
              "(init_indices 啟動時建一次就快取;見 recommendations.invalidate_indices)")


def clean(conn: sqlite3.Connection, sem: str) -> None:
    """清理髒資料: 課名｜臺大課程網 用 v2 列表課名修正; location 切掉「與...合授」雜訊。"""
    # 1. 課名髒值
    path = _list_csv(sem)
    fixed_name = 0
    if path.exists():
        df = pd.read_csv(path, dtype=str).fillna("")
        name_map = dict(zip(df["流水號"].str.strip(), df["課名"].str.strip()))
        bad = conn.execute(
            "SELECT serial_no FROM courses WHERE semester=? AND "
            "(course_name LIKE '%臺大課程網%' OR TRIM(course_name)='')", (sem,)).fetchall()
        for (sn,) in bad:
            good = name_map.get(sn, "")
            if good and "臺大課程網" not in good:
                conn.execute("UPDATE courses SET course_name=? WHERE semester=? AND serial_no=?",
                             (good, sem, sn))
                fixed_name += 1

    # 2. location 尾部「與...合授」/「，與...」雜訊切掉,只留地點
    fixed_loc = 0
    rows = conn.execute(
        "SELECT serial_no,location FROM courses WHERE semester=? AND "
        "(location LIKE '%合授%' OR location LIKE '%與%授%')", (sem,)).fetchall()
    for sn, loc in rows:
        cleaned = re.split(r"[，,]?\s*與[^與]*?合?授", loc)[0].strip().rstrip("，,。")
        if cleaned and cleaned != loc:
            conn.execute("UPDATE courses SET location=? WHERE semester=? AND serial_no=?",
                         (cleaned, sem, sn))
            fixed_loc += 1
    conn.commit()
    print(f"[clean] {sem}: 修正課名 {fixed_name} / 清理地點雜訊 {fixed_loc}")


def main() -> None:
    ap = argparse.ArgumentParser(description="merge v2 爬蟲 CSV 進 app.db + 清理髒資料")
    ap.add_argument("action", choices=["list", "detail", "clean", "all"])
    ap.add_argument("--semester", required=True, help="學期 e.g. 114-2")
    ap.add_argument("--overwrite", action="store_true", help="detail: 連已有長文一起覆蓋 (預設只填空)")
    ap.add_argument("--no-backup", action="store_true", help="跳過自動備份 (不建議)")
    args = ap.parse_args()

    if not args.no_backup:
        _backup_db()
    conn = sqlite3.connect(DB_PATH)
    try:
        if args.action in ("list", "all"):
            merge_list(conn, args.semester)
        if args.action in ("detail", "all"):
            merge_detail(conn, args.semester, args.overwrite)
        if args.action in ("clean", "all"):
            clean(conn, args.semester)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
