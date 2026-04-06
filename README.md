# 台大個性化選課推薦與分析 App
**NTU Personalized Course Recommendation & Analysis**

一個專為台灣大學學生設計的選課輔助工具，整合官方課程資料與 PTT/Dcard 非官方評價，提供個人化推薦、能力雷達圖分析與互動式課表管理。

---

## 功能總覽

| 頁面 | 功能說明 |
|------|----------|
| 個人儀表板 | 能力雷達圖、推薦課程、修課統計（學分、GPA） |
| 課程探索 | 多維度篩選（甜度、時段、學分）、關鍵字搜尋、分頁瀏覽 |
| 課程詳情 | 官方大綱、歷年學生評價、關鍵字標籤（#點名、#給分甜…） |
| 修課歷程 | 新增/刪除歷史課程、成績管理、雷達圖自動更新 |
| 互動課表 | 視覺化週課表、時段衝突顯示、空堂課程推薦填補 |
| 適合度分析 | 適合度環狀圖（百分比）、AI 分析短評、先修條件預警 |

---

## 快速開始

### 前端（純靜態，無需伺服器）

直接用瀏覽器開啟：

```
frontend/src/index.html
```

> 目前使用 Mock 資料，所有功能皆可操作。登入後可使用個人化功能（資料存於 localStorage）。

### 後端（開發中）

```bash
# 安裝依賴
pip install -r requirements.txt

# 啟動 API 伺服器（需先完成 backend/app.py）
python backend/app.py
```

---

## 專案結構

```
Web-App-Final-Project/
├── frontend/
│   └── src/
│       ├── index.html      # 單頁應用（SPA）主體
│       ├── styles.css      # 全域樣式（響應式設計）
│       └── script.js       # 所有互動邏輯與 Mock 資料
│
├── backend/
│   ├── main.py             # 後端入口（開發中）
│   ├── Web-crawler.py      # 台大課程網爬蟲
│   ├── Web-crawler-rate.py # PTT/Dcard 評價爬蟲
│   ├── merge_ntu_course_data.py  # 資料合併腳本
│   └── data/
│       ├── ntu_detailed_data.csv      # 官方課程大綱資料
│       ├── ntu_rate_data.csv          # 爬取的學生評價資料
│       ├── ntu_merged.csv             # 合併後完整資料集（3120 筆）
│       └── ntu_merge_unmatched_keys.csv
│
├── requirements.txt
└── README.md
```

---

## 資料說明

資料來源為 114 學年第 2 學期，共 **3,120 筆課程**，其中 **249 筆**含學生評價。

### `ntu_merged.csv` 欄位

| 欄位 | 說明 |
|------|------|
| 課名、教師 | 課程基本資訊 |
| 開課系所、課號 | 系所與課程代碼 |
| 上課時間、上課地點 | 如「三 6,7 教208」 |
| 學分、修課人數上限 | 選課資訊 |
| 品質、甜度、涼度、紮實 | 學生評分（1–5） |
| 評價內容、評價明細_JSON | 歷年學生評論 |
| 課程概述、課程目標、評量方式 | 官方課程大綱 |
| 詳情頁URL | 台大課程網連結 |

---

## 技術架構

**前端**
- 原生 HTML / CSS / JavaScript（無框架，單頁應用）
- [Chart.js](https://www.chartjs.org/) — 雷達圖、環狀圖
- [Font Awesome 6](https://fontawesome.com/) — 圖示
- localStorage — 使用者資料持久化

**後端**（規劃中）
- Python + Flask — REST API
- Pandas — CSV 資料處理
- Playwright / Selenium — 網頁爬蟲

---

## 開發規格（Epic 對應）

### Epic 1：前端核心介面

- **Feature 1.1** 整合性課程資訊頁面（詳情 Modal + 評價分頁 + 關鍵字標籤）
- **Feature 1.2** 個人化儀表板（雷達圖 + 推薦清單 + 互動課表）
- **Feature 1.3** 進階條件篩選（時段、甜度 Slider、Checkbox 組合篩選）
- **Feature 1.4** 適合度 UI 元件（環狀圖 + 分析短評 + 先修預警 Modal）

### Epic 2：後端架構（規劃中）

- **Feature 2.1** 台大信箱 / JWT 認證
- **Feature 2.2** 課程與評價聚合 API（分頁 + 快取）
- **Feature 2.3** 複合篩選與空堂比對 API
- **Feature 2.4** 先修/擋修規則引擎

---

## 截圖預覽

> 開啟 `frontend/src/index.html` 即可瀏覽完整 UI prototype。

主要頁面包含：儀表板（雷達圖 + 推薦）、課程探索（篩選 + Grid）、互動課表（週視圖）、適合度分析（環狀圖 + 評價）。

---

## 貢獻成員

| 負責範圍 | 說明 |
|----------|------|
| 前端 UI / SPA | 儀表板、篩選介面、課表、分析頁面 |
| 資料爬蟲 | 台大課程網、PTT/Dcard 評價收集 |
| 資料處理 | 課程資料清洗與合併 |
| 後端 API | Flask 路由設計（進行中） |
