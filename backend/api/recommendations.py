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
import re
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


def _compile_tag_pattern(tag: str) -> re.Pattern:
    """ASCII tag (例如 'AI') 用 word boundary 避免 'main','again' 誤命中。中文 tag 用單純 substring。"""
    if tag.isascii():
        return re.compile(rf"\b{re.escape(tag)}\b", re.IGNORECASE)
    return re.compile(re.escape(tag))


# =========================================================================
# 啟動時建索引 (跑一次,~50ms for 8467 courses)
# =========================================================================


def init_indices(conn: sqlite3.Connection) -> None:
    """建立課程文字索引 + 每門課的 ability profile + 每個 interest tag 的 IDF。

    Ability profile 來源:
    - 優先用 course_ability table (LLM 標注的 0-100 連續分數)
    - 沒有資料就 fallback 到關鍵字 mapping (boolean: 該能力 required 或不 required)
    """
    if _CACHE.get("ready"):
        return

    rows = conn.execute(
        """
        SELECT semester, serial_no, course_code, course_name, department,
               objectives, overview, grading
        FROM courses
        """
    ).fetchall()

    # 先載入 LLM-tagged ability scores (如果有的話)。key = course_code
    llm_ability: dict[str, dict[str, int]] = {}
    try:
        llm_rows = conn.execute(
            "SELECT course_code, logic, writing, coding, humanities, teamwork FROM course_ability"
        ).fetchall()
        for r in llm_rows:
            llm_ability[r["course_code"]] = {
                "logic": r["logic"], "writing": r["writing"], "coding": r["coding"],
                "humanities": r["humanities"], "teamwork": r["teamwork"],
            }
    except sqlite3.OperationalError:
        # 表還沒建 — 全部走 keyword fallback
        pass

    # 每個 interest tag 預先 compile pattern (ASCII 用 \b\b, 中文用 substring)
    tag_patterns = {tag: _compile_tag_pattern(tag) for tag in INTEREST_TAGS_ALL}
    ability_kw_patterns = {
        ability: [_compile_tag_pattern(kw) for kw in keywords]
        for ability, keywords in ABILITY_KEYWORDS.items()
    }

    # 內部 key 一律用 (semester, serial_no) tuple
    text_index: dict[tuple[str, str], dict[str, str]] = {}
    ability_profile: dict[tuple[str, str], dict[str, int]] = {}

    for r in rows:
        name = (r["course_name"] or "")
        dept = (r["department"] or "")
        obj = (r["objectives"] or "")
        ov = (r["overview"] or "") + " " + (r["grading"] or "")

        key = (r["semester"], r["serial_no"])
        text_index[key] = {
            "name": name,
            "dept": dept,
            "obj": obj,
            "ov": ov,
        }

        if r["course_code"] in llm_ability:
            ability_profile[key] = dict(llm_ability[r["course_code"]])
        else:
            full = name + " " + dept + " " + obj + " " + ov
            prof: dict[str, int] = {}
            for ability, patterns in ability_kw_patterns.items():
                if any(p.search(full) for p in patterns):
                    prof[ability] = 100
            ability_profile[key] = prof

    # IDF: 在幾門課裡至少出現一次 → log(N / df)
    n_total = len(text_index)
    idf: dict[str, float] = {}
    for tag, pat in tag_patterns.items():
        df = sum(
            1 for parts in text_index.values()
            if (pat.search(parts["name"])
                or pat.search(parts["dept"])
                or pat.search(parts["obj"])
                or pat.search(parts["ov"]))
        )
        idf[tag] = math.log(n_total / max(df, 1))

    # 每門課命中哪些 interest tag (供「相關課程」用),key 也是 (semester, serial_no)
    interest_tags_per_course: dict[tuple[str, str], set[str]] = {}
    for key, parts in text_index.items():
        hit_tags: set[str] = set()
        for tag, pat in tag_patterns.items():
            if (pat.search(parts["name"]) or pat.search(parts["dept"])
                    or pat.search(parts["obj"]) or pat.search(parts["ov"])):
                hit_tags.add(tag)
        interest_tags_per_course[key] = hit_tags

    _CACHE["text_index"] = text_index
    _CACHE["ability_profile"] = ability_profile
    _CACHE["interest_tags"] = interest_tags_per_course
    _CACHE["idf"] = idf
    _CACHE["tag_patterns"] = tag_patterns
    _CACHE["ready"] = True


# =========================================================================
# 成份 score 計算 (per course)
# =========================================================================


def compute_interest_score(
    profile: dict[str, Any], course_key: tuple[str, str]
) -> tuple[float, list[str]]:
    """TF-IDF based。course_key = (semester, serial_no)。回傳 (score, matched_tags)。"""
    interests = profile.get("interests") or []
    if not interests:
        return 50.0, []

    parts = _CACHE["text_index"].get(course_key)
    if not parts:
        return 50.0, []

    idf = _CACHE["idf"]
    patterns = _CACHE["tag_patterns"]
    score = 0.0
    matched: list[str] = []
    for tag in interests:
        pat = patterns.get(tag)
        if pat is None:
            continue
        tf = (
            len(pat.findall(parts["name"])) * INTEREST_TF_WEIGHT_NAME
            + len(pat.findall(parts["dept"])) * INTEREST_TF_WEIGHT_DEPT
            + len(pat.findall(parts["obj"])) * INTEREST_TF_WEIGHT_OBJ
            + len(pat.findall(parts["ov"])) * INTEREST_TF_WEIGHT_OV
        )
        if tf > 0:
            matched.append(tag)
        score += tf * idf[tag]

    return min(100.0, score * 10.0), matched


def compute_ability_score(
    profile: dict[str, Any], course_key: tuple[str, str]
) -> tuple[float, list[str]]:
    """course_key = (semester, serial_no)。回傳 (score, required_abilities)。

    ability_profile[(sem,serial)] = {ability: weight_0_to_100, ...}。
    score = 用 weight 當權重對使用者各項能力做加權平均 (LLM 標 / 關鍵字 fallback)。
    """
    course_prof: dict[str, int] = _CACHE["ability_profile"].get(course_key, {})
    # 只看有 weight 的軸
    weights = {a: w for a, w in course_prof.items() if w > 0}
    if not weights:
        return 50.0, []

    user_vals = {
        "logic":      profile["ability_logic"],
        "writing":    profile["ability_writing"],
        "coding":     profile["ability_coding"],
        "humanities": profile["ability_humanities"],
        "teamwork":   profile["ability_teamwork"],
    }
    total_w = sum(weights.values())
    score = sum(weights[a] * user_vals[a] for a in weights) / total_w
    # 依 weight 由高到低排序,顯示「最重要的能力先」
    required = sorted(weights, key=lambda a: -weights[a])
    return score, required


# =========================================================================
# 為什麼推薦這門課 — template 文字
# =========================================================================

_ABILITY_LABEL_ZH = {
    "logic": "數理邏輯",
    "writing": "文字表達",
    "coding": "程式實作",
    "humanities": "人文素養",
    "teamwork": "團隊協作",
}


def compute_explanation(
    profile: dict[str, Any],
    fit: dict[str, Any],
    matched_interests: list[str],
    required_abilities: list[str],
) -> str:
    """根據 fit 各成份的高低,生出一句中文說明。"""
    highlights: list[str] = []

    if fit["recommendation"] >= 80 and fit["n_reviews"] > 0:
        highlights.append(f"PTT 推薦度高({fit['recommendation']:.0f}/100,{fit['n_reviews']} 篇評價)")
    elif fit["recommendation"] >= 60 and fit["n_reviews"] >= 2:
        highlights.append("PTT 評價不錯")

    if matched_interests:
        names = "、".join(f"『{t}』" for t in matched_interests[:3])
        highlights.append(f"命中你的{names}興趣")

    if fit["ability"] >= 75 and required_abilities:
        if len(required_abilities) == 1:
            zh = _ABILITY_LABEL_ZH.get(required_abilities[0], required_abilities[0])
            highlights.append(f"需要的{zh}能力是你的強項")
        else:
            highlights.append("需要的能力跟你的長處對得上")

    if fit["sweetness"] >= 80 and fit["n_reviews"] > 0:
        highlights.append("給分甜度跟你偏好相近")

    if fit["loading"] >= 80 and fit["n_reviews"] > 0:
        highlights.append("loading 跟你偏好相近")

    if not highlights:
        highlights.append("各項分數平均,可考慮看看")

    caveats: list[str] = []
    if fit["sweetness"] < 40 and fit["n_reviews"] > 0:
        caveats.append("給分可能不甜")
    if fit["loading"] < 40 and fit["n_reviews"] > 0:
        caveats.append("loading 比你偏好的重")
    if fit["ability"] < 40 and required_abilities:
        weak = [
            _ABILITY_LABEL_ZH.get(a, a)
            for a in required_abilities
            if profile.get(f"ability_{a}", 50) < 50
        ]
        if weak:
            caveats.append(f"需要的{weak[0]}你目前較弱")

    text = "、".join(highlights[:3])
    if caveats:
        text += ";但" + "、".join(caveats[:2])
    return text


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
    course_key: tuple[str, str],
) -> dict[str, Any]:
    """course_key = (semester, serial_no)。
    回傳 {total, recommendation, sweetness, loading, interest, ability, n_reviews}。"""
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

    interest_score, matched_interests = compute_interest_score(profile, course_key)
    ability_score, required_abilities = compute_ability_score(profile, course_key)

    total = (
        WEIGHT_REC * rec_score
        + WEIGHT_SWEET * sweet_score
        + WEIGHT_LOAD * load_score
        + WEIGHT_INTEREST * interest_score
        + WEIGHT_ABILITY * ability_score
    )

    fit = {
        "total": round(total, 1),
        "recommendation": round(rec_score, 1),
        "sweetness": round(sweet_score, 1),
        "loading": round(load_score, 1),
        "interest": round(interest_score, 1),
        "ability": round(ability_score, 1),
        "n_reviews": (stats or {}).get("n_reviews", 0),
    }
    fit["matched_interests"] = matched_interests
    fit["required_abilities"] = required_abilities
    fit["explanation"] = compute_explanation(profile, fit, matched_interests, required_abilities)
    return fit


# =========================================================================
# 相關課程 (related courses)
# =========================================================================


def _content_similarity(
    a_key: tuple[str, str],
    b_key: tuple[str, str],
    courses_meta: dict[tuple[str, str], dict],
) -> float:
    """0-100 分,加權:dept 30 + code prefix 20 + ability Jaccard ×30 + interest Jaccard ×20。"""
    if a_key == b_key:
        return 0.0

    text = _CACHE["text_index"]
    abil = _CACHE["ability_profile"]
    interest = _CACHE["interest_tags"]
    if a_key not in text or b_key not in text:
        return 0.0

    score = 0.0
    a_dept = text[a_key]["dept"]
    b_dept = text[b_key]["dept"]
    if a_dept and b_dept:
        if a_dept == b_dept:
            score += 30
        elif a_dept in b_dept or b_dept in a_dept:
            score += 15

    code_a = courses_meta.get(a_key, {}).get("course_code", "")
    code_b = courses_meta.get(b_key, {}).get("course_code", "")
    import re as _re
    prefix_a = _re.match(r"^[A-Za-z]+", code_a)
    prefix_b = _re.match(r"^[A-Za-z]+", code_b)
    if prefix_a and prefix_b and prefix_a.group() == prefix_b.group():
        score += 20

    a_abil = set(abil.get(a_key, {}).keys())
    b_abil = set(abil.get(b_key, {}).keys())
    if a_abil | b_abil:
        score += 30 * len(a_abil & b_abil) / len(a_abil | b_abil)

    a_tag = interest.get(a_key, set())
    b_tag = interest.get(b_key, set())
    if a_tag | b_tag:
        score += 20 * len(a_tag & b_tag) / len(a_tag | b_tag)

    return round(score, 1)


def find_related_by_content(
    target_key: tuple[str, str],
    conn: sqlite3.Connection,
    limit: int = 5,
) -> list[dict]:
    """target_key = (semester, serial_no)。"""
    rows = conn.execute(
        "SELECT semester, serial_no, course_code, course_name, teacher, department, credits FROM courses"
    ).fetchall()
    courses_meta = {(r["semester"], r["serial_no"]): dict(r) for r in rows}
    if target_key not in courses_meta:
        return []
    target_code = courses_meta[target_key]["course_code"]

    scored = []
    seen_codes = {target_code}
    for key in courses_meta:
        if key == target_key:
            continue
        score = _content_similarity(target_key, key, courses_meta)
        if score < 25:
            continue
        code = courses_meta[key]["course_code"]
        if code in seen_codes:
            continue
        seen_codes.add(code)
        scored.append((score, courses_meta[key]))

    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for score, c in scored[:limit]:
        out.append({
            "semester": c["semester"],
            "serial_no": c["serial_no"],
            "course_code": c["course_code"],
            "course_name": c["course_name"],
            "teacher": c["teacher"] or "",
            "department": c["department"] or "",
            "credits": c["credits"] or "",
            "score": score,
            "source": "content",
        })
    return out


def find_related_by_cf(
    target_key: tuple[str, str],
    conn: sqlite3.Connection,
    limit: int = 5,
    min_support: int = 3,
) -> list[dict]:
    """Collaborative filtering Jaccard。target_key = (semester, serial_no)。"""
    semester, serial_no = target_key
    row = conn.execute(
        "SELECT course_code FROM courses WHERE semester = ? AND serial_no = ?",
        (semester, serial_no),
    ).fetchone()
    if row is None:
        return []
    target_code = row["course_code"]

    users_target = {
        r["user_id"]
        for r in conn.execute(
            """
            SELECT DISTINCT h.user_id
            FROM user_history h
            JOIN courses c ON c.semester = h.semester AND c.serial_no = h.serial_no
            WHERE c.course_code = ?
            """,
            (target_code,),
        ).fetchall()
    }
    if len(users_target) < min_support:
        return []

    candidates = conn.execute(
        """
        SELECT c.course_code, GROUP_CONCAT(DISTINCT h.user_id) AS user_ids
        FROM user_history h
        JOIN courses c ON c.semester = h.semester AND c.serial_no = h.serial_no
        WHERE c.course_code != ?
        GROUP BY c.course_code
        """,
        (target_code,),
    ).fetchall()

    scored = []
    for r in candidates:
        users_b = set(int(u) for u in r["user_ids"].split(","))
        intersect = users_target & users_b
        if len(intersect) < min_support:
            continue
        jaccard = len(intersect) / len(users_target | users_b)
        scored.append((round(jaccard * 100, 1), r["course_code"], len(intersect)))

    scored.sort(key=lambda x: x[0], reverse=True)

    out = []
    for score, code, n in scored[:limit]:
        rep = conn.execute(
            """
            SELECT semester, serial_no, course_code, course_name, teacher, department, credits
            FROM courses
            WHERE course_code = ?
            ORDER BY semester DESC, serial_no DESC LIMIT 1
            """,
            (code,),
        ).fetchone()
        if rep is None:
            continue
        out.append({
            "semester": rep["semester"],
            "serial_no": rep["serial_no"],
            "course_code": rep["course_code"],
            "course_name": rep["course_name"],
            "teacher": rep["teacher"] or "",
            "department": rep["department"] or "",
            "credits": rep["credits"] or "",
            "score": score,
            "source": "cf",
            "n_users": n,
        })
    return out


def find_related_courses(
    target_key: tuple[str, str],
    conn: sqlite3.Connection,
    limit: int = 5,
) -> list[dict]:
    """先試 CF,不夠就 fallback 到 content。"""
    cf = find_related_by_cf(target_key, conn, limit=limit)
    if len(cf) >= limit:
        return cf
    cf_codes = {r["course_code"] for r in cf}
    content = [
        r for r in find_related_by_content(target_key, conn, limit=limit * 2)
        if r["course_code"] not in cf_codes
    ]
    return cf + content[: limit - len(cf)]


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
