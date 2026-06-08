"""
跨 router 共用的 helper:
- 系所代碼表載入 / 查詢 (_DEPT_CODES)
- user row / profile 的轉換 helper

從原本塞在 main.py 的 module-level helper 搬出來,讓各 router 都能 import,
行為與原本完全一致。
"""

from __future__ import annotations

import json as _json
import sqlite3
from pathlib import Path

from .db import DB_PATH
from .recommendations import profile_row_to_dict
from .schemas import UserInfo, UserProfile


# =========================================================================
# 系所代碼表 (dept name → code)
# =========================================================================

_DEPT_CODES: dict[str, str] = {}  # dept_name → code (e.g. "中國文學系" → "1010")


def load_dept_codes() -> None:
    """載入 dept name → code mapping:
    - 學系代碼表.xls (大學部 80 個系)
    - dept_codes_institute.json (碩/博士班/研究所手動對應表)
    任一檔案不存在就跳過。"""
    data_dir = Path(DB_PATH).parent

    xls_path = data_dir / "學系代碼表.xls"
    if xls_path.exists():
        try:
            import pandas as _pd
            df = _pd.read_excel(xls_path, dtype=str).fillna("")
            for _, r in df.iterrows():
                name = r.get("學系全稱", "").strip()
                code = r.get("學系代碼", "").strip()
                if name and code:
                    _DEPT_CODES[name] = code
        except Exception as e:
            print(f"[dept_codes] xls 載入失敗: {e}")

    json_path = data_dir / "dept_codes_institute.json"
    if json_path.exists():
        try:
            with open(json_path, encoding="utf-8") as f:
                m = _json.load(f)
            for name, code in m.items():
                if name.startswith("_") or not isinstance(code, str):
                    continue
                _DEPT_CODES[name.strip()] = code.strip()
        except Exception as e:
            print(f"[dept_codes] json 載入失敗: {e}")


def dept_codes() -> dict[str, str]:
    """回傳已載入的 dept name → code mapping (供 router 讀)。"""
    return _DEPT_CODES


# =========================================================================
# row → schema 轉換
# =========================================================================


def row_to_user_info(row: sqlite3.Row) -> UserInfo:
    return UserInfo(id=row["id"], username=row["username"], created_at=row["created_at"])


def _row_get(row: sqlite3.Row, key: str, default):
    """sqlite3.Row 沒有 .get();欄位不存在 (舊 DB 尚未 migrate) 時回 default。"""
    return row[key] if key in row.keys() else default


def row_to_profile(row: sqlite3.Row) -> UserProfile:
    return UserProfile(
        ability_logic=row["ability_logic"],
        ability_writing=row["ability_writing"],
        ability_coding=row["ability_coding"],
        ability_humanities=row["ability_humanities"],
        ability_teamwork=row["ability_teamwork"],
        pref_sweetness=row["pref_sweetness"],
        pref_loading=row["pref_loading"],
        interests=_json.loads(row["interests"]),
        department=_row_get(row, "department", ""),
        weight_recommendation=_row_get(row, "weight_recommendation", 25),
        weight_sweetness=_row_get(row, "weight_sweetness", 20),
        weight_loading=_row_get(row, "weight_loading", 20),
        weight_interest=_row_get(row, "weight_interest", 20),
        weight_ability=_row_get(row, "weight_ability", 15),
        updated_at=row["updated_at"],
    )


def load_profile_dict(conn: sqlite3.Connection, user_id: int) -> dict:
    row = conn.execute(
        "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()
    return profile_row_to_dict(row)
