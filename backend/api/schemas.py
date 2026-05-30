"""Pydantic response models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CourseSummary(BaseModel):
    semester: str
    serial_no: str
    course_code: str
    course_name: str
    teacher: str
    department: str
    credits: str
    schedule_time: str
    location: str = ""
    language: str
    slots: list[list] = []  # parsed schedule: [[weekday_int, "period_str"], ...]


class CourseDetail(CourseSummary):
    course_identifier: str
    req_type: str
    signup_class: str
    enrollment_cap: str
    overview: str
    objectives: str
    requirements: str
    grading: str
    notes: str
    expected_hours: str
    detail_url: str


class CourseListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[CourseSummary]


class StructuredReview(BaseModel):
    custom_id: str
    course_id: str
    course_name: str
    teacher: str
    post_url: str
    post_title: str
    post_date: str
    post_tag: str
    year_term: str
    has_template: str
    recommendation: str
    sweetness: str
    workload: str
    teaching_style: str
    grading_method: str
    summary: str


class ReviewListResponse(BaseModel):
    course_code: str
    total: int
    items: list[StructuredReview]


# ---- Auth ----


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    token: str
    expires_at: str | None = None
    user: "UserInfo"


class UserInfo(BaseModel):
    id: int
    username: str
    created_at: str


AuthResponse.model_rebuild()


# ---- Recommendations / fit ----


class FitBreakdown(BaseModel):
    total: float
    recommendation: float
    sweetness: float
    loading: float
    interest: float
    ability: float
    n_reviews: int
    is_estimated: bool = False  # True = 甜度/loading/推薦是冷啟動代理值,非本課真實評價
    matched_interests: list[str] = []
    required_abilities: list[str] = []
    explanation: str = ""


class CourseRef(BaseModel):
    """(semester, serial_no) 對應到一筆 course offering;用於批次 fit 等。"""
    semester: str
    serial_no: str


class FitsBatchRequest(BaseModel):
    items: list[CourseRef]


class FillRecommendRequest(BaseModel):
    """空堂填補推薦：傳入已佔用的時段，回傳不衝堂且適合度最高的推薦。"""
    occupied_slots: list[list] = Field(default_factory=list, description="[[weekday_int, period_str], ...]")
    limit: int = Field(10, ge=1, le=30)


class RecommendationItem(BaseModel):
    semester: str
    serial_no: str
    course_code: str
    course_name: str
    teacher: str
    department: str
    credits: str
    fit: FitBreakdown


class TeacherStats(BaseModel):
    n_courses: int
    n_unique_codes: int
    n_reviews: int
    avg_recommendation: float | None
    avg_sweetness: float | None
    avg_workload: float | None


class TeacherCourseItem(BaseModel):
    semester: str
    serial_no: str
    course_code: str
    course_name: str
    department: str
    credits: str
    n_offerings: int
    n_reviews: int


class TeacherDetail(BaseModel):
    teacher: str
    stats: TeacherStats
    courses: list[TeacherCourseItem]


# ---- User history ----


class HistoryAdd(BaseModel):
    """新增修課歷史。(semester, serial_no) 一起識別一筆 course offering。"""
    semester: str
    serial_no: str
    grade: str | None = None
    notes: str | None = None


class HistoryItem(BaseModel):
    id: int
    semester: str
    serial_no: str
    grade: str | None
    notes: str | None
    added_at: str
    course_code: str
    course_name: str
    teacher: str
    credits: str
    department: str


# ---- Wishlist ----


class WishlistAdd(BaseModel):
    semester: str
    serial_no: str
    notes: str | None = None


class WishlistItem(BaseModel):
    id: int
    semester: str
    serial_no: str
    notes: str | None
    added_at: str
    course_code: str
    course_name: str
    teacher: str
    credits: str
    department: str


# ---- User profile ----


class UserProfile(BaseModel):
    ability_logic: int = Field(50, ge=0, le=100)
    ability_writing: int = Field(50, ge=0, le=100)
    ability_coding: int = Field(50, ge=0, le=100)
    ability_humanities: int = Field(50, ge=0, le=100)
    ability_teamwork: int = Field(50, ge=0, le=100)
    pref_sweetness: int = Field(50, ge=0, le=100)
    pref_loading: int = Field(50, ge=0, le=100)
    interests: list[str] = Field(default_factory=list)
    # 適合度成份權重 (0-100 importance,後端 normalize)。預設對應原本固定權重 25/20/20/20/15
    weight_recommendation: int = Field(25, ge=0, le=100)
    weight_sweetness: int = Field(20, ge=0, le=100)
    weight_loading: int = Field(20, ge=0, le=100)
    weight_interest: int = Field(20, ge=0, le=100)
    weight_ability: int = Field(15, ge=0, le=100)
    updated_at: str | None = None
