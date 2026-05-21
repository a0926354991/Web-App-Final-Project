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

from fastapi import Depends, Header, HTTPException, status

from .db import get_conn

_PBKDF2_ITER = 200_000


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
    conn.commit()


def get_current_user(
    authorization: str | None = Header(None),
    conn: sqlite3.Connection = Depends(get_conn),
) -> sqlite3.Row:
    """FastAPI dependency — 從 Authorization header 解析 token，回傳 user row 或 401。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()

    row = conn.execute(
        """
        SELECT u.id, u.username, u.created_at
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token = ?
        """,
        (token,),
    ).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")
    return row
