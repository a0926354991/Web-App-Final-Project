"""
單元測試 — auth 模組 (密碼 hash / 強度檢查 / 登入限流 / token)。

不碰 DB、不起 server,純測 backend.api.auth 的函式邏輯。
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.api import auth


# =========================================================================
# PBKDF2 密碼 hash
# =========================================================================


def test_hash_password_roundtrip():
    """同一密碼 hash 後能 verify 通過。"""
    pw_hash, salt = auth.hash_password("Secret123")
    assert auth.verify_password("Secret123", pw_hash, salt) is True


def test_verify_rejects_wrong_password():
    pw_hash, salt = auth.hash_password("Secret123")
    assert auth.verify_password("wrong-password", pw_hash, salt) is False


def test_hash_uses_random_salt_per_call():
    """同一密碼兩次 hash → salt 與 digest 都不同 (有隨機 salt)。"""
    h1, s1 = auth.hash_password("Secret123")
    h2, s2 = auth.hash_password("Secret123")
    assert s1 != s2
    assert h1 != h2
    # 但各自都能 verify
    assert auth.verify_password("Secret123", h1, s1)
    assert auth.verify_password("Secret123", h2, s2)


def test_hash_is_hex_and_uses_configured_iterations():
    pw_hash, salt = auth.hash_password("abcd1234")
    # 16-byte salt → 32 hex chars
    assert len(salt) == 32
    bytes.fromhex(salt)   # 不會 raise = 合法 hex
    bytes.fromhex(pw_hash)
    assert auth._PBKDF2_ITER == 200_000


# =========================================================================
# 密碼強度
# =========================================================================


def test_password_too_short_rejected():
    with pytest.raises(HTTPException) as exc:
        auth.validate_password_strength("ab12")
    assert exc.value.status_code == 400


def test_password_without_digit_rejected():
    with pytest.raises(HTTPException) as exc:
        auth.validate_password_strength("onlyletters")
    assert exc.value.status_code == 400


def test_password_without_letter_rejected():
    with pytest.raises(HTTPException) as exc:
        auth.validate_password_strength("12345678")
    assert exc.value.status_code == 400


def test_password_valid_passes():
    # 8 字元 + 含字母與數字 → 不 raise
    auth.validate_password_strength("abcd1234")


# =========================================================================
# token
# =========================================================================


def test_new_token_unique_and_urlsafe():
    t1, t2 = auth.new_token(), auth.new_token()
    assert t1 != t2
    assert len(t1) >= 32
    # token_urlsafe 只含 url-safe 字元
    assert all(c.isalnum() or c in "-_" for c in t1)


# =========================================================================
# 登入限流 (check_login_rate_limit)
# =========================================================================


class _FakeClient:
    def __init__(self, host):
        self.host = host


class _FakeRequest:
    def __init__(self, host="1.2.3.4"):
        self.client = _FakeClient(host)


def setup_function(_fn):
    """每個測試前清空限流計數,避免互相污染。"""
    auth._login_attempts.clear()


def test_rate_limit_allows_up_to_max():
    req = _FakeRequest("10.0.0.1")
    # 前 _LOGIN_RATE_MAX 次都應放行
    for _ in range(auth._LOGIN_RATE_MAX):
        auth.check_login_rate_limit(req, "alice")


def test_rate_limit_blocks_after_max():
    req = _FakeRequest("10.0.0.2")
    for _ in range(auth._LOGIN_RATE_MAX):
        auth.check_login_rate_limit(req, "bob")
    with pytest.raises(HTTPException) as exc:
        auth.check_login_rate_limit(req, "bob")
    assert exc.value.status_code == 429


def test_rate_limit_is_per_ip_username_pair():
    """不同 username (同 IP) 各自計數,不互相誤殺。"""
    req = _FakeRequest("10.0.0.3")
    for _ in range(auth._LOGIN_RATE_MAX):
        auth.check_login_rate_limit(req, "carol")
    # carol 已滿,但 dave 仍可登入
    auth.check_login_rate_limit(req, "dave")
