"""
FastAPI app — 課程查詢 / 評價檢索 API。

啟動：
    uvicorn backend.api.main:app --reload

互動式 docs：http://localhost:8000/docs
"""

from __future__ import annotations

import sqlite3

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .db import get_conn
from .schemas import (
    CourseDetail,
    CourseListResponse,
    CourseSummary,
    ReviewListResponse,
    StructuredReview,
)


class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"


app = FastAPI(
    title="NTU Course Recommendation API",
    description="台大個性化選課推薦系統 — 課程與 PTT 評價查詢",
    version="0.1.0",
    default_response_class=UTF8JSONResponse,
)

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
