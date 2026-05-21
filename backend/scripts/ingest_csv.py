"""
把 backend/data/ 下 CSV 灌進 SQLite (app.db)。

表結構：
  courses             — 一列 = 一筆「學期 + 課號 + 教師」開課；PK = 流水號
  reviews_raw         — PTT 原文；PK = (post_url, course_id)
  reviews_structured  — Claude 結構化結果；PK = custom_id

join：reviews.course_id ↔ courses.course_code（= 原 CSV 的「課號」）

兩種模式：
- 預設(--rebuild)：DROP 三張資料表重建,從預設的三個 CSV 重灌(會清掉舊資料)
- --append-courses <csv>：只 append 新學期的 courses CSV,既有資料完整保留
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "app.db"

DETAILED_CSV = DATA_DIR / "ntu_detailed_data.csv"
RAW_CSV = DATA_DIR / "ntu_reviews_raw.csv"
STRUCTURED_CSV = DATA_DIR / "ntu_reviews_structured.csv"

# CSV 中文欄位 → SQLite 英文欄位
COURSE_COL_MAP = {
    "課名": "course_name",
    "教師": "teacher",
    "流水號": "serial_no",
    "課號": "course_code",
    "課程識別碼": "course_identifier",
    "必選修": "req_type",
    "開課系所": "department",
    "上課時間": "schedule_time",
    "上課地點": "location",
    "加簽類別": "signup_class",
    "授課語言": "language",
    "學分": "credits",
    "修課人數上限": "enrollment_cap",
    "課程概述": "overview",
    "課程目標": "objectives",
    "課程要求": "requirements",
    "評量方式": "grading",
    "備註": "notes",
    "預期學習時數": "expected_hours",
    "詳情頁URL": "detail_url",
}

SCHEMA_SQL = """
DROP TABLE IF EXISTS courses;
DROP TABLE IF EXISTS reviews_raw;
DROP TABLE IF EXISTS reviews_structured;

CREATE TABLE courses (
    serial_no          TEXT PRIMARY KEY,
    course_code        TEXT,
    course_identifier  TEXT,
    course_name        TEXT,
    teacher            TEXT,
    req_type           TEXT,
    department         TEXT,
    schedule_time      TEXT,
    location           TEXT,
    signup_class       TEXT,
    language           TEXT,
    credits            TEXT,
    enrollment_cap     TEXT,
    overview           TEXT,
    objectives         TEXT,
    requirements       TEXT,
    grading            TEXT,
    notes              TEXT,
    expected_hours     TEXT,
    detail_url         TEXT
);
CREATE INDEX idx_courses_code       ON courses(course_code);
CREATE INDEX idx_courses_teacher    ON courses(teacher);
CREATE INDEX idx_courses_department ON courses(department);

CREATE TABLE reviews_raw (
    course_id   TEXT,
    course_name TEXT,
    teacher     TEXT,
    post_url    TEXT,
    post_title  TEXT,
    post_author TEXT,
    post_date   TEXT,
    content     TEXT,
    source      TEXT,
    PRIMARY KEY (post_url, course_id)
);
CREATE INDEX idx_raw_course_id ON reviews_raw(course_id);

CREATE TABLE reviews_structured (
    custom_id      TEXT PRIMARY KEY,
    course_id      TEXT,
    course_name    TEXT,
    teacher        TEXT,
    post_url       TEXT,
    post_title     TEXT,
    post_date      TEXT,
    post_tag       TEXT,
    year_term      TEXT,
    has_template   TEXT,
    recommendation TEXT,
    sweetness      TEXT,
    workload       TEXT,
    teaching_style TEXT,
    grading_method TEXT,
    summary        TEXT
);
CREATE INDEX idx_structured_course_id ON reviews_structured(course_id);
"""


def rebuild() -> None:
    """從預設三個 CSV 重新建表 (會清掉既有 courses / reviews_raw / reviews_structured)。"""
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_SQL)

    print(f"[1/3] loading {DETAILED_CSV.name} ...")
    df = pd.read_csv(DETAILED_CSV, dtype=str).fillna("")
    df = df.rename(columns=COURSE_COL_MAP)
    df = df.drop_duplicates(subset=["serial_no"])
    df.to_sql("courses", conn, if_exists="append", index=False)
    print(f"      courses: {len(df)} rows")

    print(f"[2/3] loading {RAW_CSV.name} ...")
    df = pd.read_csv(RAW_CSV, dtype=str).fillna("")
    df = df.drop_duplicates(subset=["post_url", "course_id"])
    df.to_sql("reviews_raw", conn, if_exists="append", index=False)
    print(f"      reviews_raw: {len(df)} rows")

    print(f"[3/3] loading {STRUCTURED_CSV.name} ...")
    df = pd.read_csv(STRUCTURED_CSV, dtype=str).fillna("")
    df = df.drop_duplicates(subset=["custom_id"])
    df.to_sql("reviews_structured", conn, if_exists="append", index=False)
    print(f"      reviews_structured: {len(df)} rows")

    conn.commit()
    conn.close()
    print(f"\n✓ wrote {DB_PATH} ({DB_PATH.stat().st_size / 1_000_000:.1f} MB)")


def append_courses(csv_path: Path) -> None:
    """把 courses CSV append 進現有 courses 表;serial_no 重複則跳過。"""
    if not csv_path.exists():
        raise SystemExit(f"找不到 CSV: {csv_path}")
    if not DB_PATH.exists():
        raise SystemExit(f"找不到 {DB_PATH} — 先跑 rebuild 模式 (預設) 建好基本資料")

    print(f"loading {csv_path.name} (append mode) ...")
    df = pd.read_csv(csv_path, dtype=str).fillna("")
    df = df.rename(columns=COURSE_COL_MAP)
    df = df.drop_duplicates(subset=["serial_no"])

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    before = conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0]

    cols = list(COURSE_COL_MAP.values())
    placeholders = ",".join("?" * len(cols))
    col_list = ",".join(cols)
    rows_inserted = 0
    rows_skipped = 0
    for _, r in df.iterrows():
        if not r.get("serial_no"):
            rows_skipped += 1
            continue
        values = tuple(r.get(c, "") for c in cols)
        cur = conn.execute(
            f"INSERT OR IGNORE INTO courses ({col_list}) VALUES ({placeholders})",
            values,
        )
        if cur.rowcount:
            rows_inserted += 1
        else:
            rows_skipped += 1
    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
    conn.close()

    print(f"      inserted: {rows_inserted} / skipped (duplicate or empty): {rows_skipped}")
    print(f"      courses table: {before} → {after} rows")
    print("\n✓ append 完成。請重啟 backend (uvicorn) 讓 recommendations 索引重建。")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--append-courses", type=Path, default=None,
                    help="把指定的 courses CSV append 進現有 DB (不刪舊資料)")
    args = ap.parse_args()

    if args.append_courses:
        append_courses(args.append_courses)
    else:
        rebuild()


if __name__ == "__main__":
    main()
