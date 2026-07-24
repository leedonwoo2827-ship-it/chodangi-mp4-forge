"""로컬 LLM 공급자 위임 (API 키 없음, OAuth CLI).

대본 JSON 을 codex(OpenAI ChatGPT CLI) 또는 agy(Google Antigravity CLI)로 생성한다.
두 공급자 모두 동일 인터페이스(`client.chat(model, messages)` + auth/model 함수)를 제공하고,
backend 가 활성 공급자를 골라 준다. 원본: 260612-od-flow-supoer3-mp4/services/{codex,agy,llm_*}.
"""
from __future__ import annotations

from .errors import (
    LLMError, LLMNotInstalled, LLMNotAuthenticated, LLMQuotaExceeded,
)

__all__ = ["LLMError", "LLMNotInstalled", "LLMNotAuthenticated", "LLMQuotaExceeded"]
