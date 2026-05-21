# 台大個性化選課推薦與分析

NTU Personalized Course Recommendation — Web 應用程式期末專案。

從台大課程網爬全校 8,467 門課，從 PTT NTUcourse 板爬 4,265 篇修課心得，
用 Claude API 結構化評價，再依使用者偏好計算「適合度」推薦課程。

---

## 功能總覽

| 功能 | 說明 |
|---|---|
| 註冊 / 登入 | 自製 session token auth（PBKDF2 密碼 hash）|
| 課程探索 | 搜尋（課名/教師/課號）+ 系所/學分篩選 + 分頁 |
| 課程詳情 | 完整課綱 + PTT 結構化評價（推薦分數 / 甜度 / loading / 摘要 / 原文連結）|
| 使用者資訊 | 5 軸能力 + 甜度偏好 + loading 偏好 + 興趣 tag |
| 修課歷史 | 紀錄學期 + 成績 + 筆記；探索頁顯示「已修」狀態 |
| 個性化推薦 | 4 成份加權算「適合度 %」，顯示於儀表板 / 探索表格 / 詳情抽屜 / 分析頁 |

## 技術棧

- **後端**：Python 3.11+, FastAPI, SQLite (stdlib `sqlite3`)
- **資料管線**：Playwright（爬課程網）, requests + BeautifulSoup（爬 PTT）,
  Anthropic Batch API（LLM 結構化）
- **前端**：純 HTML + CSS + Vanilla JS，Chart.js 畫雷達圖
- **無框架**：沒用 React/Vue 是刻意的（簡化部署 + 顯示原生 web 技能）

---

## 專案結構

```
.
├── backend/
│   ├── api/                    # FastAPI app
│   │   ├── main.py             # 所有 endpoint
│   │   ├── auth.py             # PBKDF2 hash + session token
│   │   ├── recommendations.py  # 適合度演算法
│   │   ├── db.py               # SQLite 連線
│   │   └── schemas.py          # Pydantic models
│   ├── scripts/
│   │   └── ingest_csv.py       # CSV → SQLite 一次性灌資料
│   ├── data/                   # CSV (gitignored: app.db)
│   ├── Web-crawler.py          # 台大課程網 Playwright 爬蟲
│   ├── ptt_review_crawler.py   # PTT NTUcourse 板爬蟲
│   ├── regex_structure_reviews.py   # Regex 結構化（免 API）
│   ├── llm_structure_reviews.py     # Claude Batch API 結構化
│   └── rematch_reviews.py      # 補匹配（尾綴變體）
├── frontend/src/
│   ├── index.html              # SPA 結構（5 個 view）
│   ├── script.js               # 全部互動邏輯
│   └── styles.css              # 樣式
└── requirements.txt
```

---

## 快速開始

### 1. 安裝依賴

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 準備資料庫

`backend/data/` 內已有 3 個 CSV。執行以下指令把它們灌進 SQLite：

```bash
python backend/scripts/ingest_csv.py
```

產出 `backend/data/app.db`（~30 MB）。

> 想重新爬資料？依序執行：
> 1. `python backend/Web-crawler.py` — 爬全校課程
> 2. `python backend/ptt_review_crawler.py` — 爬 PTT 評價
> 3. `python backend/regex_structure_reviews.py` 或 `llm_structure_reviews.py` — 結構化
>
> LLM 路徑需要 `ANTHROPIC_API_KEY` 環境變數。

### 3. 啟動 server

```bash
# Terminal 1: 後端 API
source .venv/bin/activate
uvicorn backend.api.main:app --reload
# Swagger 文件: http://localhost:8000/docs

# Terminal 2: 前端 static server
cd frontend/src
python3 -m http.server 5500
```

瀏覽器開 **http://localhost:5500** 開始使用。

---

## 資料量

| 表 | 列數 |
|---|---|
| `courses` | 8,467 門（PK = 流水號，跨學期/教師會重複；5,249 個 unique 課號）|
| `reviews_raw` | 4,265 篇 PTT 原文 |
| `reviews_structured` | 4,265 筆結構化評價（涵蓋 719 個 unique 課號）|

---

## API 一覽（13 個 endpoints）

| Method | Path | 用途 | 需 auth |
|---|---|---|---|
| GET | `/health` | 健康檢查 | – |
| GET | `/courses` | 列表 + 搜尋 + 篩選 + 分頁 | – |
| GET | `/courses/{serial_no}` | 單堂課詳情 | – |
| GET | `/courses/{serial_no}/reviews` | 該課的 PTT 評價 | – |
| GET | `/departments` | 系所列表 | – |
| POST | `/auth/register` | 註冊 | – |
| POST | `/auth/login` | 登入 | – |
| POST | `/auth/logout` | 登出 | ✓ |
| GET | `/auth/me` | 取得目前使用者 | ✓ |
| GET / PUT | `/me/profile` | 個人偏好讀寫 | ✓ |
| GET | `/me/history` | 修課歷史列表 | ✓ |
| POST | `/me/history` | 新增 | ✓ |
| DELETE | `/me/history/{id}` | 刪除 | ✓ |
| GET | `/me/recommendations` | Top N 推薦 | ✓ |
| GET | `/me/fit/{serial_no}` | 單堂適合度分數 | ✓ |
| POST | `/me/fits` | 批次拿一組課的適合度 | ✓ |

完整 schema 在 **http://localhost:8000/docs**（FastAPI 自動產生）。

---

## 適合度演算法

對一門課，分數 = 4 個成份加權平均（0–100）：

| 成份 | 權重 | 怎麼算 |
|---|---|---|
| **PTT 推薦** | 30% | 結構化評價的「推薦指數」均值 × 20 |
| **甜度匹配** | 25% | `max(0, 100 - |使用者偏好 - 評價甜度均值×20|)` |
| **Loading 匹配** | 25% | 同上，比對 loading 偏好 |
| **興趣命中** | 20% | 使用者興趣 tag 在「課名 + 系所」字串中出現幾次 × 50（上限 100）|

實作見 [`backend/api/recommendations.py`](backend/api/recommendations.py)。

### 設計取捨

- 只對「有 PTT 結構化評價」的 719 個課號做推薦；其他課缺資料無法評估。
- 使用者已修過的課（出現在 `user_history`）會從推薦中排除。
- 5 個能力值 slider 目前只用於使用者畫像（雷達圖），**尚未納入演算法**。原因是難以從課名/系所直接推出該課需要哪些能力，未來工作可用 LLM 標 tag 或 TF-IDF 比對課程概述。

---

## 未來工作

- **演算法用課程內容文字**：`課程概述` / `課程目標` / `評量方式` 都還沒用上。可以用 TF-IDF 或 embedding 計算與使用者偏好的相似度。
- **5 軸能力值真正影響推薦**：用關鍵字或 LLM 標每門課需要哪些能力，跟使用者能力做匹配。
- **多 session 管理**：目前 session 沒有過期機制，登入後 token 永久有效。
- **OAuth**：可以加 Google OAuth 作為第二種登入方式。
- **手機版 polish**：RWD 基本可用，但小螢幕的 sliders / 表格還可以優化。
- **覆蓋更多課**：PTT NTUcourse 板的爬蟲只抓到部分課程的評價，覆蓋率仍偏低。

---

## 安全注意事項

- 密碼用 PBKDF2-HMAC-SHA256 + 16-byte salt + 200,000 iterations，存在 `users.password_hash`。
- Session token 用 `secrets.token_urlsafe(32)`，存在 `sessions` 表，HTTP header `Authorization: Bearer <token>`。
- CORS 目前全開（`allow_origins=["*"]`），方便本機開發；正式部署前要鎖到特定 origin。
- SQL 全部用 parameterized query，不會被 SQL injection。
- 前端輸出全部 HTML-escape。
