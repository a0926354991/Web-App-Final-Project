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

import hashlib
import json
import math
import os
import re
import sqlite3
import time
from typing import Any

from . import llm

WEIGHT_REC = 0.25
WEIGHT_SWEET = 0.20
WEIGHT_LOAD = 0.20
WEIGHT_INTEREST = 0.20
WEIGHT_ABILITY = 0.15

# 預設權重 (與上面常數一致),compute_fit 在沒給 weights 時用這組
DEFAULT_WEIGHTS: dict[str, float] = {
    "recommendation": WEIGHT_REC,
    "sweetness": WEIGHT_SWEET,
    "loading": WEIGHT_LOAD,
    "interest": WEIGHT_INTEREST,
    "ability": WEIGHT_ABILITY,
}

# user_profiles 裡每個成份權重欄位名 (使用者可在前端用滑桿調)
_WEIGHT_PROFILE_KEYS: dict[str, str] = {
    "recommendation": "weight_recommendation",
    "sweetness": "weight_sweetness",
    "loading": "weight_loading",
    "interest": "weight_interest",
    "ability": "weight_ability",
}


def weights_from_profile(profile: dict[str, Any]) -> dict[str, float]:
    """從 profile 的 weight_* 欄位 (0-100 整數) 取出 5 成份權重並 normalize 成總和=1。

    任一欄位缺失或總和 <= 0 → 退回 DEFAULT_WEIGHTS。
    讓使用者用滑桿自由設「我多看重 PTT 推薦 / 甜度 / loading / 興趣 / 能力」。"""
    raw: dict[str, float] = {}
    for comp, key in _WEIGHT_PROFILE_KEYS.items():
        v = profile.get(key)
        if v is None:
            return dict(DEFAULT_WEIGHTS)
        raw[comp] = float(v)
    total = sum(raw.values())
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {k: v / total for k, v in raw.items()}

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

# LLM explanation 快取:相同 (course_key, profile_sig, fit_sig) 不重算
# 命中 → 0 延遲 + 0 token,典型情境是同一使用者重新整理首頁
_LLM_EXPLANATION_CACHE: dict[str, str] = {}
_LLM_EXPLANATION_CACHE_MAX = 2000

_LLM_SYSTEM_PROMPT = (
    "你是台大選課助教。根據使用者的能力、偏好,以及一門課的 PTT 評價統計與適合度分數,"
    "用 1-2 句、總長 60 字以內的中文白話,告訴使用者『為什麼這門課適合 / 不適合他』。"
    "規則:\n"
    "- 不要列點、不要用「首先」「其次」、不要寒暄\n"
    "- 提到具體理由(例如:命中興趣、能力契合、給分甜、loading 重等),但不要重複數字\n"
    "- 如有明顯缺點(loading 重、給分不甜、能力差距大)務必點出\n"
    "- 評價少於 2 篇就要說「樣本少,僅供參考」"
)


def _profile_signature(profile: dict[str, Any]) -> str:
    """穩定的 profile 指紋,用於 cache key。"""
    parts = [
        profile.get("ability_logic"), profile.get("ability_writing"),
        profile.get("ability_coding"), profile.get("ability_humanities"),
        profile.get("ability_teamwork"),
        profile.get("pref_sweetness"), profile.get("pref_loading"),
        ",".join(sorted(profile.get("interests") or [])),
    ]
    return hashlib.md5(json.dumps(parts).encode()).hexdigest()[:12]


def compute_explanation_llm(
    profile: dict[str, Any],
    fit: dict[str, Any],
    matched_interests: list[str],
    required_abilities: list[str],
    course_meta: dict[str, str] | None,
    course_key: tuple[str, str],
) -> str | None:
    """用 Gemini 生成個人化說明。失敗或 LLM 沒設定就回 None,呼叫端應 fallback。"""
    if not llm.is_available():
        return None

    fit_sig = f"{fit['total']:.0f}_{fit['recommendation']:.0f}_{fit['sweetness']:.0f}_{fit['loading']:.0f}_{fit['interest']:.0f}_{fit['ability']:.0f}_{fit['n_reviews']}"
    cache_key = f"{course_key[0]}__{course_key[1]}__{_profile_signature(profile)}__{fit_sig}"
    if cache_key in _LLM_EXPLANATION_CACHE:
        return _LLM_EXPLANATION_CACHE[cache_key]

    name = (course_meta or {}).get("course_name", "")
    dept = (course_meta or {}).get("department", "")
    teacher = (course_meta or {}).get("teacher", "")

    user_abilities_zh = ", ".join(
        f"{_ABILITY_LABEL_ZH[a]}{profile.get(f'ability_{a}', 50)}"
        for a in ["logic", "writing", "coding", "humanities", "teamwork"]
    )
    required_zh = "、".join(_ABILITY_LABEL_ZH.get(a, a) for a in required_abilities[:3]) or "無特別要求"
    interests_zh = "、".join(profile.get("interests") or []) or "未指定"
    matched_zh = "、".join(matched_interests) or "無"

    prompt = (
        f"課程:{name}({dept}{f' / {teacher} 老師' if teacher else ''})\n"
        f"使用者能力(0-100):{user_abilities_zh}\n"
        f"使用者興趣:{interests_zh}\n"
        f"使用者偏好:甜度{profile.get('pref_sweetness', 50)}/100、loading {profile.get('pref_loading', 50)}/100\n"
        f"---\n"
        f"適合度總分 {fit['total']:.0f}/100,組成:\n"
        f"- PTT 推薦 {fit['recommendation']:.0f}({fit['n_reviews']} 篇評價)\n"
        f"- 給分甜度契合 {fit['sweetness']:.0f}\n"
        f"- Loading 契合 {fit['loading']:.0f}\n"
        f"- 興趣命中 {fit['interest']:.0f}(命中:{matched_zh})\n"
        f"- 能力契合 {fit['ability']:.0f}(課程需要:{required_zh})\n"
    )

    # llm.generate_text 內部關掉 thinking,200 token 足夠 60 字中文輸出
    text = llm.generate_text(
        prompt,
        system=_LLM_SYSTEM_PROMPT,
        max_output_tokens=200,
        temperature=0.35,
    )
    if not text:
        return None

    # 簡單 cache 驅逐
    if len(_LLM_EXPLANATION_CACHE) >= _LLM_EXPLANATION_CACHE_MAX:
        for k in list(_LLM_EXPLANATION_CACHE.keys())[:200]:
            _LLM_EXPLANATION_CACHE.pop(k, None)
    _LLM_EXPLANATION_CACHE[cache_key] = text
    return text


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
    if fit.get("is_estimated"):
        text = "（此課無 PTT 評價,甜度/loading/推薦為同類課估計）" + text
    return text


# =========================================================================
# 加總 fit
# =========================================================================


# aggregate stats 快取 TTL（秒）— reviews_structured 變動頻率低，1 小時夠用
_STATS_TTL_SECONDS = 3600


def aggregate_course_stats(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """回傳 {course_code: {avg_rec, avg_sweet, avg_workload, n_reviews}}

    結果快取在模組級 _CACHE 內，TTL=1 小時，避免每次推薦 / 批次 fit 請求都
    全表掃 reviews_structured。資料變動可呼叫 invalidate_stats_cache() 立即失效。
    """
    cached = _CACHE.get("stats_map")
    cached_at = _CACHE.get("stats_map_at", 0.0)
    if cached is not None and (time.monotonic() - cached_at) < _STATS_TTL_SECONDS:
        return cached

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
    stats_map = {
        r["course_code"]: {
            "avg_rec": r["avg_rec"],
            "avg_sweet": r["avg_sweet"],
            "avg_workload": r["avg_workload"],
            "n_reviews": r["n_reviews"],
        }
        for r in rows
    }
    _CACHE["stats_map"] = stats_map
    _CACHE["stats_map_at"] = time.monotonic()
    return stats_map


def invalidate_stats_cache() -> None:
    """手動失效 aggregate_course_stats 快取（重新 ingest 評價後可呼叫）。"""
    _CACHE.pop("stats_map", None)
    _CACHE.pop("stats_map_at", None)
    _CACHE.pop("proxy_stats", None)


# =========================================================================
# 冷啟動 (cold-start): 沒有 PTT 評價的課,用「同課號前綴 → 同系所」的評價平均當代理
# =========================================================================


def build_proxy_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    """為冷啟動建代理評價:把「有評價的課」依 課號英文前綴 / 開課系所 分組求均值。

    回傳 {"by_prefix": {prefix: stats}, "by_dept": {dept: stats}, "code_dept": {code: dept}}。
    每個 stats = {avg_rec, avg_sweet, avg_workload, n_codes}。
    結果快取在 _CACHE,重新 ingest 後 invalidate_stats_cache() / invalidate_indices() 失效。"""
    cached = _CACHE.get("proxy_stats")
    if cached is not None:
        return cached

    stats_map = aggregate_course_stats(conn)
    meta = courses_meta_cache(conn)

    code_dept: dict[str, str] = {}
    for m in meta.values():
        c = m.get("course_code")
        if c and c not in code_dept:
            code_dept[c] = m.get("department") or ""

    def _prefix(code: str) -> str:
        m = re.match(r"^[A-Za-z]+", code or "")
        return m.group() if m else ""

    pre_acc: dict[str, dict] = {}
    dept_acc: dict[str, dict] = {}
    for code, s in stats_map.items():
        if s.get("avg_rec") is None:
            continue
        for bucket, k in ((pre_acc, _prefix(code)), (dept_acc, code_dept.get(code, ""))):
            if not k:
                continue
            b = bucket.setdefault(k, {"rec": [], "sw": [], "wl": [], "codes": 0})
            b["codes"] += 1
            if s.get("avg_rec") is not None:
                b["rec"].append(s["avg_rec"])
            if s.get("avg_sweet") is not None:
                b["sw"].append(s["avg_sweet"])
            if s.get("avg_workload") is not None:
                b["wl"].append(s["avg_workload"])

    def _finalize(acc: dict[str, dict]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for k, b in acc.items():
            out[k] = {
                "avg_rec": sum(b["rec"]) / len(b["rec"]) if b["rec"] else None,
                "avg_sweet": sum(b["sw"]) / len(b["sw"]) if b["sw"] else None,
                "avg_workload": sum(b["wl"]) / len(b["wl"]) if b["wl"] else None,
                "n_codes": b["codes"],
                "n_reviews": 0,  # 代理分數不是「這門課」的真實評價數
            }
        return out

    proxy = {
        "by_prefix": _finalize(pre_acc),
        "by_dept": _finalize(dept_acc),
        "code_dept": code_dept,
    }
    _CACHE["proxy_stats"] = proxy
    return proxy


# 代理分數至少要由幾個「有評價的課」聚合,才夠可信
_PROXY_MIN_CODES = 3


def resolve_stats(
    course_code: str,
    department: str,
    stats_map: dict[str, Any],
    proxy: dict[str, Any],
) -> tuple[dict[str, Any] | None, bool]:
    """解析一門課要用的評價 stats。回傳 (stats, is_estimated)。

    階梯:
      1. 有自己的 PTT 評價 → 用真實值 (is_estimated=False)
      2. 同課號前綴 (e.g. CSIE) 的評價均值 (聚合 >= 3 個課號) → 估計值
      3. 同系所的評價均值 (聚合 >= 3 個課號) → 估計值
      4. 都沒有 → (None, False),compute_fit 會退回中性 50"""
    s = stats_map.get(course_code)
    if s and s.get("avg_rec") is not None:
        return s, False

    m = re.match(r"^[A-Za-z]+", course_code or "")
    prefix = m.group() if m else ""
    dept = department or proxy.get("code_dept", {}).get(course_code, "")

    p = proxy["by_prefix"].get(prefix)
    if p and p.get("avg_rec") is not None and p["n_codes"] >= _PROXY_MIN_CODES:
        return p, True
    d = proxy["by_dept"].get(dept)
    if d and d.get("avg_rec") is not None and d["n_codes"] >= _PROXY_MIN_CODES:
        return d, True
    return None, False


def invalidate_indices() -> None:
    """失效課程文字索引 + ability profile + IDF + 衍生快取。

    興趣 TF-IDF 比對吃 course_name / department / objectives / overview / grading,
    這些索引在 startup 建一次就快取 (init_indices 的 `ready` 守門)。補爬課程長文
    (overview/objectives/grading) 後須呼叫此函式 (或重啟 server),否則推薦的興趣
    分數仍用舊的 (多為空的) 課程文字。下次 init_indices 會重建。

    同時失效 courses_meta_cache (相關課程用) 與 period1_set (早八過濾用),
    兩者都假設課程資料在 runtime 不變;重新 ingest 課程後須一併失效。"""
    for k in ("text_index", "ability_profile", "interest_tags", "idf", "tag_patterns",
              "ready", "courses_meta", "period1_set"):
        _CACHE.pop(k, None)


def courses_meta_cache(conn: sqlite3.Connection) -> dict[tuple[str, str], dict]:
    """{(semester, serial_no): {course_code, course_name, teacher, department, credits}}。

    課程資料在 runtime 視為不變,所以全表只讀一次後快取在 _CACHE。
    取代「每次 related / substitutes 請求都 SELECT 全表 (~18k 列) + 重建 dict」。
    重新 ingest 課程後呼叫 invalidate_indices() 失效。"""
    cached = _CACHE.get("courses_meta")
    if cached is not None:
        return cached
    rows = conn.execute(
        "SELECT semester, serial_no, course_code, course_name, teacher, department, credits FROM courses"
    ).fetchall()
    meta = {(r["semester"], r["serial_no"]): dict(r) for r in rows}
    _CACHE["courses_meta"] = meta
    return meta


def period1_course_keys(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    """回傳「課表含第 1 節 (早八)」的 (semester, serial_no) 集合,建一次後快取。

    取代 list_courses 的 no_period1 過濾每次對所有候選列 re-parse schedule_time
    (regex 重)。判定邏輯與原本 parse_schedule 完全一致 (含第 1 節即排除)。
    重新 ingest 課程後呼叫 invalidate_indices() 失效。"""
    cached = _CACHE.get("period1_set")
    if cached is not None:
        return cached
    from .schedule import parse_schedule

    rows = conn.execute("SELECT semester, serial_no, schedule_time FROM courses").fetchall()
    keys = {
        (r["semester"], r["serial_no"])
        for r in rows
        if any(str(p) == "1" for _, p in parse_schedule(r["schedule_time"]))
    }
    _CACHE["period1_set"] = keys
    return keys


# 語意加成:TF-IDF 與 embedding 語意分的混合權重 (各半)
SEMANTIC_BLEND = 0.5


def _maybe_semantic_boost(
    profile: dict[str, Any], course_key: tuple[str, str], tfidf_score: float
) -> float:
    """用 embedding 語意相似度加成 TF-IDF 興趣分。失敗 / 無 key → 原樣回傳。

    ai_features 在 module 末端 lazy import,避免 circular import
    (ai_features 會 from .recommendations import ...)。"""
    interests = profile.get("interests") or []
    if not interests:
        return tfidf_score
    parts = _CACHE.get("text_index", {}).get(course_key)
    if not parts:
        return tfidf_score
    course_text = f"{parts['name']} {parts['dept']} {parts['obj']} {parts['ov']}"
    try:
        from . import ai_features
        sem = ai_features.semantic_interest_score(interests, course_text)
    except Exception:
        sem = None
    if sem is None:
        return tfidf_score
    return round(SEMANTIC_BLEND * sem + (1 - SEMANTIC_BLEND) * tfidf_score, 1)


def compute_fit(
    profile: dict[str, Any],
    stats: dict[str, Any] | None,
    course_key: tuple[str, str],
    *,
    use_llm: bool = False,
    use_semantic: bool = False,
    course_meta: dict[str, str] | None = None,
    weights: dict[str, float] | None = None,
    estimated: bool = False,
) -> dict[str, Any]:
    """course_key = (semester, serial_no)。
    回傳 {total, recommendation, sweetness, loading, interest, ability, n_reviews, is_estimated}。

    use_llm=True 時嘗試呼叫 Gemini 生成 explanation;失敗 fallback 模板。
    use_semantic=True 時對興趣分做 embedding 語意加成 (僅用於 top-N 重排,因為
        每次要呼叫 Gemini embedding;失敗 / 無 key 自動只用 TF-IDF)。
    course_meta = {"course_name", "department", "teacher"} 供 LLM 用。
    weights = 5 成份權重 (已 normalize),None → DEFAULT_WEIGHTS。
    estimated = True 表示 stats 是冷啟動代理值 (非這門課真實評價),會標進 is_estimated。"""
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

    # 語意加成 (只在 top-N 重排階段開):用 Gemini embedding 算「使用者興趣 ↔ 課程
    # 文字」的語意相似度,跟手刻 TF-IDF 的興趣分混合 (各半),補強同義詞抓不到的缺點
    # (例如興趣標『AI』但課名寫『機器學習』『深度學習』,純關鍵字會漏)。
    # 失敗 / 無 GEMINI_API_KEY → semantic 回 None → 維持純 TF-IDF。
    interest_score = _maybe_semantic_boost(profile, course_key, interest_score) if use_semantic else interest_score

    w = weights or DEFAULT_WEIGHTS
    total = (
        w["recommendation"] * rec_score
        + w["sweetness"] * sweet_score
        + w["loading"] * load_score
        + w["interest"] * interest_score
        + w["ability"] * ability_score
    )

    fit = {
        "total": round(total, 1),
        "recommendation": round(rec_score, 1),
        "sweetness": round(sweet_score, 1),
        "loading": round(load_score, 1),
        "interest": round(interest_score, 1),
        "ability": round(ability_score, 1),
        "n_reviews": (stats or {}).get("n_reviews", 0),
        "is_estimated": estimated,
    }
    fit["matched_interests"] = matched_interests
    fit["required_abilities"] = required_abilities

    explanation: str | None = None
    if use_llm and os.environ.get("USE_LLM_EXPLANATION", "1") != "0":
        explanation = compute_explanation_llm(
            profile, fit, matched_interests, required_abilities, course_meta, course_key
        )
    if not explanation:
        explanation = compute_explanation(profile, fit, matched_interests, required_abilities)
    fit["explanation"] = explanation
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
    courses_meta = courses_meta_cache(conn)
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
            "weight_recommendation": 25, "weight_sweetness": 20, "weight_loading": 20,
            "weight_interest": 20, "weight_ability": 15,
        }
    keys = row.keys()
    return {
        "ability_logic": row["ability_logic"],
        "ability_writing": row["ability_writing"],
        "ability_coding": row["ability_coding"],
        "ability_humanities": row["ability_humanities"],
        "ability_teamwork": row["ability_teamwork"],
        "pref_sweetness": row["pref_sweetness"],
        "pref_loading": row["pref_loading"],
        "interests": _json.loads(row["interests"]),
        "weight_recommendation": row["weight_recommendation"] if "weight_recommendation" in keys else 25,
        "weight_sweetness": row["weight_sweetness"] if "weight_sweetness" in keys else 20,
        "weight_loading": row["weight_loading"] if "weight_loading" in keys else 20,
        "weight_interest": row["weight_interest"] if "weight_interest" in keys else 20,
        "weight_ability": row["weight_ability"] if "weight_ability" in keys else 15,
    }
