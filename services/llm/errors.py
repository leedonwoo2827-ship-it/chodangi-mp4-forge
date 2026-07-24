"""LLM 공급자 공통 예외 (codex/agy 가 상속)."""
from __future__ import annotations


class LLMError(RuntimeError):
    """LLM 호출 일반 오류(공급자 공통)."""


class LLMNotInstalled(LLMError):
    """공급자 CLI(agy/codex)가 설치되어 있지 않음."""


class LLMNotAuthenticated(LLMError):
    """공급자에 로그인되어 있지 않음."""


class LLMQuotaExceeded(LLMError):
    """계정 할당량(quota) 초과."""
