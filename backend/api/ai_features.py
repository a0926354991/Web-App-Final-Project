"""
LLM-powered features: 個人化摘要 / 心得整理 / 替代課推薦 /
學期平衡顧問 / 興趣建議 / 教師教學風格。

設計原則:
- 每個 feature 都有 in-memory cache (避免重複呼叫)
- 失敗一律回 None,呼叫端決定怎麼跟使用者顯示
- 所有 prompt 限制中文輸出 + 字數
"""

from __future__ import annotations

import hashlib
import sqlite3
from typing import Any

from . import llm
from .recommendations import _ABILITY_LABEL_ZH, _profile_signature

# ---------- 通用 cache ----------

_CACHE: dict[str, str] = {}
_CACHE_MAX = 2000


def _cache_get(key: str) -> str | None:
    return _CACHE.get(key)


def _cache_set(key: str, val: str) -> None:
    if len(_CACHE) >= _CACHE_MAX:
        for k in list(_CACHE.keys())[:200]:
            _CACHE.pop(k, None)
    _CACHE[key] = val


def _truncate(text: str | None, n: int) -> str:
    if not text:
        return ""
    text = text.strip()
    return text if len(text) <= n else text[:n] + "…"


# =========================================================================
# #3 個人化課程摘要
# =========================================================================

_SUMMARY_SYSTEM = (
    "你是台大選課助教。根據課程的官方資料、PTT 評價統計、以及這位使用者的能力 / 偏好,"
    "寫一段 2-3 句、總長 100 字內的中文白話摘要,告訴他『這門課實際上會怎麼上、適不適合你修』。"
    "規則:不要列點、不要寒暄、不要重複數字、不要假設使用者修過先修課。"
)


def personalized_course_summary(
    profile: dict[str, Any],
    course: dict[str, Any],
    stats: dict[str, Any] | None,
) -> str | None:
    """course 必含 course_name / department / teacher / overview / objectives / grading。"""
    if not llm.is_available():
        return None

    profile_sig = _profile_signature(profile)
    course_sig = f"{course.get('semester')}__{course.get('serial_no')}"
    key = f"summary__{course_sig}__{profile_sig}"
    cached = _cache_get(key)
    if cached:
        return cached

    user_abilities = ", ".join(
        f"{_ABILITY_LABEL_ZH[a]}{profile.get(f'ability_{a}', 50)}"
        for a in ["logic", "writing", "coding", "humanities", "teamwork"]
    )
    interests = "、".join(profile.get("interests") or []) or "未指定"
    stats_text = ""
    if stats and stats.get("n_reviews"):
        stats_text = (
            f"PTT 評價({stats['n_reviews']} 篇): 推薦 {stats.get('avg_rec', 0):.1f}/5、"
            f"甜度 {stats.get('avg_sweet', 0):.1f}/5、loading {stats.get('avg_workload', 0):.1f}/5"
        )

    teacher = course.get("teacher") or ""
    teacher_part = f" / {teacher} 老師" if teacher else ""
    prompt = (
        f"課程:{course.get('course_name')}({course.get('department', '')}{teacher_part})\n"
        f"課程概述:{_truncate(course.get('overview'), 500)}\n"
        f"課程目標:{_truncate(course.get('objectives'), 300)}\n"
        f"評量方式:{_truncate(course.get('grading'), 200)}\n"
        f"{stats_text}\n"
        f"---\n"
        f"使用者能力(0-100):{user_abilities}\n"
        f"使用者興趣:{interests}\n"
        f"使用者偏好:甜度 {profile.get('pref_sweetness', 50)}/100、loading {profile.get('pref_loading', 50)}/100"
    )

    text = llm.generate_text(prompt, system=_SUMMARY_SYSTEM, max_output_tokens=300, temperature=0.4)
    if text:
        _cache_set(key, text)
    return text


# =========================================================================
# #5 修課心得整理
# =========================================================================

_HISTORY_SUMMARY_SYSTEM = (
    "你是學習助理。根據課程資訊與使用者輸入的心得筆記,寫一段 2-3 句、總長 120 字內的中文,"
    "幫他整理「這門課我學到什麼、收穫是什麼、有哪些可以記下來的重點」。"
    "規則:第二人稱、不要列點、不要寒暄、若 notes 太短或空就回『筆記太少,無法整理重點』。"
)


def summarize_history_note(
    course_name: str,
    department: str,
    objectives: str,
    grade: str,
    notes: str,
) -> str | None:
    if not llm.is_available():
        return None
    if not notes or len(notes.strip()) < 5:
        return "筆記太少,無法整理重點"

    key = f"hist__{hashlib.md5((course_name + notes + (grade or '')).encode()).hexdigest()[:16]}"
    cached = _cache_get(key)
    if cached:
        return cached

    prompt = (
        f"課程:{course_name}({department or ''})\n"
        f"課程目標:{_truncate(objectives, 250)}\n"
        f"我的成績:{grade or '未填'}\n"
        f"我的筆記:{_truncate(notes, 800)}"
    )
    text = llm.generate_text(prompt, system=_HISTORY_SUMMARY_SYSTEM, max_output_tokens=350, temperature=0.4)
    if text:
        _cache_set(key, text)
    return text


# =========================================================================
# #4 衝堂替代課推薦理由 (LLM 解釋 why)
#    候選課程仍由 find_related_courses 提供,LLM 只負責生成『為什麼推薦這幾門』的說明
# =========================================================================

_SUBSTITUTE_SYSTEM = (
    "你是台大選課助教。使用者原本想修課程 A,但跟另一門課時間衝堂。"
    "從一組『內容相似但不衝堂』的替代課中,挑 2-3 門,各用 1 句中文(20 字內)說明為何適合替代。"
    "輸出格式嚴格:每行一個推薦,格式『[課名] - [理由]』,不要其他文字、不要編號、不要 markdown。"
)


def explain_substitutes(
    target_course: dict[str, Any],
    candidates: list[dict[str, Any]],
    user_busy_slots: list[str] | None = None,
) -> str | None:
    if not llm.is_available() or not candidates:
        return None

    def _cand_line(c: dict[str, Any]) -> str:
        t = c.get("teacher") or ""
        tail = f" / {t} 老師" if t else ""
        return f"- {c.get('course_name')}({c.get('department', '')}{tail})"
    cand_lines = "\n".join(_cand_line(c) for c in candidates[:8])
    cand_key = "_".join(c.get("course_code", "") for c in candidates[:8])
    key = f"sub__{target_course.get('semester')}__{target_course.get('serial_no')}__{hashlib.md5(cand_key.encode()).hexdigest()[:8]}"
    cached = _cache_get(key)
    if cached:
        return cached

    prompt = (
        f"原想修:{target_course.get('course_name')}"
        f"({target_course.get('department', '')})\n"
        f"---\n"
        f"候選替代課程:\n{cand_lines}"
    )
    text = llm.generate_text(prompt, system=_SUBSTITUTE_SYSTEM, max_output_tokens=400, temperature=0.4)
    if text:
        _cache_set(key, text)
    return text


# =========================================================================
# #8 學期 workload 平衡顧問
# =========================================================================

_BALANCE_SYSTEM = (
    "你是台大選課顧問。根據使用者本學期已加入的課程清單(含 loading、推薦度、所需能力),"
    "用 2-3 句中文(120 字內)評估這學期的整體負擔與能力分布是否平衡。"
    "規則:具體指出『coding 集中』『loading 過重』『缺乏人文調節』等;不要列點;沒問題就說『搭配平衡,可以放心去修』。"
)


def schedule_balance_advice(
    courses: list[dict[str, Any]],
    profile: dict[str, Any] | None = None,
) -> str | None:
    if not llm.is_available() or not courses:
        return None

    lines = []
    for c in courses[:20]:
        bits = [c.get("course_name", ""), f"{c.get('credits', '?')}學分"]
        if c.get("avg_workload") is not None:
            bits.append(f"loading {c['avg_workload']:.1f}/5")
        if c.get("avg_rec") is not None:
            bits.append(f"PTT {c['avg_rec']:.1f}/5")
        if c.get("ability_axes"):
            bits.append(f"重{','.join(_ABILITY_LABEL_ZH.get(a, a) for a in c['ability_axes'][:2])}")
        lines.append("- " + " · ".join(bits))

    course_sig = "_".join(f"{c.get('semester', '')}__{c.get('serial_no', '')}" for c in courses)
    profile_sig = _profile_signature(profile) if profile else "anon"
    key = f"bal__{hashlib.md5(course_sig.encode()).hexdigest()[:12]}__{profile_sig}"
    cached = _cache_get(key)
    if cached:
        return cached

    user_part = ""
    if profile:
        user_part = (
            f"使用者偏好:loading {profile.get('pref_loading', 50)}/100、"
            f"甜度 {profile.get('pref_sweetness', 50)}/100\n"
        )
    prompt = f"本學期課程清單:\n" + "\n".join(lines) + f"\n{user_part}"
    text = llm.generate_text(prompt, system=_BALANCE_SYSTEM, max_output_tokens=350, temperature=0.4)
    if text:
        _cache_set(key, text)
    return text


# =========================================================================
# #7 動態興趣標籤建議
# =========================================================================

_INTEREST_SUGGEST_SYSTEM = (
    "你是台大選課助理。根據使用者的修課歷史,推測他可能還有哪些『沒在固定 13 個標籤中』的細分興趣。"
    "輸出嚴格格式:每行一個建議,格式『[興趣名 2-6 字] | [一句理由,20 字內]』,2-4 個建議,"
    "不要 markdown、不要編號、不要重複給定的 13 個標籤。"
)

_FIXED_INTERESTS = [
    "AI", "程式", "金融", "商管", "設計", "人文", "語言",
    "自然科學", "社會科學", "醫學", "法律", "體育", "藝術",
]


def suggest_interests(history_courses: list[dict[str, Any]]) -> str | None:
    if not llm.is_available() or not history_courses:
        return None

    lines = [
        f"- {c.get('course_name')}({c.get('department', '')})"
        for c in history_courses[:30]
    ]
    sig = "_".join(c.get("course_code", "") for c in history_courses)
    key = f"int__{hashlib.md5(sig.encode()).hexdigest()[:12]}"
    cached = _cache_get(key)
    if cached:
        return cached

    prompt = (
        f"已修課程:\n" + "\n".join(lines) +
        f"\n---\n固定標籤(請避免重複):{', '.join(_FIXED_INTERESTS)}"
    )
    text = llm.generate_text(prompt, system=_INTEREST_SUGGEST_SYSTEM, max_output_tokens=300, temperature=0.5)
    if text:
        _cache_set(key, text)
    return text


# =========================================================================
# #6 教師教學風格摘要
# =========================================================================

_TEACHER_STYLE_SYSTEM = (
    "你是台大課程觀察員。根據一位老師多門課的 PTT 評價摘要與課程資訊,"
    "用 2-3 句(總長 120 字內)中文白話描述這位老師的教學風格與評分習慣。"
    "規則:具體指出『重討論』『給分嚴格』『投影片詳細』等;不要寒暄;不要列點;"
    "若評價樣本少(<3 篇)就在最後加『樣本少僅供參考』。"
)


# =========================================================================
# #9 先修脈絡推論 (lazy, per-course on-demand)
# =========================================================================

_PREREQ_SYSTEM = (
    "你是台大課程顧問。根據課程的官方資訊(課名、系所、目標、評量、概述),"
    "推測使用者修這門課前『最好先具備什麼背景或先修課程』。"
    "輸出 1-2 句中文(80 字內),具體點出建議的先修科目或基礎能力。"
    "規則:不要列點;若該課明顯是基礎課程不需先修,就回『此為入門課程,無需特別先修』;"
    "如果無法判斷就回『官方資訊不足以判斷』。"
)


def infer_prerequisites(course: dict[str, Any]) -> str | None:
    """course 必含 course_name / department / objectives / overview。"""
    if not llm.is_available():
        return None
    key = f"prereq__{course.get('semester')}__{course.get('serial_no')}"
    cached = _cache_get(key)
    if cached:
        return cached

    prompt = (
        f"課程:{course.get('course_name')}({course.get('department', '')})\n"
        f"課程目標:{_truncate(course.get('objectives'), 300)}\n"
        f"課程概述:{_truncate(course.get('overview'), 400)}\n"
        f"評量方式:{_truncate(course.get('grading'), 150)}"
    )
    text = llm.generate_text(prompt, system=_PREREQ_SYSTEM, max_output_tokens=250, temperature=0.35)
    if text:
        _cache_set(key, text)
    return text


# =========================================================================
# #2 語意化興趣比對 (lazy embeddings, user-side)
#
# 注意:對 8467 門課全量 embedding 需要離線批次,屬於 infrastructure scope。
# 這個函式只 embed 使用者的興趣 tag 跟『候選課程的短描述』,
# 用於 fit 計算階段給興趣分數加成 (補強原本 regex-based TF-IDF 抓不到同義詞的缺點)。
# 候選課程仍由原本 ranking 階段提供,只在 top-K 重排時使用 semantic boost。
# =========================================================================

_EMBEDDING_CACHE: dict[str, list[float]] = {}


def _embed_text(text: str) -> list[float] | None:
    """單次 embedding。失敗回 None。Gemini text-embedding-004。"""
    if not llm.is_available():
        return None
    if not text:
        return None
    key = hashlib.md5(text.encode()).hexdigest()
    if key in _EMBEDDING_CACHE:
        return _EMBEDDING_CACHE[key]
    try:
        from google import genai
        client = llm._get_client()
        if client is None:
            return None
        resp = client.models.embed_content(
            model="text-embedding-004",
            contents=text,
        )
        # resp.embeddings is a list of ContentEmbedding; take first
        vec = list(resp.embeddings[0].values)
        _EMBEDDING_CACHE[key] = vec
        return vec
    except Exception as e:
        print(f"[llm] embed 失敗: {e}")
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    import math as _m
    dot = sum(x * y for x, y in zip(a, b))
    na = _m.sqrt(sum(x * x for x in a))
    nb = _m.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def semantic_interest_score(user_interests: list[str], course_text: str) -> float | None:
    """回 0-100 分,代表使用者興趣跟課程文字的語意契合度。失敗回 None。"""
    if not user_interests or not course_text:
        return None
    if not llm.is_available():
        return None

    query = "、".join(user_interests)
    q_vec = _embed_text(query)
    c_vec = _embed_text(_truncate(course_text, 400))
    if q_vec is None or c_vec is None:
        return None
    sim = _cosine(q_vec, c_vec)  # -1 to 1
    # 把 [0, 1] 線性映射到 [0, 100],負值 clamp 0
    return max(0.0, min(100.0, sim * 100.0))


def teacher_style_summary(
    teacher: str,
    reviews: list[dict[str, Any]],
    course_count: int,
) -> str | None:
    if not llm.is_available():
        return None

    n = len(reviews)
    key = f"teacher__{hashlib.md5((teacher + str(n) + str(course_count)).encode()).hexdigest()[:16]}"
    cached = _cache_get(key)
    if cached:
        return cached

    if n == 0:
        return None

    bits = []
    for r in reviews[:20]:
        bit = []
        if r.get("teaching_style"):
            bit.append(f"風格:{_truncate(r['teaching_style'], 60)}")
        if r.get("grading_method"):
            bit.append(f"評分:{_truncate(r['grading_method'], 60)}")
        if r.get("summary"):
            bit.append(_truncate(r["summary"], 100))
        if bit:
            bits.append("- " + " | ".join(bit))

    if not bits:
        return None

    prompt = (
        f"老師:{teacher}(開過 {course_count} 門課,共 {n} 篇 PTT 評價)\n"
        f"評價精選:\n" + "\n".join(bits)
    )
    text = llm.generate_text(prompt, system=_TEACHER_STYLE_SYSTEM, max_output_tokens=350, temperature=0.4)
    if text:
        _cache_set(key, text)
    return text
