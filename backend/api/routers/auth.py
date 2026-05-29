"""
認證 router:
- /auth/register  註冊
- /auth/login     登入 (含 rate limit)
- /auth/refresh   延長 session
- /auth/logout    登出
- /auth/me        取得目前使用者

從 main.py 原樣搬出,路徑與回傳不變。
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ..auth import (
    check_login_rate_limit,
    get_current_user,
    hash_password,
    new_token,
    validate_password_strength,
    verify_password,
)
from ..db import get_conn
from ..deps import row_to_user_info
from ..schemas import AuthResponse, LoginRequest, RegisterRequest, UserInfo

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=201)
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
    return AuthResponse(token=token, expires_at=sess["expires_at"], user=row_to_user_info(row))


@router.post("/login", response_model=AuthResponse)
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
    return AuthResponse(token=token, expires_at=sess["expires_at"], user=row_to_user_info(row))


@router.post("/refresh", response_model=AuthResponse)
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
    return AuthResponse(token=token, expires_at=sess["expires_at"], user=row_to_user_info(current))


@router.post("/logout", status_code=204)
def logout(
    authorization: str = Header(...),
    conn: sqlite3.Connection = Depends(get_conn),
    _current: sqlite3.Row = Depends(get_current_user),
) -> None:
    token = authorization.removeprefix("Bearer ").strip()
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()


@router.get("/me", response_model=UserInfo)
def me(current: sqlite3.Row = Depends(get_current_user)) -> UserInfo:
    return row_to_user_info(current)
