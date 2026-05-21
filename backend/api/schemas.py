"""Pydantic response models."""

from __future__ import annotations

from pydantic import BaseModel


class CourseSummary(BaseModel):
    serial_no: str
    course_code: str
    course_name: str
    teacher: str
    department: str
    credits: str
    schedule_time: str
    language: str


class CourseDetail(CourseSummary):
    course_identifier: str
    req_type: str
    location: str
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
