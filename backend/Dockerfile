FROM python:3.11-slim

WORKDIR /app

# 安裝 backend API 執行期 deps (不含爬蟲依賴 Playwright/requests/bs4/anthropic)。
# 用 requirements-api.txt 作為單一來源,避免跟手動清單版本漂移。
# 含 google-genai + python-dotenv,否則 AI 功能在 container 內會 ImportError → 全部 fallback。
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# 複製 backend 程式碼
COPY backend/ /app/backend/

# 建立資料庫
RUN python backend/scripts/ingest_csv.py 

# Port
EXPOSE 8000

# 啟動指令
CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
