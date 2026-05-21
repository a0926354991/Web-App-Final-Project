"""
把 backend/data/course_ability.csv (LLM 標的能力分數) 載入 app.db 的 course_ability 表。

跑這個之前需要先跑 backend/llm_ability_tags.py 產出 CSV。

Usage:
    python backend/scripts/ingest_ability_tags.py
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "app.db"
CSV_PATH = DATA_DIR / "course_ability.csv"


def main() -> None:
    if not CSV_PATH.exists():
        raise SystemExit(f"找不到 {CSV_PATH} — 請先跑 backend/llm_ability_tags.py")
    if not DB_PATH.exists():
        raise SystemExit(f"找不到 {DB_PATH} — 請先跑 backend/scripts/ingest_csv.py")

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS course_ability (
            course_code TEXT PRIMARY KEY,
            logic       INTEGER NOT NULL DEFAULT 0,
            writing     INTEGER NOT NULL DEFAULT 0,
            coding      INTEGER NOT NULL DEFAULT 0,
            humanities  INTEGER NOT NULL DEFAULT 0,
            teamwork    INTEGER NOT NULL DEFAULT 0,
            updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    ok = err = 0
    with CSV_PATH.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r.get("error") or not r.get("course_code"):
                err += 1
                continue
            try:
                conn.execute(
                    """
                    INSERT INTO course_ability
                        (course_code, logic, writing, coding, humanities, teamwork, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(course_code) DO UPDATE SET
                        logic = excluded.logic,
                        writing = excluded.writing,
                        coding = excluded.coding,
                        humanities = excluded.humanities,
                        teamwork = excluded.teamwork,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        r["course_code"],
                        int(r["logic"]), int(r["writing"]), int(r["coding"]),
                        int(r["humanities"]), int(r["teamwork"]),
                    ),
                )
                ok += 1
            except (ValueError, KeyError):
                err += 1

    conn.commit()
    n_total = conn.execute("SELECT COUNT(*) FROM course_ability").fetchone()[0]
    conn.close()
    print(f"匯入完成: {ok} 筆成功, {err} 筆失敗 (table 共 {n_total} 列)")


if __name__ == "__main__":
    main()
