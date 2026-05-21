"""
適合度演算法。

四個成份 (0-100):
- recommendation: PTT 評價的「推薦指數」均值 × 20
- sweetness:      使用者甜度偏好 vs 評價甜度均值的接近程度
- loading:        使用者 loading 偏好 vs 評價 loading 均值的接近程度
- interest:       使用者興趣 tag 與「課名+系所」字串的命中度

權重 (合計 100):
- 30% recommendation
- 25% sweetness
- 25% loading
- 20% interest

只考慮有 PTT 結構化評價的 course_code (~719 個)。
"""

from __future__ import annotations

import sqlite3
from typing import Any

WEIGHT_REC = 0.30
WEIGHT_SWEET = 0.25
WEIGHT_LOAD = 0.25
WEIGHT_INTEREST = 0.20


def aggregate_course_stats(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """回傳 {course_code: {avg_rec, avg_sweet, avg_workload, n_reviews}}"""
    rows = conn.execute(
        """
        SELECT
            course_id AS course_code,
            AVG(CAST(NULLIF(recommendation, '') AS REAL)) AS avg_rec,
            AVG(CAST(NULLIF(sweetness, '')      AS REAL)) AS avg_sweet,
            AVG(CAST(NULLIF(workload, '')       AS REAL)) AS avg_workload,
            COUNT(*) AS n_reviews
        FROM reviews_structured
        GROUP BY course_id
        HAVING n_reviews > 0
        """
    ).fetchall()
    return {
        r["course_code"]: {
            "avg_rec": r["avg_rec"],
            "avg_sweet": r["avg_sweet"],
            "avg_workload": r["avg_workload"],
            "n_reviews": r["n_reviews"],
        }
        for r in rows
    }


def compute_fit(
    profile: dict[str, Any],
    stats: dict[str, Any] | None,
    course_name: str,
    department: str,
) -> dict[str, Any]:
    """回傳 {total, recommendation, sweetness, loading, interest, n_reviews}。"""
    # 評價來源 (1-5 → 0-100)
    if stats and stats.get("avg_rec") is not None:
        rec_score = stats["avg_rec"] * 20
    else:
        rec_score = 50.0  # 中性

    if stats and stats.get("avg_sweet") is not None:
        diff = abs(profile["pref_sweetness"] - stats["avg_sweet"] * 20)
        sweet_score = max(0.0, 100.0 - diff)
    else:
        sweet_score = 50.0

    if stats and stats.get("avg_workload") is not None:
        diff = abs(profile["pref_loading"] - stats["avg_workload"] * 20)
        load_score = max(0.0, 100.0 - diff)
    else:
        load_score = 50.0

    # 興趣 hit 計算
    interests = profile.get("interests") or []
    text = f"{course_name} {department}".lower()
    hits = sum(1 for tag in interests if tag and tag.lower() in text)
    interest_score = min(100.0, hits * 50.0)

    total = (
        WEIGHT_REC * rec_score
        + WEIGHT_SWEET * sweet_score
        + WEIGHT_LOAD * load_score
        + WEIGHT_INTEREST * interest_score
    )

    return {
        "total": round(total, 1),
        "recommendation": round(rec_score, 1),
        "sweetness": round(sweet_score, 1),
        "loading": round(load_score, 1),
        "interest": round(interest_score, 1),
        "n_reviews": (stats or {}).get("n_reviews", 0),
    }


def profile_row_to_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    """user_profiles row (or None) → dict with defaults。"""
    import json as _json

    if row is None:
        return {
            "ability_logic": 50, "ability_writing": 50, "ability_coding": 50,
            "ability_humanities": 50, "ability_teamwork": 50,
            "pref_sweetness": 50, "pref_loading": 50,
            "interests": [],
        }
    return {
        "ability_logic": row["ability_logic"],
        "ability_writing": row["ability_writing"],
        "ability_coding": row["ability_coding"],
        "ability_humanities": row["ability_humanities"],
        "ability_teamwork": row["ability_teamwork"],
        "pref_sweetness": row["pref_sweetness"],
        "pref_loading": row["pref_loading"],
        "interests": _json.loads(row["interests"]),
    }
