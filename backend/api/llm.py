"""
共用的 Gemini client。

- 從環境變數讀 GEMINI_API_KEY / GEMINI_MODEL
- 沒設 key → is_available() = False,呼叫端應 fallback
- generate_text() 失敗回 None,不拋,讓呼叫端決定 fallback
"""

from __future__ import annotations

import os
import threading

_LOCK = threading.Lock()
_CLIENT = None  # google.genai.Client | None
_INIT_TRIED = False


def _get_client():
    global _CLIENT, _INIT_TRIED
    if _INIT_TRIED:
        return _CLIENT
    with _LOCK:
        if _INIT_TRIED:
            return _CLIENT
        _INIT_TRIED = True
        api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
        if not api_key:
            return None
        try:
            from google import genai
            _CLIENT = genai.Client(api_key=api_key)
        except Exception as e:
            print(f"[llm] Gemini client 初始化失敗: {e}")
            _CLIENT = None
        return _CLIENT


def is_available() -> bool:
    return _get_client() is not None


def model_name() -> str:
    return (os.environ.get("GEMINI_MODEL") or "gemini-2.5-flash").strip()


def generate_text(
    prompt: str,
    *,
    system: str | None = None,
    max_output_tokens: int = 200,
    temperature: float = 0.4,
) -> str | None:
    """單次同步呼叫,回純文字。失敗回 None。"""
    client = _get_client()
    if client is None:
        return None
    try:
        from google.genai import types
        # thinking_budget=0 關掉 reasoning,避免 thinking token 吃掉 max_output_tokens
        # gemini-2.5-flash 預設會 think,且 thinking 算在 max_output_tokens 內
        config_kwargs: dict = {
            "system_instruction": system,
            "max_output_tokens": max_output_tokens,
            "temperature": temperature,
        }
        try:
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        except Exception:
            pass  # 較舊 SDK 或不支援的 model
        config = types.GenerateContentConfig(**config_kwargs)
        resp = client.models.generate_content(
            model=model_name(),
            contents=prompt,
            config=config,
        )
        text = (resp.text or "").strip()
        return text or None
    except Exception as e:
        print(f"[llm] generate_text 失敗: {e}")
        return None
