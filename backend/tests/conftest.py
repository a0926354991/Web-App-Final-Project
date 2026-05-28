"""pytest 設定 — 確保能 import backend.api.*。"""

import sys
from pathlib import Path

# 專案根目錄 (含 backend/) 加進 sys.path,讓 `from backend.api import ...` 可用
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
