"""
公開課程查詢 router:
- /courses              列表 + 搜尋 + 篩選 + 分頁
- /courses/{sem}/{sno}  單堂課詳情
- /courses/.../related  相關課程 (CF + content hybrid)
- /courses/.../reviews  該課的 PTT 結構化評價
- /departments          系所列表
- /teachers/{name}      教師概覽 + 統計

全部無需 auth。從 main.py 原樣搬出,路徑與回傳不變。
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from ..db import get_conn
from ..deps import dept_codes
from ..recommendations import find_related_courses
from ..schedule import parse_schedule
from ..schemas import (
    CourseDetail,
    CourseListResponse,
    CourseSummary,
    ReviewListResponse,
    StructuredReview,
    TeacherCourseItem,
    TeacherDetail,
    TeacherStats,
)

router = APIRouter(tags=["courses"])


@router.get("/courses", response_model=CourseListResponse)
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


@router.get("/courses/{semester}/{serial_no}", response_model=CourseDetail)
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


@router.get("/courses/{semester}/{serial_no}/related")
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


@router.get("/courses/{semester}/{serial_no}/reviews", response_model=ReviewListResponse)
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


@router.get("/departments", response_model=list[dict])
def list_departments(
    conn: sqlite3.Connection = Depends(get_conn),
) -> list[dict]:
    """回傳系所代碼表內、且實際出現在 courses 表的單一系所 [{name, code}]。
    多系所合開的字串 (e.g. "A / B") 不會直接列出,但 dept filter 用 substring 比對,
    所以選「法律學系」就能找到「中國大陸研究學程 / 法律學系 / ...」這類。"""
    out = []
    for name, code in dept_codes().items():
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


@router.get("/teachers/{name}", response_model=TeacherDetail)
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
