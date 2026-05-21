"""
一次性：把 backend/data/ 下三個 CSV 灌進 SQLite (app.db)。

表結構：
  courses             — 一列 = 一筆「學期 + 課號 + 教師」開課；PK = 流水號
  reviews_raw         — PTT 原文；PK = (post_url, course_id)
  reviews_structured  — Claude 結構化結果；PK = custom_id

join：reviews.course_id ↔ courses.course_code（= 原 CSV 的「課號」）
"""

from __future__ import annotations

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


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()

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


if __name__ == "__main__":
    main()
