"""
課程資料品質檢查 — 隨時跑,看各欄位覆蓋率 / 已知髒值 / 評價覆蓋。

純讀 app.db,不修改任何東西。補完爬蟲資料後可跑來驗證品質。

用法:
    python backend/scripts/data_quality_report.py
    python backend/scripts/data_quality_report.py --semester 114-2
"""

from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"

# (DB 欄位, 顯示名)
FIELDS = [
    ("course_name", "課名"), ("teacher", "教師"), ("course_code", "課號"),
    ("req_type", "必選修"), ("department", "開課系所"),
    ("schedule_time", "上課時間"), ("location", "上課地點"),
    ("credits", "學分"), ("language", "授課語言"),
    ("overview", "課程概述"), ("objectives", "課程目標"),
    ("requirements", "課程要求"), ("grading", "評量方式"),
    ("notes", "備註"), ("expected_hours", "預期時數"),
]


def _coverage(conn: sqlite3.Connection, sem: str | None) -> None:
    where = "WHERE semester=?" if sem else ""
    args = (sem,) if sem else ()
    total = conn.execute(f"SELECT COUNT(*) FROM courses {where}", args).fetchone()[0]
    if total == 0:
        print(f"  (無課程: semester={sem})")
        return
    label = sem or "全部"
    print(f"\n===== 欄位覆蓋率 [{label}] (共 {total:,} 門) =====")
    print(f"{'欄位':<10}{'有值':>9}{'覆蓋':>8}")
    for col, zh in FIELDS:
        n = conn.execute(
            f"SELECT COUNT(*) FROM courses {where} {'AND' if where else 'WHERE'} "
            f"{col} IS NOT NULL AND TRIM({col})!=''", args).fetchone()[0]
        bar = "█" * round(n / total * 20)
        print(f"{zh:<10}{n:>9,}{n/total*100:>7.1f}%  {bar}")


def _dirty(conn: sqlite3.Connection, sem: str | None) -> None:
    where = "semester=? AND" if sem else ""
    args = (sem,) if sem else ()
    print(f"\n===== 已知髒值檢查 =====")

    # 課名含「臺大課程網」(爬蟲 title 抓失敗)
    n = conn.execute(
        f"SELECT COUNT(*) FROM courses WHERE {where} course_name LIKE '%臺大課程網%'", args).fetchone()[0]
    print(f"  課名含「臺大課程網」: {n}")

    # 地點含合授雜訊
    n = conn.execute(
        f"SELECT COUNT(*) FROM courses WHERE {where} (location LIKE '%合授%' OR location LIKE '%與%授%')",
        args).fetchone()[0]
    print(f"  地點含「合授」雜訊: {n}")

    # schedule_time 不像時段 (含中文句子 / 冒號)
    rows = conn.execute(
        f"SELECT schedule_time FROM courses WHERE {where} TRIM(schedule_time)!=''", args).fetchall()
    bad_st = sum(
        1 for (st,) in rows
        if not re.fullmatch(r"[一二三四五六日\d\sA-D,，/、·\-~～]+", st.strip()))
    print(f"  上課時間非標準格式 (含說明文字): {bad_st}")


def _reviews(conn: sqlite3.Connection) -> None:
    print(f"\n===== PTT 評價覆蓋 =====")
    raw = conn.execute("SELECT COUNT(*) FROM reviews_raw").fetchone()[0]
    struct = conn.execute("SELECT COUNT(*) FROM reviews_structured").fetchone()[0]
    codes = conn.execute(
        "SELECT COUNT(DISTINCT course_id) FROM reviews_structured "
        "WHERE course_id IN (SELECT course_code FROM courses)").fetchone()[0]
    uniq = conn.execute("SELECT COUNT(DISTINCT course_code) FROM courses").fetchone()[0]
    print(f"  原文 {raw:,} / 結構化 {struct:,}")
    print(f"  有評價的課號 {codes:,} / 全部課號 {uniq:,} ({codes/uniq*100:.1f}%)")


def main() -> None:
    ap = argparse.ArgumentParser(description="課程資料品質檢查 (唯讀)")
    ap.add_argument("--semester", default=None, help="只看某學期 e.g. 114-2;省略 = 全部 + 各學期")
    args = ap.parse_args()

    conn = sqlite3.connect(DB_PATH)
    try:
        if args.semester:
            _coverage(conn, args.semester)
            _dirty(conn, args.semester)
        else:
            _coverage(conn, None)
            for sem in [r[0] for r in conn.execute(
                    "SELECT DISTINCT semester FROM courses ORDER BY semester")]:
                _coverage(conn, sem)
            _dirty(conn, None)
        _reviews(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
