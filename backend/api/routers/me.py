"""
登入後的使用者資料 router (全部需 auth):
- /me/profile          能力值 + 偏好 (get / upsert)
- /me/recommendations  Top N 推薦 (排除已修)
- /me/fit/{...}        單堂課適合度
- /me/fits             批次適合度
- /me/history          修課歷史 CRUD
- /me/wishlist         想修清單 CRUD

從 main.py 原樣搬出,路徑與回傳不變。
"""

from __future__ import annotations

import json as _json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import get_current_user
from ..db import get_conn
from ..deps import load_profile_dict, row_to_profile
from ..recommendations import aggregate_course_stats, compute_fit
from ..schemas import (
    FitBreakdown,
    FitsBatchRequest,
    HistoryAdd,
    HistoryItem,
    RecommendationItem,
    UserProfile,
    WishlistAdd,
    WishlistItem,
)

router = APIRouter(prefix="/me", tags=["me"])


# =========================================================================
# User profile (能力值 + 偏好)
# =========================================================================


@router.get("/profile", response_model=UserProfile)
def get_my_profile(
    current: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> UserProfile:
    row = conn.execute(
        "SELECT * FROM user_profiles WHERE user_id = ?", (current["id"],)
    ).fetchone()
    if row is None:
        # 第一次拿:回傳預設值(沒寫入 DB 直到使用者按存檔)
        return UserProfile()
    return row_to_profile(row)


@router.put("/profile", response_model=UserProfile)
def update_my_profile(
    body: UserProfile,
    current: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> UserProfile:
    interests_json = _json.dumps(body.interests, ensure_ascii=False)
    conn.execute(
        """
        INSERT INTO user_profiles (
            user_id, ability_logic, ability_writing, ability_coding,
            ability_humanities, ability_teamwork,
            pref_sweetness, pref_loading, interests, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET
            ability_logic = excluded.ability_logic,
            ability_writing = excluded.ability_writing,
            ability_coding = excluded.ability_coding,
            ability_humanities = excluded.ability_humanities,
            ability_teamwork = excluded.ability_teamwork,
            pref_sweetness = excluded.pref_sweetness,
            pref_loading = excluded.pref_loading,
            interests = excluded.interests,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            current["id"],
            body.ability_logic, body.ability_writing, body.ability_coding,
            body.ability_humanities, body.ability_teamwork,
            body.pref_sweetness, body.pref_loading, interests_json,
        ),
    )
    conn.commit()

    row = conn.execute(
        "SELECT * FROM user_profiles WHERE user_id = ?", (current["id"],)
    ).fetchone()
    return row_to_profile(row)


# =========================================================================
# Recommendations / fit-score
# =========================================================================


@router.get("/recommendations", response_model=list[RecommendationItem])
def my_recommendations(
    limit: int = Query(5, ge=1, le=50),
    current: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> list[RecommendationItem]:
    profile = load_profile_dict(conn, current["id"])
    stats_map = aggregate_course_stats(conn)
    if not stats_map:
        return []

    taken_codes = {
        r["course_code"]
        for r in conn.execute(
            """
            SELECT DISTINCT c.course_code
            FROM user_history h
            JOIN courses c ON c.semester = h.semester AND c.serial_no = h.serial_no
            WHERE h.user_id = ?
            """,
            (current["id"],),
        ).fetchall()
    }

    # 每個 course_code 取最新學期的代表 (semester, serial_no)
    placeholders = ",".join("?" * len(stats_map))
    reps = conn.execute(
        f"""
        SELECT c.semester, c.serial_no, c.course_code,
               c.course_name, c.teacher, c.department, c.credits
        FROM courses c
        JOIN (
            SELECT course_code, MAX(semester || '_' || serial_no) AS marker
            FROM courses
            WHERE course_code IN ({placeholders})
            GROUP BY course_code
        ) m ON m.course_code = c.course_code
            AND m.marker = c.semester || '_' || c.serial_no
        """,
        list(stats_map.keys()),
    ).fetchall()

    # 第一輪:對所有候選課程算 fit (不呼叫 LLM,純計算 → 快)
    scored: list[tuple[float, dict, dict]] = []  # (total, row, fit)
    for r in reps:
        code = r["course_code"]
        if code in taken_codes:
            continue
        course_key = (r["semester"], r["serial_no"])
        fit = compute_fit(profile, stats_map.get(code), course_key, use_llm=False)
        scored.append((fit["total"], dict(r), fit))

    scored.sort(key=lambda x: x[0], reverse=True)

    # 第二輪:只對 top-N 重新生成 LLM explanation,平行呼叫
    top = scored[:limit]

    def _enrich(r: dict, fit: dict) -> RecommendationItem:
        course_key = (r["semester"], r["serial_no"])
        llm_fit = compute_fit(
            profile, stats_map.get(r["course_code"]), course_key,
            use_llm=True,
            use_semantic=True,  # top-N 重排才開 embedding 語意加成 (只 N 次,有快取)
            course_meta={
                "course_name": r["course_name"] or "",
                "department": r["department"] or "",
                "teacher": r["teacher"] or "",
            },
        )
        return RecommendationItem(
            semester=r["semester"],
            serial_no=r["serial_no"],
            course_code=r["course_code"],
            course_name=r["course_name"],
            teacher=r["teacher"] or "",
            department=r["department"] or "",
            credits=r["credits"] or "",
            fit=FitBreakdown(**llm_fit),
        )

    with ThreadPoolExecutor(max_workers=min(8, max(1, len(top)))) as ex:
        out = list(ex.map(lambda t: _enrich(t[1], t[2]), top))
    return out


@router.get("/fit/{semester}/{serial_no}", response_model=FitBreakdown)
def my_fit(
    semester: str,
    serial_no: str,
    current: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> FitBreakdown:
    course = conn.execute(
        "SELECT course_code, course_name, department, teacher FROM courses WHERE semester = ? AND serial_no = ?",
        (semester, serial_no),
    ).fetchone()
    if course is None:
        raise HTTPException(404, f"course {semester}/{serial_no} not found")

    profile = load_profile_dict(conn, current["id"])
    stats = conn.execute(
        """
        SELECT
            AVG(CAST(NULLIF(recommendation, '') AS REAL)) AS avg_rec,
            AVG(CAST(NULLIF(sweetness, '')      AS REAL)) AS avg_sweet,
            AVG(CAST(NULLIF(workload, '')       AS REAL)) AS avg_workload,
            COUNT(*) AS n_reviews
        FROM reviews_structured
        WHERE course_id = ?
        """,
        (course["course_code"],),
    ).fetchone()
    stats_dict = dict(stats) if stats and stats["n_reviews"] > 0 else None

    fit = compute_fit(
        profile, stats_dict, (semester, serial_no),
        use_llm=True,
        course_meta={
            "course_name": course["course_name"] or "",
            "department": course["department"] or "",
            "teacher": course["teacher"] or "",
        },
    )
    return FitBreakdown(**fit)


@router.post("/fits", response_model=dict[str, FitBreakdown])
def my_fits_batch(
    body: FitsBatchRequest,
    current: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, FitBreakdown]:
    """批次拿一組 (semester, serial_no) 的 fit (供探索頁表格用)。
    回傳 key = "{semester}__{serial_no}"。"""
    items = body.items or []
    if not items:
        return {}

    conds = " OR ".join("(semester=? AND serial_no=?)" for _ in items)
    args: list[str] = []
    for it in items:
        args.extend([it.semester, it.serial_no])
    rows = conn.execute(
        f"SELECT semester, serial_no, course_code FROM courses WHERE {conds}",
        args,
    ).fetchall()

    profile = load_profile_dict(conn, current["id"])
    stats_map = aggregate_course_stats(conn)

    out: dict[str, FitBreakdown] = {}
    for r in rows:
        key = f"{r['semester']}__{r['serial_no']}"
        fit = compute_fit(profile, stats_map.get(r["course_code"]), (r["semester"], r["serial_no"]))
        out[key] = FitBreakdown(**fit)
    return out


# =========================================================================
# User history (修課歷史)
# =========================================================================


@router.get("/history", response_model=list[HistoryItem])
def list_my_history(
    current: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> list[HistoryItem]:
    rows = conn.execute(
        """
        SELECT h.id, h.semester, h.serial_no, h.grade, h.notes, h.added_at,
               c.course_code, c.course_name, c.teacher, c.credits, c.department
        FROM user_history h
        LEFT JOIN courses c ON c.semester = h.semester AND c.serial_no = h.serial_no
        WHERE h.user_id = ?
        ORDER BY h.semester DESC, h.added_at DESC
        """,
        (current["id"],),
    ).fetchall()
    return [HistoryItem(**{k: (r[k] if r[k] is not None else "") for k in r.keys()}) for r in rows]


@router.post("/history", response_model=HistoryItem, status_code=201)
def add_to_history(
    body: HistoryAdd,
    current: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> HistoryItem:
    if not body.semester.strip() or not body.serial_no.strip():
        raise HTTPException(400, "semester / serial_no 為必填")
    course = conn.execute(
        "SELECT 1 FROM courses WHERE semester = ? AND serial_no = ?",
        (body.semester, body.serial_no),
    ).fetchone()
    if course is None:
        raise HTTPException(404, f"course {body.semester}/{body.serial_no} not found")

    try:
        cur = conn.execute(
            """
            INSERT INTO user_history (user_id, semester, serial_no, grade, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (current["id"], body.semester.strip(), body.serial_no.strip(),
             (body.grade or None), (body.notes or None)),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(409, "已在修課歷史中")
    conn.commit()
    new_id = cur.lastrowid

    row = conn.execute(
        """
        SELECT h.id, h.semester, h.serial_no, h.grade, h.notes, h.added_at,
               c.course_code, c.course_name, c.teacher, c.credits, c.department
        FROM user_history h
        LEFT JOIN courses c ON c.semester = h.semester AND c.serial_no = h.serial_no
        WHERE h.id = ?
        """,
        (new_id,),
    ).fetchone()
    return HistoryItem(**{k: (row[k] if row[k] is not None else "") for k in row.keys()})


@router.delete("/history/{history_id}", status_code=204)
def delete_history(
    history_id: int,
    current: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> None:
    cur = conn.execute(
        "DELETE FROM user_history WHERE id = ? AND user_id = ?",
        (history_id, current["id"]),
    )
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "history item not found")


# =========================================================================
# Wishlist (想修清單)
# =========================================================================


def _wishlist_row_to_item(row: sqlite3.Row) -> WishlistItem:
    return WishlistItem(
        id=row["id"],
        semester=row["semester"],
        serial_no=row["serial_no"],
        notes=row["notes"],
        added_at=row["added_at"],
        course_code=row["course_code"] or "",
        course_name=row["course_name"] or "",
        teacher=row["teacher"] or "",
        credits=row["credits"] or "",
        department=row["department"] or "",
    )


@router.get("/wishlist", response_model=list[WishlistItem])
def list_my_wishlist(
    current: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> list[WishlistItem]:
    rows = conn.execute(
        """
        SELECT w.id, w.semester, w.serial_no, w.notes, w.added_at,
               c.course_code, c.course_name, c.teacher, c.credits, c.department
        FROM user_wishlist w
        LEFT JOIN courses c ON c.semester = w.semester AND c.serial_no = w.serial_no
        WHERE w.user_id = ?
        ORDER BY w.added_at DESC
        """,
        (current["id"],),
    ).fetchall()
    return [_wishlist_row_to_item(r) for r in rows]


@router.post("/wishlist", response_model=WishlistItem, status_code=201)
def add_to_wishlist(
    body: WishlistAdd,
    current: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> WishlistItem:
    course = conn.execute(
        "SELECT 1 FROM courses WHERE semester = ? AND serial_no = ?",
        (body.semester, body.serial_no),
    ).fetchone()
    if course is None:
        raise HTTPException(404, f"course {body.semester}/{body.serial_no} not found")

    try:
        cur = conn.execute(
            "INSERT INTO user_wishlist (user_id, semester, serial_no, notes) VALUES (?, ?, ?, ?)",
            (current["id"], body.semester, body.serial_no, body.notes or None),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(409, "已在想修清單中")
    conn.commit()

    row = conn.execute(
        """
        SELECT w.id, w.semester, w.serial_no, w.notes, w.added_at,
               c.course_code, c.course_name, c.teacher, c.credits, c.department
        FROM user_wishlist w
        LEFT JOIN courses c ON c.semester = w.semester AND c.serial_no = w.serial_no
        WHERE w.id = ?
        """,
        (cur.lastrowid,),
    ).fetchone()
    return _wishlist_row_to_item(row)


@router.delete("/wishlist/{wishlist_id}", status_code=204)
def delete_wishlist(
    wishlist_id: int,
    current: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> None:
    cur = conn.execute(
        "DELETE FROM user_wishlist WHERE id = ? AND user_id = ?",
        (wishlist_id, current["id"]),
    )
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "wishlist item not found")
