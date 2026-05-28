"""
FastAPI app — 課程查詢 / 評價檢索 API。

啟動：
    uvicorn backend.api.main:app --reload

互動式 docs：http://localhost:8000/docs
"""

from __future__ import annotations

import os
import sqlite3

# 載入專案根目錄的 .env (GEMINI_API_KEY 等)。必須在其他 os.environ 讀取前。
try:
    from dotenv import load_dotenv
    from pathlib import Path as _Path
    _env_path = _Path(__file__).resolve().parents[2] / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import (
    check_login_rate_limit,
    get_current_user,
    hash_password,
    init_auth_tables,
    new_token,
    validate_password_strength,
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
from . import ai_features
from .schedule import parse_schedule
from .schemas import (
    AuthResponse,
    CourseDetail,
    CourseListResponse,
    CourseSummary,
    FitBreakdown,
    FitsBatchRequest,
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


_DEPT_CODES: dict[str, str] = {}  # dept_name → code (e.g. "中國文學系" → "1010")


def _load_dept_codes() -> None:
    """載入 dept name → code mapping:
    - 學系代碼表.xls (大學部 80 個系)
    - dept_codes_institute.json (碩/博士班/研究所手動對應表)
    任一檔案不存在就跳過。"""
    from pathlib import Path
    import json as _json
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


@app.on_event("startup")
def _startup() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        init_auth_tables(conn)
        init_indices(conn)
    finally:
        conn.close()
    _load_dept_codes()

# CORS: 從 env var ALLOWED_ORIGINS 讀 (comma-separated)。
# - production (APP_ENV=production) 必須明確設定，否則啟動時 fail-fast，
#   避免漏設導致預設的 localhost 名單被部署到雲端
# - dev 沒設就用 localhost 預設值
_app_env = os.environ.get("APP_ENV", "development").strip().lower()
_env_origins = os.environ.get("ALLOWED_ORIGINS", "").strip()

if _app_env == "production":
    if not _env_origins:
        raise RuntimeError(
            "APP_ENV=production 必須設定 ALLOWED_ORIGINS 環境變數 "
            "(e.g. ALLOWED_ORIGINS=https://your.domain)"
        )
    if _env_origins == "*":
        raise RuntimeError("production 不允許 ALLOWED_ORIGINS=*,請列出明確的 origin")
    allow_origins = [o.strip() for o in _env_origins.split(",") if o.strip()]
elif _env_origins == "*":
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
    semester: str | None = Query(None, description="學期 (e.g. 114-1, 114-2)"),
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
        # 用 substring 比對,讓「中國文學系」也能找到「中國文學系 / 文學院」這種多系所合開
        where.append("department LIKE ?")
        params.append(f"%{dept}%")
    if semester:
        where.append("semester = ?")
        params.append(semester)
    if credits:
        where.append("credits = ?")
        params.append(credits)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    total = conn.execute(
        f"SELECT COUNT(*) FROM courses {where_sql}", params
    ).fetchone()[0]

    rows = conn.execute(
        f"""
        SELECT semester, serial_no, course_code, course_name, teacher,
               department, credits, schedule_time, location, language
        FROM courses
        {where_sql}
        ORDER BY semester DESC, course_code, serial_no
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()

    def _to_summary(r: sqlite3.Row) -> CourseSummary:
        d = dict(r)
        d["location"] = d.get("location") or ""  # DB 可能為 NULL
        d["slots"] = [list(s) for s in parse_schedule(d.get("schedule_time"))]
        return CourseSummary(**d)

    return CourseListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[_to_summary(r) for r in rows],
    )


@app.get("/courses/{semester}/{serial_no}", response_model=CourseDetail)
def get_course(
    semester: str,
    serial_no: str,
    conn: sqlite3.Connection = Depends(get_conn),
) -> CourseDetail:
    row = conn.execute(
        "SELECT * FROM courses WHERE semester = ? AND serial_no = ?",
        (semester, serial_no),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"course {semester}/{serial_no} not found")
    d = {k: (v if v is not None else "") for k, v in dict(row).items()}
    d["slots"] = [list(s) for s in parse_schedule(d.get("schedule_time"))]
    return CourseDetail(**d)


@app.get("/courses/{semester}/{serial_no}/related")
def related_courses(
    semester: str,
    serial_no: str,
    limit: int = Query(5, ge=1, le=20),
    conn: sqlite3.Connection = Depends(get_conn),
) -> list[dict]:
    row = conn.execute(
        "SELECT 1 FROM courses WHERE semester = ? AND serial_no = ?",
        (semester, serial_no),
    ).fetchone()
    if row is None:
        raise HTTPException(404, f"course {semester}/{serial_no} not found")
    return find_related_courses((semester, serial_no), conn, limit=limit)


@app.get("/courses/{semester}/{serial_no}/reviews", response_model=ReviewListResponse)
def get_course_reviews(
    semester: str,
    serial_no: str,
    conn: sqlite3.Connection = Depends(get_conn),
) -> ReviewListResponse:
    course = conn.execute(
        "SELECT course_code FROM courses WHERE semester = ? AND serial_no = ?",
        (semester, serial_no),
    ).fetchone()
    if course is None:
        raise HTTPException(status_code=404, detail=f"course {semester}/{serial_no} not found")

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


@app.get("/departments", response_model=list[dict])
def list_departments(
    conn: sqlite3.Connection = Depends(get_conn),
) -> list[dict]:
    """回傳系所代碼表內、且實際出現在 courses 表的單一系所 [{name, code}]。
    多系所合開的字串 (e.g. "A / B") 不會直接列出,但 dept filter 用 substring 比對,
    所以選「法律學系」就能找到「中國大陸研究學程 / 法律學系 / ...」這類。"""
    out = []
    for name, code in _DEPT_CODES.items():
        # 確認該系所實際有出現在 courses 表 (含多系所合開的 substring)
        row = conn.execute(
            "SELECT 1 FROM courses WHERE department LIKE ? LIMIT 1",
            (f"%{name}%",),
        ).fetchone()
        if row:
            out.append({"name": name, "code": code})
    # 沒代碼但常見的「研究所 / 學程」也補進來(出現課程數 >= 20 的)
    rows = conn.execute(
        """
        SELECT department, COUNT(*) AS n FROM courses
        WHERE department != '' AND department NOT LIKE '% / %'
        GROUP BY department
        HAVING n >= 20
        """
    ).fetchall()
    seen = {d["name"] for d in out}
    for r in rows:
        if r["department"] not in seen:
            out.append({"name": r["department"], "code": ""})
    out.sort(key=lambda d: (d["code"] == "", d["code"], d["name"]))
    return out


@app.get("/teachers/{name}", response_model=TeacherDetail)
def get_teacher(
    name: str,
    conn: sqlite3.Connection = Depends(get_conn),
) -> TeacherDetail:
    name = name.strip()
    if not name:
        raise HTTPException(400, "teacher name 不可空白")

    # 一個 course_code 可能跨學期被同一教師開多次,挑最新學期的代表
    courses = conn.execute(
        """
        SELECT
            (SELECT semester FROM courses
             WHERE teacher = ? AND course_code = c.course_code
             ORDER BY semester DESC, serial_no DESC LIMIT 1) AS semester,
            (SELECT serial_no FROM courses
             WHERE teacher = ? AND course_code = c.course_code
             ORDER BY semester DESC, serial_no DESC LIMIT 1) AS serial_no,
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
        (name, name, name),
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
                semester=r["semester"],
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
    validate_password_strength(body.password)

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
    username = body.username.strip()
    check_login_rate_limit(request, username)
    row = conn.execute(
        "SELECT id, username, password_hash, salt, created_at FROM users WHERE username = ?",
        (username,),
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
    from concurrent.futures import ThreadPoolExecutor

    top = scored[:limit]

    def _enrich(r: dict, fit: dict) -> RecommendationItem:
        course_key = (r["semester"], r["serial_no"])
        llm_fit = compute_fit(
            profile, stats_map.get(r["course_code"]), course_key,
            use_llm=True,
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


@app.get("/me/fit/{semester}/{serial_no}", response_model=FitBreakdown)
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


@app.post("/me/fits", response_model=dict[str, FitBreakdown])
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

    profile = _load_profile_dict(conn, current["id"])
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


@app.get("/me/history", response_model=list[HistoryItem])
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


@app.post("/me/history", response_model=HistoryItem, status_code=201)
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


@app.get("/me/wishlist", response_model=list[WishlistItem])
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


@app.post("/me/wishlist", response_model=WishlistItem, status_code=201)
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


# =========================================================================
# AI features (LLM-powered)
# =========================================================================


@app.get("/me/courses/{semester}/{serial_no}/summary")
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

    profile = _load_profile_dict(conn, current["id"])
    text = ai_features.personalized_course_summary(profile, dict(course), stats)
    return {"summary": text}


@app.post("/me/history/{history_id}/summarize")
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


@app.get("/me/courses/{semester}/{serial_no}/substitutes")
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


@app.post("/me/schedule/balance")
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
        from .recommendations import _CACHE as _rec_cache
        prof = _rec_cache.get("ability_profile", {}).get((sem, sno), {})
        c["ability_axes"] = [a for a, w in sorted(prof.items(), key=lambda kv: -kv[1]) if w > 0][:3]
        courses_input.append(c)

    profile = _load_profile_dict(conn, current["id"])
    advice = ai_features.schedule_balance_advice(courses_input, profile)
    return {"advice": advice}


@app.get("/me/suggested-interests")
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


@app.get("/teachers/{name}/style")
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


@app.get("/courses/{semester}/{serial_no}/prerequisites")
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
