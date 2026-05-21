FROM python:3.11-slim

WORKDIR /app

# 安裝 backend 需要的 deps (api 部分,不含爬蟲依賴 Playwright)
COPY requirements.txt .
RUN pip install --no-cache-dir \
    "fastapi>=0.110" \
    "uvicorn[standard]>=0.27" \
    "pydantic>=2.5" \
    "pandas>=2.0"

# 複製 backend 程式碼
COPY backend/ /app/backend/

# Port
EXPOSE 8000

# 啟動指令
CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
