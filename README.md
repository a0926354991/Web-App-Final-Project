# 台大個性化選課推薦與分析

NTU Personalized Course Recommendation — Web 應用程式期末專案。

從台大課程網爬全校 8,467 門課，從 PTT NTUcourse 板爬 4,265 篇修課心得，
用 Claude API 結構化評價；再依使用者偏好（5 軸能力、甜度 / loading 偏好、興趣領域），
以**手刻 TF-IDF + 關鍵字 mapping** 計算「適合度」推薦課程，並附上 template 生成的推薦理由。

---

## 功能總覽

| 功能 | 說明 |
|---|---|
| **註冊 / 登入** | 自製 session token auth（PBKDF2 密碼 hash） |
| **課程探索** | 搜尋（課名/教師/課號）+ 系所/學分篩選 + 分頁 + 可水平捲動 |
| **課程詳情抽屜** | 完整課綱 + PTT 結構化評價 + 適合度分數 + 推薦理由 |
| **教師頁面** | 點教師名 → 抽屜切換到該教師概覽：開過課數、累計 PTT 平均評分、所有開過的課 |
| **課程比較** | 勾選 2-3 門課 → 全螢幕並排比較適合度 / PTT 樣本 / 評量方式 / 課程要求 |
| **使用者資訊** | 5 軸能力 + 甜度偏好 + loading 偏好 + 興趣 tag |
| **修課歷史** | 紀錄學期 + 成績 + 筆記；探索頁顯示「已修」狀態；已修課自動排除推薦 |
| **想修清單** | backend 持久化的 wishlist，跟修課歷史對稱 |
| **我的課表** | localStorage 持久化的本學期排課，有衝堂偵測 + 視覺化週課表 |
| **相關課程** | 修過 X 也修 Y（CF Jaccard）+ 內容相似度（dept / code / ability / interest Jaccard）hybrid |
| **PDF 匯出** | 修課歷史 / 想修 / 課表都可一鍵列印成 PDF |
| **個性化推薦** | 5 成份加權算「適合度 %」，搭配一句話 explanation 解釋為什麼推薦 |
| **適合度顯示位置** | 儀表板 / 探索表格（可按分數排序）/ 詳情抽屜 / 適合度分析 tab（Top 20）|
| **Dark mode** | header 一鍵切換深淺色，localStorage 持久化 |
| **RWD** | < 600px 時：比較表格垂直堆疊、抽屜全屏、filter 全寬 |

---

## 技術棧

- **後端**：Python 3.11+、FastAPI、SQLite（stdlib `sqlite3`，無 ORM）
- **資料管線**：Playwright（爬課程網）、requests + BeautifulSoup（爬 PTT）、
  Anthropic Batch API（LLM 結構化評價）
- **前端**：純 HTML + CSS + Vanilla JS、Chart.js 雷達圖
- **無框架前端是刻意的**：簡化部署、展示原生 web 技能
- **演算法依賴零新增**：TF-IDF 手刻、無 sklearn、無 jieba

---

## 專案結構

```
.
├── backend/
│   ├── api/                       # FastAPI app
│   │   ├── main.py                # 全部 endpoints
│   │   ├── auth.py                # PBKDF2 hash + session token + table init
│   │   ├── recommendations.py     # TF-IDF + ability matching + 推薦理由
│   │   ├── db.py                  # SQLite 連線 dependency
│   │   └── schemas.py             # Pydantic models
│   ├── scripts/
│   │   └── ingest_csv.py          # CSV → SQLite 一次性灌資料
│   ├── data/                      # CSV (gitignored: app.db)
│   ├── Web-crawler.py             # 台大課程網 Playwright 爬蟲
│   ├── ptt_review_crawler.py      # PTT NTUcourse 板爬蟲
│   ├── regex_structure_reviews.py # Regex 結構化（免 API）
│   ├── llm_structure_reviews.py   # Claude Batch API 結構化
│   └── rematch_reviews.py         # 補匹配（尾綴變體）
├── frontend/src/
│   ├── index.html                 # SPA 結構（5 個 view + 3 個 modal + 抽屜）
│   ├── script.js                  # 所有互動邏輯（auth / discovery / drawer / compare / etc.）
│   └── styles.css                 # 樣式（含 dark mode + RWD）
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

`backend/data/` 內已有 3 個 CSV（隨 repo 提供）。執行：

```bash
python backend/scripts/ingest_csv.py
```

產出 `backend/data/app.db`（~30 MB）。

> 想自己重新爬資料？依序執行 `Web-crawler.py` → `ptt_review_crawler.py`
> → `regex_structure_reviews.py` 或 `llm_structure_reviews.py`。
> LLM 路徑需要 `ANTHROPIC_API_KEY` 環境變數。

### 3. 啟動 server

**選項 A:本機開發 (有 hot reload)**
```bash
# Terminal 1: 後端 API
source .venv/bin/activate
uvicorn backend.api.main:app --reload
# Swagger 文件: http://localhost:8000/docs

# Terminal 2: 前端 static server
cd frontend/src
python3 -m http.server 5500
```

**選項 B:Docker compose 一鍵啟動 (示範 / 部署用)**
```bash
docker compose up --build
```

瀏覽器開 **http://localhost:5500**。

> Docker 版會自動 mount `backend/data/`,所以 `app.db` 跟 CSV 跟本機共用。
> 注意 backend container 不包含爬蟲依賴 (Playwright),只有 API 必要的 deps。

---

## 資料量

| 表 | 列數 |
|---|---|
| `courses` | 8,467 門（PK = 流水號；同 `課號` 跨學期 / 教師會重複，共 5,249 個 unique 課號）|
| `reviews_raw` | 4,265 篇 PTT 原文 |
| `reviews_structured` | 4,265 筆結構化評價（涵蓋 719 個 unique 課號）|
| `users` / `sessions` / `user_profiles` / `user_history` | 使用者相關，啟動時自動建表 |

---

## API 一覽（共 19 個 endpoints）

| Method | Path | 用途 | 需 auth |
|---|---|---|---|
| GET | `/health` | 健康檢查 | – |
| GET | `/courses` | 列表 + 搜尋 + 篩選 + 分頁 | – |
| GET | `/courses/{serial_no}` | 單堂課詳情 | – |
| GET | `/courses/{serial_no}/reviews` | 該課的 PTT 結構化評價 | – |
| GET | `/departments` | 系所列表（給前端下拉）| – |
| GET | `/teachers/{name}` | 教師概覽 + 該教師所有課 + 統計 | – |
| POST | `/auth/register` | 註冊 | – |
| POST | `/auth/login` | 登入 | – |
| POST | `/auth/logout` | 登出（刪 session token）| ✓ |
| GET | `/auth/me` | 取得目前使用者 | ✓ |
| GET | `/me/profile` | 取得偏好（不存在則回預設）| ✓ |
| PUT | `/me/profile` | 寫入偏好（upsert）| ✓ |
| GET | `/me/history` | 修課歷史列表（含 join courses）| ✓ |
| POST | `/me/history` | 新增一筆 | ✓ |
| DELETE | `/me/history/{id}` | 刪除一筆 | ✓ |
| GET | `/me/wishlist` | 想修清單 | ✓ |
| POST | `/me/wishlist` | 加入想修 | ✓ |
| DELETE | `/me/wishlist/{id}` | 移除想修 | ✓ |
| GET | `/courses/{serial_no}/related` | 相關課程 (CF + content hybrid) | – |
| GET | `/me/recommendations?limit=N` | Top N 推薦（排除已修）| ✓ |
| GET | `/me/fit/{serial_no}` | 單堂課適合度分數 + 各成份 + 推薦理由 | ✓ |
| POST | `/me/fits` | 批次拿一組課的適合度（供表格顯示）| ✓ |

完整 request/response schema 在 **http://localhost:8000/docs**（FastAPI 自動產生）。

---

## 適合度演算法

對一門課，分數 = 5 個成份加權平均（0–100）：

| 成份 | 權重 | 怎麼算 |
|---|---|---|
| **PTT 推薦** | 25% | 結構化評價的「推薦指數」均值 × 20 |
| **甜度匹配** | 20% | `max(0, 100 - |使用者甜度偏好 − 評價甜度均值×20|)` |
| **Loading 匹配** | 20% | 同上，比對 loading 偏好 |
| **興趣 (TF-IDF)** | 20% | 手刻 TF-IDF：interest tag 在課程文字中加權命中度 |
| **能力匹配** | 15% | 課程關鍵字推「該課需要哪些能力」→ 取使用者那幾項能力的平均 |

實作見 [`backend/api/recommendations.py`](backend/api/recommendations.py)。

### TF-IDF 興趣比對（手刻，無新依賴）

啟動時對 13 個固定 interest tag（AI / 程式 / 金融 / 商管 / ...）計算 **IDF**：
出現在越少課的 tag，匹配時越值錢。每門課的文字依區段加權：

| 區段 | TF 權重 |
|---|---|
| 課名 | ×3 |
| 開課系所 | ×3 |
| 課程目標 | ×2 |
| 課程概述 + 評量方式 | ×1 |

ASCII tag（例如 `AI`）用 `\bAI\b` 詞邊界匹配，避免被 `application` / `again` / `main` 等誤匹配。
中文 tag 用單純 substring。

最終 score = Σ TF × IDF，clamp 到 0–100。

### 能力 keyword mapping

每個能力定一組關鍵字，對課程全文做匹配；命中的關鍵字代表「該課需要這項能力」：

| 能力軸 | 關鍵字（節選）|
|---|---|
| 數理邏輯 | 數學、微積分、邏輯、線性代數、機率、統計、證明、解析 |
| 文字表達 | 寫作、論文、報告、文學、撰寫 |
| 程式實作 | 程式、演算法、資料結構、Python、Java、software |
| 人文素養 | 哲學、歷史、藝術、文化、社會學、人類學、宗教 |
| 團隊協作 | 團體、合作、專題、小組、工作坊、協作 |

該課需要的每個能力，取使用者該項能力值（0–100）→ 平均 = ability score。
如果沒命中任何關鍵字（課程定位較中立），給中性 50 分。

### 推薦理由（compute_explanation）

純 template，無 LLM。根據 fit breakdown 各成份的高低生出一句中文：
- 取 1-3 個強項組成 highlight：「PTT 推薦度高(100/100,4 篇評價)、命中你的『金融』興趣、需要的能力跟你的長處對得上」
- 如果有成份 < 40 → 接「但...」說 caveat：「但 loading 比你偏好的重」

### 設計取捨

- 只對「有 PTT 結構化評價」的 **719 個課號**做推薦排序；其他課缺資料無法評估甜度 / loading / 推薦。
- 使用者已修過的課（出現在 `user_history`）會被排除。
- PTT 樣本 ≤ 2 篇的課，前端在分數旁顯示「⚠ 樣本少」警告。

---

## 安全注意事項

- 密碼用 **PBKDF2-HMAC-SHA256 + 16-byte salt + 200,000 iterations**，存在 `users.password_hash`。
- Session token 用 `secrets.token_urlsafe(32)`，存 `sessions` 表，HTTP header `Authorization: Bearer <token>`。
- CORS 全開（`allow_origins=["*"]`），方便本機開發；正式部署前要鎖到特定 origin。
- SQL 全部用 parameterized query。
- 前端輸出全部 HTML-escape。
- Token 目前**沒有過期機制**，登入後永久有效（未來工作見下）。

---

## 未來工作

- **Session 過期 / refresh**：目前 token 永久有效，正式部署前要加。
- **演算法層面**：
  - 用 sentence embedding 算課程概述跟使用者偏好的相似度（取代 substring TF）。
  - 用 LLM（Claude 等）為每門課標 ability tag，比關鍵字精準。
  - 加 collaborative filtering：「修過 X 的人也修了 Y」。
- **OAuth**：Google 登入作為第二種登入方式。
- **覆蓋更多評價**：PTT NTUcourse 板覆蓋率有限，可以加 ColleGo、學校教學意見調查等資料來源。
- **更完整的 dark mode**：目前覆蓋主要 surface，少數細節（圖表 tooltip、icon color）仍是亮色預設。
