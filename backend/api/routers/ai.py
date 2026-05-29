"""
AI features router — 9 個 LLM-powered 功能 (沒 key 自動 fallback,不會壞)。

路徑橫跨 /me、/teachers、/courses 三個前綴,所以這個 router 不設共用 prefix,
各 endpoint 用完整路徑宣告,與重構前的 main.py 完全一致:
- #3 GET  /me/courses/{sem}/{sno}/summary        個人化課程摘要
- #4 GET  /me/courses/{sem}/{sno}/substitutes    衝堂替代課推薦
- #5 POST /me/history/{id}/summarize             修課心得整理
- #6 GET  /teachers/{name}/style                 教師教學風格摘要 (公開)
- #7 GET  /me/suggested-interests                動態興趣標籤建議
- #8 POST /me/schedule/balance                   學期 workload 平衡顧問
- #9 GET  /courses/{sem}/{sno}/prerequisites     先修脈絡推論 (公開)
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import ai_features
from ..auth import get_current_user
from ..db import get_conn
from ..deps import load_profile_dict
from ..recommendations import aggregate_course_stats, find_related_courses

router = APIRouter(tags=["ai"])


@router.get("/me/courses/{semester}/{serial_no}/summary")
def my_course_summary(
    semester: str,
    serial_no: str,
    current: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, str | None]:
    """#3 個人化課程摘要"""
    course = conn.execute(
        "SELECT semester, serial_no, course_code, course_name, department, teacher, "
        "overview, objectives, grading FROM courses WHERE semester = ? AND serial_no = ?",
        (semester, serial_no),
    ).fetchone()
    if course is None:
        raise HTTPException(404, "course not found")

    stats_row = conn.execute(
        """
        SELECT
            AVG(CAST(NULLIF(recommendation, '') AS REAL)) AS avg_rec,
            AVG(CAST(NULLIF(sweetness, '')      AS REAL)) AS avg_sweet,
            AVG(CAST(NULLIF(workload, '')       AS REAL)) AS avg_workload,
            COUNT(*) AS n_reviews
        FROM reviews_structured WHERE course_id = ?
        """,
        (course["course_code"],),
    ).fetchone()
    stats = dict(stats_row) if stats_row and stats_row["n_reviews"] > 0 else None

    profile = load_profile_dict(conn, current["id"])
    text = ai_features.personalized_course_summary(profile, dict(course), stats)
    return {"summary": text}


@router.post("/me/history/{history_id}/summarize")
def my_history_summarize(
    history_id: int,
    current: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, str | None]:
    """#5 修課心得整理"""
    row = conn.execute(
        """
        SELECT h.grade, h.notes, c.course_name, c.department, c.objectives
        FROM user_history h
        JOIN courses c ON c.semester = h.semester AND c.serial_no = h.serial_no
        WHERE h.id = ? AND h.user_id = ?
        """,
        (history_id, current["id"]),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "history item not found")

    text = ai_features.summarize_history_note(
        course_name=row["course_name"] or "",
        department=row["department"] or "",
        objectives=row["objectives"] or "",
        grade=row["grade"] or "",
        notes=row["notes"] or "",
    )
    return {"summary": text}


@router.get("/me/courses/{semester}/{serial_no}/substitutes")
def my_substitutes(
    semester: str,
    serial_no: str,
    limit: int = Query(5, ge=1, le=10),
    current: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict:
    """#4 衝堂替代課推薦 - 候選來自 find_related_courses,LLM 解釋為何"""
    course = conn.execute(
        "SELECT semester, serial_no, course_code, course_name, department FROM courses "
        "WHERE semester = ? AND serial_no = ?",
        (semester, serial_no),
    ).fetchone()
    if course is None:
        raise HTTPException(404, "course not found")

    candidates = find_related_courses((semester, serial_no), conn, limit=limit)
    explanation = ai_features.explain_substitutes(dict(course), candidates)
    return {"candidates": candidates, "explanation": explanation}


@router.post("/me/schedule/balance")
def my_schedule_balance(
    body: dict,
    current: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, str | None]:
    """#8 學期 workload 平衡顧問。body: {items: [{semester, serial_no}, ...]}"""
    items = body.get("items") or []
    if not items:
        return {"advice": None}

    # 取每門課的 stats + ability axes
    stats_map = aggregate_course_stats(conn)
    courses_input: list[dict] = []
    for it in items[:20]:
        sem = it.get("semester")
        sno = it.get("serial_no")
        if not sem or not sno:
            continue
        row = conn.execute(
            "SELECT semester, serial_no, course_code, course_name, credits FROM courses "
            "WHERE semester = ? AND serial_no = ?",
            (sem, sno),
        ).fetchone()
        if row is None:
            continue
        c: dict = dict(row)
        s = stats_map.get(row["course_code"])
        if s:
            c["avg_rec"] = s.get("avg_rec")
            c["avg_workload"] = s.get("avg_workload")
        # ability axes (前 N 個有 weight 的)
        from ..recommendations import _CACHE as _rec_cache
        prof = _rec_cache.get("ability_profile", {}).get((sem, sno), {})
        c["ability_axes"] = [a for a, w in sorted(prof.items(), key=lambda kv: -kv[1]) if w > 0][:3]
        courses_input.append(c)

    profile = load_profile_dict(conn, current["id"])
    advice = ai_features.schedule_balance_advice(courses_input, profile)
    return {"advice": advice}


@router.get("/me/suggested-interests")
def my_suggested_interests(
    current: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict:
    """#7 動態興趣標籤建議"""
    rows = conn.execute(
        """
        SELECT c.course_code, c.course_name, c.department
        FROM user_history h
        JOIN courses c ON c.semester = h.semester AND c.serial_no = h.serial_no
        WHERE h.user_id = ?
        ORDER BY h.added_at DESC LIMIT 30
        """,
        (current["id"],),
    ).fetchall()
    history = [dict(r) for r in rows]
    if not history:
        return {"suggestions": None, "has_history": False}

    text = ai_features.suggest_interests(history)
    return {"suggestions": text, "has_history": True}


@router.get("/teachers/{name}/style")
def teacher_style(
    name: str,
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, str | None]:
    """#6 教師教學風格摘要 (公開,無需 auth)"""
    name = name.strip()
    if not name:
        raise HTTPException(400, "teacher name 不可空白")

    course_codes_rows = conn.execute(
        "SELECT DISTINCT course_code FROM courses WHERE teacher = ?",
        (name,),
    ).fetchall()
    if not course_codes_rows:
        raise HTTPException(404, f"teacher '{name}' not found")
    course_codes = [r["course_code"] for r in course_codes_rows]
    placeholders = ",".join("?" * len(course_codes))

    reviews = conn.execute(
        f"""
        SELECT teaching_style, grading_method, summary
        FROM reviews_structured
        WHERE course_id IN ({placeholders})
            AND (teaching_style != '' OR grading_method != '' OR summary != '')
        LIMIT 25
        """,
        course_codes,
    ).fetchall()

    text = ai_features.teacher_style_summary(name, [dict(r) for r in reviews], len(course_codes))
    return {"style": text}


@router.get("/courses/{semester}/{serial_no}/prerequisites")
def course_prerequisites(
    semester: str,
    serial_no: str,
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, str | None]:
    """#9 先修脈絡推論 (公開,無需 auth)"""
    row = conn.execute(
        "SELECT semester, serial_no, course_name, department, objectives, overview, grading "
        "FROM courses WHERE semester = ? AND serial_no = ?",
        (semester, serial_no),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "course not found")
    text = ai_features.infer_prerequisites(dict(row))
    return {"prerequisites": text}
