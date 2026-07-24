"""LLM 공급자 디스패처 — codex(기본) ↔ agy 토글.

활성 공급자를 data/llm_provider.json 에 저장하고, 상위(script_gen, 라우트)에서
공급자 무관하게 active_client()/status_all() 로 접근한다.
원본: 260612-od-flow-supoer3-mp4/services/llm_backend.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import agy, codex

VALID = ("codex", "agy")
LABELS = {"codex": "OpenAI (ChatGPT)", "agy": "Gemini (Google)"}

_PROVIDER_FILE = Path(__file__).resolve().parents[2] / "data" / "llm_provider.json"
_DEFAULT = (os.environ.get("LLM_PROVIDER", "codex").strip() or "codex")


def _mod(name: str):
    return codex if name == "codex" else agy


def get_provider() -> str:
    try:
        if _PROVIDER_FILE.is_file():
            p = json.loads(_PROVIDER_FILE.read_text(encoding="utf-8")).get("provider", "")
            if p in VALID:
                return p
    except Exception:
        pass
    return _DEFAULT if _DEFAULT in VALID else "codex"


def set_provider(name: str) -> bool:
    name = (name or "").strip()
    if name not in VALID:
        return False
    try:
        _PROVIDER_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PROVIDER_FILE.write_text(json.dumps({"provider": name}, ensure_ascii=False),
                                  encoding="utf-8")
        return True
    except Exception:
        return False


def active_client():
    return _mod(get_provider()).client


def active_module():
    return _mod(get_provider())


def login_cmd(name: Optional[str] = None) -> List[str]:
    return _mod(name or get_provider()).login_terminal_cmd()


def _status_one(name: str) -> Dict[str, Any]:
    try:
        m = _mod(name)
        installed = m.is_installed()
        authed = m.is_authenticated() if installed else False
        email = m.get_account_email() if authed else None
    except Exception:
        installed = authed = False
        email = None
    return {"provider": name, "label": LABELS.get(name, name),
            "installed": installed, "authenticated": authed, "email": email}


def status_all() -> Dict[str, Any]:
    cur = get_provider()
    return {
        "provider": cur,
        "label": LABELS.get(cur, cur),
        "providers": {n: _status_one(n) for n in VALID},
        "active": _status_one(cur),
    }


def list_models() -> List[str]:
    return _mod(get_provider()).list_models()


def get_model() -> str:
    return _mod(get_provider()).get_model()


def set_model(name: str) -> None:
    _mod(get_provider()).set_model(name)
