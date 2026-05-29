"""
API 層整合測試 — 用 FastAPI TestClient 打真實 endpoint。

關鍵:不碰真實 app.db。用 tmp_path 起一個乾淨的小 SQLite,
override get_conn dependency,並 seed 最小 courses / reviews 資料。
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.api import auth as auth_mod
from backend.api.db import get_conn
from backend.api.main import app


# --- 最小 courses / reviews schema + 一筆資料,讓需要課程的 endpoint 能跑 ----

_SEED_SQL = """
CREATE TABLE courses (
    semester TEXT NOT NULL, serial_no TEXT NOT NULL, course_code TEXT,
    course_identifier TEXT, course_name TEXT, teacher TEXT, req_type TEXT,
    department TEXT, schedule_time TEXT, location TEXT, signup_class TEXT,
    language TEXT, credits TEXT, enrollment_cap TEXT, overview TEXT,
    objectives TEXT, requirements TEXT, grading TEXT, notes TEXT,
    expected_hours TEXT, detail_url TEXT,
    PRIMARY KEY (semester, serial_no)
);
CREATE TABLE reviews_structured (
    custom_id TEXT PRIMARY KEY, course_id TEXT, course_name TEXT, teacher TEXT,
    post_url TEXT, post_title TEXT, post_date TEXT, post_tag TEXT, year_term TEXT,
    has_template TEXT, recommendation TEXT, sweetness TEXT, workload TEXT,
    teaching_style TEXT, grading_method TEXT, summary TEXT
);
INSERT INTO courses (semester, serial_no, course_code, course_name, teacher,
                     department, credits, schedule_time, location, language)
VALUES ('114-2', '99999', 'TEST101', '測試課程', '王老師',
        '資訊工程學系', '3', '一 3,4', '資 101', '中文');
"""


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    auth_mod.init_auth_tables(conn)   # users / sessions / profiles / history / wishlist
    conn.executescript(_SEED_SQL)
    conn.commit()
    conn.close()

    def _override_get_conn():
        c = sqlite3.connect(db_path, check_same_thread=False)
        c.row_factory = sqlite3.Row
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[get_conn] = _override_get_conn
    auth_mod._login_attempts.clear()  # 避免被其他測試的限流計數污染
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()


# =========================================================================
# 基本健康檢查
# =========================================================================


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# =========================================================================
# 註冊 / 登入 / me
# =========================================================================


def test_register_returns_token_and_user(client):
    r = client.post("/auth/register", json={"username": "alice", "password": "Secret123"})
    assert r.status_code == 201
    body = r.json()
    assert body["token"]
    assert body["user"]["username"] == "alice"


def test_register_rejects_weak_password(client):
    r = client.post("/auth/register", json={"username": "bob", "password": "weak"})
    assert r.status_code == 400


def test_register_duplicate_username_conflicts(client):
    client.post("/auth/register", json={"username": "carol", "password": "Secret123"})
    r = client.post("/auth/register", json={"username": "carol", "password": "Secret123"})
    assert r.status_code == 409


def test_login_success_and_wrong_password(client):
    client.post("/auth/register", json={"username": "dave", "password": "Secret123"})
    ok = client.post("/auth/login", json={"username": "dave", "password": "Secret123"})
    assert ok.status_code == 200
    assert ok.json()["token"]

    bad = client.post("/auth/login", json={"username": "dave", "password": "WrongPass1"})
    assert bad.status_code == 401


def test_login_rate_limit_returns_429(client):
    client.post("/auth/register", json={"username": "erin", "password": "Secret123"})
    # 連續打錯密碼 — 超過上限後應 429 (而非一直 401)
    statuses = []
    for _ in range(auth_mod._LOGIN_RATE_MAX + 2):
        r = client.post("/auth/login", json={"username": "erin", "password": "WrongPass1"})
        statuses.append(r.status_code)
    assert 429 in statuses


def test_me_requires_auth(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer bogus"}).status_code == 401


def test_me_with_valid_token(client):
    tok = client.post("/auth/register",
                      json={"username": "frank", "password": "Secret123"}).json()["token"]
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json()["username"] == "frank"


def test_logout_invalidates_token(client):
    tok = client.post("/auth/register",
                      json={"username": "grace", "password": "Secret123"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.post("/auth/logout", headers=h).status_code == 204
    # 登出後同一 token 應失效
    assert client.get("/auth/me", headers=h).status_code == 401


# =========================================================================
# Profile upsert
# =========================================================================


def _auth_headers(client, username):
    tok = client.post("/auth/register",
                      json={"username": username, "password": "Secret123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_profile_default_then_upsert(client):
    h = _auth_headers(client, "heidi")
    # 第一次拿 → 預設值 (ability 50)
    r = client.get("/me/profile", headers=h)
    assert r.status_code == 200
    assert r.json()["ability_logic"] == 50

    # upsert
    payload = {
        "ability_logic": 90, "ability_writing": 30, "ability_coding": 80,
        "ability_humanities": 40, "ability_teamwork": 60,
        "pref_sweetness": 70, "pref_loading": 20, "interests": ["AI", "金融"],
    }
    put = client.put("/me/profile", json=payload, headers=h)
    assert put.status_code == 200
    assert put.json()["ability_logic"] == 90
    assert put.json()["interests"] == ["AI", "金融"]

    # 再讀回 → 持久化成功
    again = client.get("/me/profile", headers=h)
    assert again.json()["ability_coding"] == 80


# =========================================================================
# 修課歷史 / 想修清單 (對課程外鍵驗證)
# =========================================================================


def test_history_add_list_delete(client):
    h = _auth_headers(client, "ivan")
    add = client.post("/me/history",
                      json={"semester": "114-2", "serial_no": "99999", "grade": "A+", "notes": "讚"},
                      headers=h)
    assert add.status_code == 201
    hid = add.json()["id"]
    assert add.json()["course_name"] == "測試課程"   # LEFT JOIN courses 帶出課名

    lst = client.get("/me/history", headers=h)
    assert lst.status_code == 200
    assert any(item["id"] == hid for item in lst.json())

    assert client.delete(f"/me/history/{hid}", headers=h).status_code == 204


def test_history_rejects_unknown_course(client):
    h = _auth_headers(client, "judy")
    r = client.post("/me/history",
                    json={"semester": "114-2", "serial_no": "00000"},
                    headers=h)
    assert r.status_code == 404


def test_history_duplicate_conflicts(client):
    h = _auth_headers(client, "kate")
    body = {"semester": "114-2", "serial_no": "99999"}
    assert client.post("/me/history", json=body, headers=h).status_code == 201
    assert client.post("/me/history", json=body, headers=h).status_code == 409


def test_wishlist_add_and_delete(client):
    h = _auth_headers(client, "leo")
    add = client.post("/me/wishlist",
                      json={"semester": "114-2", "serial_no": "99999"}, headers=h)
    assert add.status_code == 201
    wid = add.json()["id"]
    assert any(i["id"] == wid for i in client.get("/me/wishlist", headers=h).json())
    assert client.delete(f"/me/wishlist/{wid}", headers=h).status_code == 204


def test_me_endpoints_require_auth(client):
    """所有 /me/* 沒帶 token → 401。"""
    assert client.get("/me/profile").status_code == 401
    assert client.get("/me/history").status_code == 401
    assert client.get("/me/wishlist").status_code == 401
    assert client.get("/me/recommendations").status_code == 401


# =========================================================================
# 公開課程 endpoint
# =========================================================================


def test_list_courses_and_search(client):
    r = client.get("/courses")
    assert r.status_code == 200
    assert r.json()["total"] >= 1

    hit = client.get("/courses", params={"q": "測試"})
    assert hit.json()["total"] == 1
    assert hit.json()["items"][0]["course_name"] == "測試課程"


def test_get_course_detail_and_404(client):
    ok = client.get("/courses/114-2/99999")
    assert ok.status_code == 200
    assert ok.json()["course_code"] == "TEST101"
    # slot 由 schedule.parse_schedule 解析「一 3,4」
    assert ok.json()["slots"]

    assert client.get("/courses/114-2/00000").status_code == 404


def test_teacher_404_for_unknown(client):
    assert client.get("/teachers/不存在的老師").status_code == 404
