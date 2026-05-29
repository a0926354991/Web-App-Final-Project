"""
FastAPI app — 課程查詢 / 評價檢索 / 推薦 / AI 功能 API。

啟動：
    uvicorn backend.api.main:app --reload

互動式 docs：http://localhost:8000/docs

組裝結構 (route handler 拆在 routers/ 底下):
    routers/courses.py  公開課程 / 評價 / 教師 / 系所
    routers/auth.py     註冊 / 登入 / 登出 / refresh / me
    routers/me.py       profile / 推薦 / 適合度 / 修課歷史 / 想修清單 (需 auth)
    routers/ai.py       9 個 LLM-powered AI 功能
共用 helper 在 deps.py。main.py 只負責建 app、設 CORS、startup、include router。
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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import init_auth_tables
from .db import DB_PATH
from .deps import load_dept_codes
from .recommendations import init_indices
from .routers import ai, auth, courses, me


class UTF8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"


app = FastAPI(
    title="NTU Course Recommendation API",
    description="台大個性化選課推薦系統 — 課程與 PTT 評價查詢",
    version="0.1.0",
    default_response_class=UTF8JSONResponse,
)


@app.on_event("startup")
def _startup() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        init_auth_tables(conn)
        init_indices(conn)
    finally:
        conn.close()
    load_dept_codes()


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


# Route handlers 全部拆在 routers/ 底下,在此 include。
# 順序維持與重構前一致:courses → auth → me → ai。
app.include_router(courses.router)
app.include_router(auth.router)
app.include_router(me.router)
app.include_router(ai.router)
