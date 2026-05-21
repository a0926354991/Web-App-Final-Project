"""
FastAPI app — 課程查詢 / 評價檢索 API。

啟動：
    uvicorn backend.api.main:app --reload

互動式 docs：http://localhost:8000/docs
"""

from __future__ import annotations

import os
import sqlite3

import sqlite3 as _sqlite3

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import (
    check_login_rate_limit,
    get_current_user,
    hash_password,
    init_auth_tables,
    new_token,
    verify_password,
)
from .db import DB_PATH, get_conn
from .recommendations import (
    aggregate_course_stats,
    compute_fit,
    find_related_courses,
    init_indices,
    profile_row_to_dict,
)
from .schedule import parse_schedule
from .schemas import (
    AuthResponse,
    CourseDetail,
    CourseListResponse,
    CourseSummary,
    FitBreakdown,
    HistoryAdd,
    HistoryItem,
    TeacherCourseItem,
    TeacherDetail,
    TeacherStats,
    WishlistAdd,
    WishlistItem,
    LoginRequest,
    RecommendationItem,
    RegisterRequest,
    ReviewListResponse,
    StructuredReview,
    UserInfo,
    UserProfile,
)


class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"


app = FastAPI(
    title="NTU Course Recommendation API",
    description="台大個性化選課推薦系統 — 課程與 PTT 評價查詢",
    version="0.1.0",
    default_response_class=UTF8JSONResponse,
)


@app.on_event("startup")
def _startup() -> None:
    conn = _sqlite3.connect(DB_PATH)
    conn.row_factory = _sqlite3.Row
    try:
        init_auth_tables(conn)
        init_indices(conn)
    finally:
        conn.close()

# CORS: 從 env var ALLOWED_ORIGINS 讀 (comma-separated),沒設就允許本機 dev origin。
# 正式部署請設定環境變數明確列出允許的 origin。
_env_origins = os.environ.get("ALLOWED_ORIGINS", "").strip()
if _env_origins == "*":
    allow_origins = ["*"]
elif _env_origins:
    allow_origins = [o.strip() for o in _env_origins.split(",") if o.strip()]
else:
    allow_origins = [
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:5173",  # vite dev (將來如果用)
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/courses", response_model=CourseListResponse)
def list_courses(
    q: str | None = Query(None, description="關鍵字 (比對課名/教師/課號)"),
    dept: str | None = Query(None, description="開課系所完全比對"),
    credits: str | None = Query(None, description="學分數完全比對"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_conn),
) -> CourseListResponse:
    where: list[str] = []
    params: list[str | int] = []

    if q:
        where.append("(course_name LIKE ? OR teacher LIKE ? OR course_code LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])
    if dept:
        where.append("department = ?")
        params.append(dept)
    if credits:
        where.append("credits = ?")
        params.append(credits)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    total = conn.execute(
        f"SELECT COUNT(*) FROM courses {where_sql}", params
    ).fetchone()[0]

    rows = conn.execute(
        f"""
        SELECT serial_no, course_code, course_name, teacher,
               department, credits, schedule_time, language
        FROM courses
        {where_sql}
        ORDER BY course_code, serial_no
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()

    def _to_summary(r: sqlite3.Row) -> CourseSummary:
        d = dict(r)
        d["slots"] = [list(s) for s in parse_schedule(d.get("schedule_time"))]
        return CourseSummary(**d)

    return CourseListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[_to_summary(r) for r in rows],
    )


@app.get("/courses/{serial_no}", response_model=CourseDetail)
def get_course(
    serial_no: str,
    conn: sqlite3.Connection = Depends(get_conn),
) -> CourseDetail:
    row = conn.execute(
        "SELECT * FROM courses WHERE serial_no = ?", (serial_no,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"course {serial_no} not found")
    d = dict(row)
    d["slots"] = [list(s) for s in parse_schedule(d.get("schedule_time"))]
    return CourseDetail(**d)


@app.get("/courses/{serial_no}/related")
def related_courses(
    serial_no: str,
    limit: int = Query(5, ge=1, le=20),
    conn: sqlite3.Connection = Depends(get_conn),
) -> list[dict]:
    row = conn.execute(
        "SELECT 1 FROM courses WHERE serial_no = ?", (serial_no,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"course {serial_no} not found")
    return find_related_courses(serial_no, conn, limit=limit)


@app.get("/courses/{serial_no}/reviews", response_model=ReviewListResponse)
def get_course_reviews(
    serial_no: str,
    conn: sqlite3.Connection = Depends(get_conn),
) -> ReviewListResponse:
    course = conn.execute(
        "SELECT course_code FROM courses WHERE serial_no = ?", (serial_no,)
    ).fetchone()
    if course is None:
        raise HTTPException(status_code=404, detail=f"course {serial_no} not found")

    course_code = course["course_code"]
    rows = conn.execute(
        """
        SELECT * FROM reviews_structured
        WHERE course_id = ?
        ORDER BY post_date DESC
        """,
        (course_code,),
    ).fetchall()

    return ReviewListResponse(
        course_code=course_code,
        total=len(rows),
        items=[StructuredReview(**dict(r)) for r in rows],
    )


@app.get("/departments", response_model=list[str])
def list_departments(
    conn: sqlite3.Connection = Depends(get_conn),
) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT department FROM courses
        WHERE department != ''
        ORDER BY department
        """
    ).fetchall()
    return [r["department"] for r in rows]


@app.get("/teachers/{name}", response_model=TeacherDetail)
def get_teacher(
    name: str,
    conn: sqlite3.Connection = Depends(get_conn),
) -> TeacherDetail:
    name = name.strip()
    if not name:
        raise HTTPException(400, "teacher name 不可空白")

    # 一個 course_code 可能跨學期被同一教師開多次,以最新 (MAX(serial_no)) 為代表
    courses = conn.execute(
        """
        SELECT
            MAX(c.serial_no) AS serial_no,
            c.course_code,
            c.course_name,
            c.department,
            c.credits,
            COUNT(*) AS n_offerings,
            (SELECT COUNT(*) FROM reviews_structured r WHERE r.course_id = c.course_code) AS n_reviews
        FROM courses c
        WHERE c.teacher = ?
        GROUP BY c.course_code
        ORDER BY n_reviews DESC, c.course_code
        """,
        (name,),
    ).fetchall()

    if not courses:
        raise HTTPException(404, f"teacher '{name}' not found")

    course_codes = list({r["course_code"] for r in courses})
    placeholders = ",".join("?" * len(course_codes))
    agg = conn.execute(
        f"""
        SELECT
            COUNT(*) AS n_reviews,
            AVG(CAST(NULLIF(recommendation, '') AS REAL)) AS avg_rec,
            AVG(CAST(NULLIF(sweetness, '')      AS REAL)) AS avg_sweet,
            AVG(CAST(NULLIF(workload, '')       AS REAL)) AS avg_workload
        FROM reviews_structured
        WHERE course_id IN ({placeholders})
        """,
        course_codes,
    ).fetchone()

    stats = TeacherStats(
        n_courses=sum(r["n_offerings"] for r in courses),
        n_unique_codes=len(courses),
        n_reviews=agg["n_reviews"] or 0,
        avg_recommendation=round(agg["avg_rec"], 2) if agg["avg_rec"] is not None else None,
        avg_sweetness=round(agg["avg_sweet"], 2) if agg["avg_sweet"] is not None else None,
        avg_workload=round(agg["avg_workload"], 2) if agg["avg_workload"] is not None else None,
    )

    return TeacherDetail(
        teacher=name,
        stats=stats,
        courses=[
            TeacherCourseItem(
                serial_no=r["serial_no"],
                course_code=r["course_code"],
                course_name=r["course_name"],
                department=r["department"] or "",
                credits=r["credits"] or "",
                n_offerings=r["n_offerings"],
                n_reviews=r["n_reviews"],
            )
            for r in courses
        ],
    )


# =========================================================================
# Auth
# =========================================================================


def _row_to_user_info(row: sqlite3.Row) -> UserInfo:
    return UserInfo(id=row["id"], username=row["username"], created_at=row["created_at"])


@app.post("/auth/register", response_model=AuthResponse, status_code=201)
def register(
    body: RegisterRequest,
    conn: sqlite3.Connection = Depends(get_conn),
) -> AuthResponse:
    username = body.username.strip()
    if len(username) < 2:
        raise HTTPException(400, "username 至少 2 個字元")
    if len(body.password) < 6:
        raise HTTPException(400, "password 至少 6 個字元")

    exists = conn.execute(
        "SELECT 1 FROM users WHERE username = ?", (username,)
    ).fetchone()
    if exists:
        raise HTTPException(409, "username 已被使用")

    pw_hash, salt = hash_password(body.password)
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
        (username, pw_hash, salt),
    )
    user_id = cur.lastrowid
    token = new_token()
    conn.execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, datetime('now', '+30 days'))", (token, user_id)
    )
    conn.commit()

    row = conn.execute(
        "SELECT id, username, created_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    sess = conn.execute(
        "SELECT expires_at FROM sessions WHERE token = ?", (token,)
    ).fetchone()
    return AuthResponse(token=token, expires_at=sess["expires_at"], user=_row_to_user_info(row))


@app.post("/auth/login", response_model=AuthResponse)
def login(
    body: LoginRequest,
    request: Request,
    conn: sqlite3.Connection = Depends(get_conn),
) -> AuthResponse:
    check_login_rate_limit(request)
    row = conn.execute(
        "SELECT id, username, password_hash, salt, created_at FROM users WHERE username = ?",
        (body.username.strip(),),
    ).fetchone()
    if row is None or not verify_password(body.password, row["password_hash"], row["salt"]):
        raise HTTPException(401, "帳號或密碼錯誤")

    token = new_token()
    conn.execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, datetime('now', '+30 days'))", (token, row["id"])
    )
    conn.commit()
    sess = conn.execute(
        "SELECT expires_at FROM sessions WHERE token = ?", (token,)
    ).fetchone()
    return AuthResponse(token=token, expires_at=sess["expires_at"], user=_row_to_user_info(row))


@app.post("/auth/refresh", response_model=AuthResponse)
def refresh_session(
    authorization: str = Header(...),
    conn: sqlite3.Connection = Depends(get_conn),
    current: sqlite3.Row = Depends(get_current_user),
) -> AuthResponse:
    """延長現有 session token 的過期時間 (再 30 天)。
    依然回傳同一個 token,前端不用換 (但會拿到新的 expires_at)。"""
    token = authorization.removeprefix("Bearer ").strip()
    conn.execute(
        "UPDATE sessions SET expires_at = datetime('now', '+30 days') WHERE token = ?",
        (token,),
    )
    conn.commit()
    sess = conn.execute(
        "SELECT expires_at FROM sessions WHERE token = ?", (token,)
    ).fetchone()
    return AuthResponse(token=token, expires_at=sess["expires_at"], user=_row_to_user_info(current))


@app.post("/auth/logout", status_code=204)
def logout(
    authorization: str = Header(...),
    conn: sqlite3.Connection = Depends(get_conn),
    _current: sqlite3.Row = Depends(get_current_user),
) -> None:
    token = authorization.removeprefix("Bearer ").strip()
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()


@app.get("/auth/me", response_model=UserInfo)
def me(current: sqlite3.Row = Depends(get_current_user)) -> UserInfo:
    return _row_to_user_info(current)


# =========================================================================
# User profile (能力值 + 偏好)
# =========================================================================

import json as _json


def _row_to_profile(row: sqlite3.Row) -> UserProfile:
    return UserProfile(
        ability_logic=row["ability_logic"],
        ability_writing=row["ability_writing"],
        ability_coding=row["ability_coding"],
        ability_humanities=row["ability_humanities"],
        ability_teamwork=row["ability_teamwork"],
        pref_sweetness=row["pref_sweetness"],
        pref_loading=row["pref_loading"],
        interests=_json.loads(row["interests"]),
        updated_at=row["updated_at"],
    )


@app.get("/me/profile", response_model=UserProfile)
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
    return _row_to_profile(row)


@app.put("/me/profile", response_model=UserProfile)
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
    return _row_to_profile(row)


# =========================================================================
# Recommendations / fit-score
# =========================================================================


def _load_profile_dict(conn: sqlite3.Connection, user_id: int) -> dict:
    row = conn.execute(
        "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()
    return profile_row_to_dict(row)


@app.get("/me/recommendations", response_model=list[RecommendationItem])
def my_recommendations(
    limit: int = Query(5, ge=1, le=50),
    current: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> list[RecommendationItem]:
    profile = _load_profile_dict(conn, current["id"])
    stats_map = aggregate_course_stats(conn)
    if not stats_map:
        return []

    # 拿掉已修過的 course_code
    taken_codes = {
        r["course_code"]
        for r in conn.execute(
            """
            SELECT DISTINCT c.course_code
            FROM user_history h
            JOIN courses c ON c.serial_no = h.serial_no
            WHERE h.user_id = ?
            """,
            (current["id"],),
        ).fetchall()
    }

    # 對每個有評價的 course_code, 挑一個代表 serial_no (最新的 = 流水號最大)
    placeholders = ",".join("?" * len(stats_map))
    reps = conn.execute(
        f"""
        SELECT course_code, MAX(serial_no) AS serial_no,
               course_name, teacher, department, credits
        FROM courses
        WHERE course_code IN ({placeholders})
        GROUP BY course_code
        """,
        list(stats_map.keys()),
    ).fetchall()

    scored: list[tuple[float, RecommendationItem]] = []
    for r in reps:
        code = r["course_code"]
        if code in taken_codes:
            continue
        fit = compute_fit(profile, stats_map.get(code), r["serial_no"])
        scored.append((
            fit["total"],
            RecommendationItem(
                serial_no=r["serial_no"],
                course_code=code,
                course_name=r["course_name"],
                teacher=r["teacher"] or "",
                department=r["department"] or "",
                credits=r["credits"] or "",
                fit=FitBreakdown(**fit),
            ),
        ))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:limit]]


@app.get("/me/fit/{serial_no}", response_model=FitBreakdown)
def my_fit(
    serial_no: str,
    current: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> FitBreakdown:
    course = conn.execute(
        "SELECT course_code, course_name, department FROM courses WHERE serial_no = ?",
        (serial_no,),
    ).fetchone()
    if course is None:
        raise HTTPException(404, f"course {serial_no} not found")

    profile = _load_profile_dict(conn, current["id"])
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

    fit = compute_fit(profile, stats_dict, serial_no)
    return FitBreakdown(**fit)


@app.post("/me/fits", response_model=dict[str, FitBreakdown])
def my_fits_batch(
    serial_nos: list[str],
    current: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, FitBreakdown]:
    """批次拿一組 serial_no 的 fit (供探索頁表格用)。"""
    if not serial_nos:
        return {}
    placeholders = ",".join("?" * len(serial_nos))
    rows = conn.execute(
        f"""
        SELECT serial_no, course_code
        FROM courses
        WHERE serial_no IN ({placeholders})
        """,
        serial_nos,
    ).fetchall()

    profile = _load_profile_dict(conn, current["id"])
    stats_map = aggregate_course_stats(conn)

    out: dict[str, FitBreakdown] = {}
    for r in rows:
        fit = compute_fit(profile, stats_map.get(r["course_code"]), r["serial_no"])
        out[r["serial_no"]] = FitBreakdown(**fit)
    return out


# =========================================================================
# User history (修課歷史)
# =========================================================================


@app.get("/me/history", response_model=list[HistoryItem])
def list_my_history(
    current: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> list[HistoryItem]:
    rows = conn.execute(
        """
        SELECT h.id, h.serial_no, h.semester, h.grade, h.notes, h.added_at,
               c.course_code, c.course_name, c.teacher, c.credits, c.department
        FROM user_history h
        LEFT JOIN courses c ON c.serial_no = h.serial_no
        WHERE h.user_id = ?
        ORDER BY h.semester DESC, h.added_at DESC
        """,
        (current["id"],),
    ).fetchall()
    return [HistoryItem(**{k: (r[k] if r[k] is not None else "") for k in r.keys()}) for r in rows]


@app.post("/me/history", response_model=HistoryItem, status_code=201)
def add_to_history(
    body: HistoryAdd,
    current: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> HistoryItem:
    course = conn.execute(
        "SELECT 1 FROM courses WHERE serial_no = ?", (body.serial_no,)
    ).fetchone()
    if course is None:
        raise HTTPException(404, f"course {body.serial_no} not found")
    if not body.semester.strip():
        raise HTTPException(400, "semester 為必填")

    cur = conn.execute(
        """
        INSERT INTO user_history (user_id, serial_no, semester, grade, notes)
        VALUES (?, ?, ?, ?, ?)
        """,
        (current["id"], body.serial_no, body.semester.strip(),
         (body.grade or None), (body.notes or None)),
    )
    conn.commit()
    new_id = cur.lastrowid

    row = conn.execute(
        """
        SELECT h.id, h.serial_no, h.semester, h.grade, h.notes, h.added_at,
               c.course_code, c.course_name, c.teacher, c.credits, c.department
        FROM user_history h
        LEFT JOIN courses c ON c.serial_no = h.serial_no
        WHERE h.id = ?
        """,
        (new_id,),
    ).fetchone()
    return HistoryItem(**{k: (row[k] if row[k] is not None else "") for k in row.keys()})


@app.delete("/me/history/{history_id}", status_code=204)
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
        serial_no=row["serial_no"],
        notes=row["notes"],
        added_at=row["added_at"],
        course_code=row["course_code"] or "",
        course_name=row["course_name"] or "",
        teacher=row["teacher"] or "",
        credits=row["credits"] or "",
        department=row["department"] or "",
    )


@app.get("/me/wishlist", response_model=list[WishlistItem])
def list_my_wishlist(
    current: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> list[WishlistItem]:
    rows = conn.execute(
        """
        SELECT w.id, w.serial_no, w.notes, w.added_at,
               c.course_code, c.course_name, c.teacher, c.credits, c.department
        FROM user_wishlist w
        LEFT JOIN courses c ON c.serial_no = w.serial_no
        WHERE w.user_id = ?
        ORDER BY w.added_at DESC
        """,
        (current["id"],),
    ).fetchall()
    return [_wishlist_row_to_item(r) for r in rows]


@app.post("/me/wishlist", response_model=WishlistItem, status_code=201)
def add_to_wishlist(
    body: WishlistAdd,
    current: sqlite3.Row = Depends(get_current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> WishlistItem:
    course = conn.execute(
        "SELECT 1 FROM courses WHERE serial_no = ?", (body.serial_no,)
    ).fetchone()
    if course is None:
        raise HTTPException(404, f"course {body.serial_no} not found")

    try:
        cur = conn.execute(
            "INSERT INTO user_wishlist (user_id, serial_no, notes) VALUES (?, ?, ?)",
            (current["id"], body.serial_no, body.notes or None),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(409, "已在想修清單中")
    conn.commit()

    row = conn.execute(
        """
        SELECT w.id, w.serial_no, w.notes, w.added_at,
               c.course_code, c.course_name, c.teacher, c.credits, c.department
        FROM user_wishlist w
        LEFT JOIN courses c ON c.serial_no = w.serial_no
        WHERE w.id = ?
        """,
        (cur.lastrowid,),
    ).fetchone()
    return _wishlist_row_to_item(row)


@app.delete("/me/wishlist/{wishlist_id}", status_code=204)
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
