"""FastAPI APIRouter 模組 — 從原本單一 main.py 拆出。

- courses:  公開的課程 / 評價 / 教師 / 系所查詢 + 相關課程
- auth:     註冊 / 登入 / 登出 / refresh / me
- me:       使用者 profile / 推薦 / 適合度 / 修課歷史 / 想修清單 (需 auth)
- ai:       9 個 LLM-powered AI 功能

main.py 只負責組裝 app 並 include 這些 router,路徑與行為與重構前完全一致。
"""
