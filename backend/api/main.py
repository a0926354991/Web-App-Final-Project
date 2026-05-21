"""
FastAPI app — 課程查詢 / 評價檢索 API。

啟動：
    uvicorn backend.api.main:app --reload

互動式 docs：http://localhost:8000/docs
"""

from __future__ import annotations

import sqlite3

import sqlite3 as _sqlite3

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import (
    get_current_user,
    hash_password,
    init_auth_tables,
    new_token,
    verify_password,
)
from .db import DB_PATH, get_conn
from .schemas import (
    AuthResponse,
    CourseDetail,
    CourseListResponse,
    CourseSummary,
    LoginRequest,
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
    try:
        init_auth_tables(conn)
    finally:
        conn.close()

# 前端目前是靜態檔，先全開 CORS 方便開發
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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

    return CourseListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[CourseSummary(**dict(r)) for r in rows],
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
    return CourseDetail(**dict(row))


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
        "INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, user_id)
    )
    conn.commit()

    row = conn.execute(
        "SELECT id, username, created_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    return AuthResponse(token=token, user=_row_to_user_info(row))


@app.post("/auth/login", response_model=AuthResponse)
def login(
    body: LoginRequest,
    conn: sqlite3.Connection = Depends(get_conn),
) -> AuthResponse:
    row = conn.execute(
        "SELECT id, username, password_hash, salt, created_at FROM users WHERE username = ?",
        (body.username.strip(),),
    ).fetchone()
    if row is None or not verify_password(body.password, row["password_hash"], row["salt"]):
        raise HTTPException(401, "帳號或密碼錯誤")

    token = new_token()
    conn.execute(
        "INSERT INTO sessions (token, user_id) VALUES (?, ?)", (token, row["id"])
    )
    conn.commit()
    return AuthResponse(token=token, user=_row_to_user_info(row))


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
