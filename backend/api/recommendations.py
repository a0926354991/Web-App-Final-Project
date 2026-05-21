"""
適合度演算法。

五個成份 (0-100):
- recommendation: PTT 評價的「推薦指數」均值 × 20
- sweetness:      使用者甜度偏好 vs 評價甜度均值的接近程度
- loading:        使用者 loading 偏好 vs 評價 loading 均值的接近程度
- interest:       手刻 TF-IDF: 使用者興趣 tag 對課程文字 (課名/系所/目標/概述/評量)
                  的 TF-IDF 加總,各區段加權 (課名 ×3 / 系所 ×3 / 目標 ×2 / 概述+評量 ×1)
- ability:        關鍵字 mapping 推每門課所需能力,取使用者那幾項能力的平均值

權重 (合計 100):
- 25% recommendation
- 20% sweetness
- 20% loading
- 20% interest
- 15% ability
"""

from __future__ import annotations

import math
import sqlite3
from typing import Any

WEIGHT_REC = 0.25
WEIGHT_SWEET = 0.20
WEIGHT_LOAD = 0.20
WEIGHT_INTEREST = 0.20
WEIGHT_ABILITY = 0.15

# 興趣 tag 的固定清單 (前端 INTEREST_OPTIONS 的鏡像)
INTEREST_TAGS_ALL = [
    "AI", "程式", "金融", "商管", "設計", "人文", "語言",
    "自然科學", "社會科學", "醫學", "法律", "體育", "藝術",
]

# 5 軸能力的關鍵字
ABILITY_KEYWORDS: dict[str, list[str]] = {
    "logic":      ["數學", "微積分", "邏輯", "線性代數", "離散", "機率", "統計", "證明", "解析", "演算"],
    "writing":    ["寫作", "論文", "報告", "文學", "閱讀", "撰寫", "口頭報告", "expository", "essay"],
    "coding":     ["程式", "演算法", "資料結構", "軟體", "編程", "Python", "Java", "C++", "JavaScript",
                   "system design", "programming", "資工", "資訊", "coding"],
    "humanities": ["哲學", "歷史", "藝術", "文化", "社會學", "人類學", "宗教", "倫理", "思想", "文明"],
    "teamwork":   ["團體", "合作", "專題", "小組", "工作坊", "團隊", "分組", "合製", "共同創作", "協作"],
}

# 興趣 tag 比對時,各文字區段的權重
INTEREST_TF_WEIGHT_NAME = 3
INTEREST_TF_WEIGHT_DEPT = 3
INTEREST_TF_WEIGHT_OBJ = 2
INTEREST_TF_WEIGHT_OV = 1  # 含 grading

# 模組級快取
_CACHE: dict[str, Any] = {}


# =========================================================================
# 啟動時建索引 (跑一次,~50ms for 8467 courses)
# =========================================================================


def init_indices(conn: sqlite3.Connection) -> None:
    """建立課程文字索引 + 每門課的 ability profile + 每個 interest tag 的 IDF。"""
    if _CACHE.get("ready"):
        return

    rows = conn.execute(
        """
        SELECT serial_no, course_name, department, objectives, overview, grading
        FROM courses
        """
    ).fetchall()

    text_index: dict[str, dict[str, str]] = {}
    ability_profile: dict[str, set[str]] = {}

    for r in rows:
        name = (r["course_name"] or "")
        dept = (r["department"] or "")
        obj = (r["objectives"] or "")
        ov = (r["overview"] or "") + " " + (r["grading"] or "")

        text_index[r["serial_no"]] = {
            "name": name.lower(),
            "dept": dept.lower(),
            "obj": obj.lower(),
            "ov": ov.lower(),
        }

        full_lower = (name + " " + dept + " " + obj + " " + ov).lower()
        prof: set[str] = set()
        for ability, keywords in ABILITY_KEYWORDS.items():
            if any(kw.lower() in full_lower for kw in keywords):
                prof.add(ability)
        ability_profile[r["serial_no"]] = prof

    # IDF: 在幾門課裡至少出現一次 → log(N / df)
    n_total = len(text_index)
    idf: dict[str, float] = {}
    for tag in INTEREST_TAGS_ALL:
        tag_lower = tag.lower()
        df = sum(
            1 for parts in text_index.values()
            if (tag_lower in parts["name"]
                or tag_lower in parts["dept"]
                or tag_lower in parts["obj"]
                or tag_lower in parts["ov"])
        )
        idf[tag] = math.log(n_total / max(df, 1))

    _CACHE["text_index"] = text_index
    _CACHE["ability_profile"] = ability_profile
    _CACHE["idf"] = idf
    _CACHE["ready"] = True


# =========================================================================
# 成份 score 計算 (per course)
# =========================================================================


def compute_interest_score(profile: dict[str, Any], serial_no: str) -> float:
    """TF-IDF based: 興趣 tag 在課程文字中的加權命中度。"""
    interests = profile.get("interests") or []
    if not interests:
        return 50.0  # 沒填興趣 → 中性

    parts = _CACHE["text_index"].get(serial_no)
    if not parts:
        return 50.0

    idf = _CACHE["idf"]
    score = 0.0
    for tag in interests:
        if tag not in idf:
            continue
        t = tag.lower()
        tf = (
            parts["name"].count(t) * INTEREST_TF_WEIGHT_NAME
            + parts["dept"].count(t) * INTEREST_TF_WEIGHT_DEPT
            + parts["obj"].count(t) * INTEREST_TF_WEIGHT_OBJ
            + parts["ov"].count(t) * INTEREST_TF_WEIGHT_OV
        )
        score += tf * idf[tag]

    # 正規化:依經驗 score 落在 0-15 之間,放大成 0-100 並 clamp
    return min(100.0, score * 10.0)


def compute_ability_score(profile: dict[str, Any], serial_no: str) -> float:
    """課程關鍵字命中哪些 ability → 取使用者那幾項的平均值。沒命中 → 中性 50。"""
    required = _CACHE["ability_profile"].get(serial_no, set())
    if not required:
        return 50.0

    user_vals = {
        "logic":      profile["ability_logic"],
        "writing":    profile["ability_writing"],
        "coding":     profile["ability_coding"],
        "humanities": profile["ability_humanities"],
        "teamwork":   profile["ability_teamwork"],
    }
    return sum(user_vals[a] for a in required) / len(required)


# =========================================================================
# 加總 fit
# =========================================================================


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
    serial_no: str,
) -> dict[str, Any]:
    """回傳 {total, recommendation, sweetness, loading, interest, ability, n_reviews}。"""
    # 評價來源 (1-5 → 0-100)
    if stats and stats.get("avg_rec") is not None:
        rec_score = stats["avg_rec"] * 20
    else:
        rec_score = 50.0

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

    interest_score = compute_interest_score(profile, serial_no)
    ability_score = compute_ability_score(profile, serial_no)

    total = (
        WEIGHT_REC * rec_score
        + WEIGHT_SWEET * sweet_score
        + WEIGHT_LOAD * load_score
        + WEIGHT_INTEREST * interest_score
        + WEIGHT_ABILITY * ability_score
    )

    return {
        "total": round(total, 1),
        "recommendation": round(rec_score, 1),
        "sweetness": round(sweet_score, 1),
        "loading": round(load_score, 1),
        "interest": round(interest_score, 1),
        "ability": round(ability_score, 1),
        "n_reviews": (stats or {}).get("n_reviews", 0),
    }


def profile_row_to_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    """user_profiles row (或 None) → dict with defaults。"""
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
