"""
Auth：密碼 hash + session token。

設計：
- 密碼用 PBKDF2-HMAC-SHA256 + 16-byte salt + 200k iterations（stdlib，不加額外套件）。
- Token 用 secrets.token_urlsafe(32)，存 sessions 表。
- Authorization header: "Bearer <token>"。
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import time
from collections import defaultdict, deque

from fastapi import Depends, Header, HTTPException, Request, status

from .db import get_conn

_PBKDF2_ITER = 200_000

# Session 有效期 (秒) — 30 天
SESSION_TTL_SECONDS = 30 * 24 * 3600

# Login rate limit: 同一 IP 60 秒內超過 N 次 → 429
_LOGIN_RATE_WINDOW = 60.0
_LOGIN_RATE_MAX = 8
_login_attempts: dict[str, deque[float]] = defaultdict(deque)


def hash_password(password: str) -> tuple[str, str]:
    """回傳 (hex_hash, hex_salt)。"""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITER)
    return digest.hex(), salt.hex()


def verify_password(password: str, hex_hash: str, hex_salt: str) -> bool:
    salt = bytes.fromhex(hex_salt)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITER)
    return secrets.compare_digest(digest.hex(), hex_hash)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def init_auth_tables(conn: sqlite3.Connection) -> None:
    """idempotent — 在 app startup 呼叫，已存在則不動。"""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt          TEXT NOT NULL,
            created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token      TEXT PRIMARY KEY,
            user_id    INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT NOT NULL DEFAULT (datetime('now', '+30 days')),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);

        CREATE TABLE IF NOT EXISTS user_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            serial_no  TEXT NOT NULL,
            semester   TEXT NOT NULL,
            grade      TEXT,
            notes      TEXT,
            added_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_history_user ON user_history(user_id);

        CREATE TABLE IF NOT EXISTS user_wishlist (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            serial_no  TEXT NOT NULL,
            notes      TEXT,
            added_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, serial_no),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_wishlist_user ON user_wishlist(user_id);

        -- LLM-tagged ability profile per course_code (optional, fallback to keyword mapping if empty)
        CREATE TABLE IF NOT EXISTS course_ability (
            course_code TEXT PRIMARY KEY,
            logic       INTEGER NOT NULL DEFAULT 0,
            writing     INTEGER NOT NULL DEFAULT 0,
            coding      INTEGER NOT NULL DEFAULT 0,
            humanities  INTEGER NOT NULL DEFAULT 0,
            teamwork    INTEGER NOT NULL DEFAULT 0,
            updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id            INTEGER PRIMARY KEY,
            ability_logic      INTEGER NOT NULL DEFAULT 50,
            ability_writing    INTEGER NOT NULL DEFAULT 50,
            ability_coding     INTEGER NOT NULL DEFAULT 50,
            ability_humanities INTEGER NOT NULL DEFAULT 50,
            ability_teamwork   INTEGER NOT NULL DEFAULT 50,
            pref_sweetness     INTEGER NOT NULL DEFAULT 50,
            pref_loading       INTEGER NOT NULL DEFAULT 50,
            interests          TEXT NOT NULL DEFAULT '[]',
            updated_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
    )
    # Migration: 舊 sessions 表如果沒有 expires_at,加上去
    cols = {r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    if "expires_at" not in cols:
        conn.execute(
            "ALTER TABLE sessions ADD COLUMN expires_at TEXT NOT NULL DEFAULT '2099-12-31 00:00:00'"
        )
        # 舊 session 立刻補 30 天過期
        conn.execute(
            "UPDATE sessions SET expires_at = datetime(created_at, '+30 days')"
        )
    conn.commit()


def get_current_user(
    authorization: str | None = Header(None),
    conn: sqlite3.Connection = Depends(get_conn),
) -> sqlite3.Row:
    """FastAPI dependency — 從 Authorization header 解析 token,回傳 user row 或 401。
    過期的 token 會被刪除並回 401。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()

    row = conn.execute(
        """
        SELECT u.id, u.username, u.created_at, s.expires_at
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token = ?
        """,
        (token,),
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")

    # 過期 → 刪掉 + 401
    expired = conn.execute(
        "SELECT 1 WHERE datetime(?) < datetime('now')", (row["expires_at"],)
    ).fetchone()
    if expired:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session expired, please log in again")
    return row


def check_login_rate_limit(request: Request) -> None:
    """同一 client IP 60 秒內最多 _LOGIN_RATE_MAX 次 login 嘗試。"""
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    q = _login_attempts[ip]
    while q and now - q[0] > _LOGIN_RATE_WINDOW:
        q.popleft()
    if len(q) >= _LOGIN_RATE_MAX:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"login attempts exceeded, please wait {_LOGIN_RATE_WINDOW:.0f} seconds",
        )
    q.append(now)
