"""codex(OpenAI Codex CLI) LLM 래퍼 — 인증 상태 + 비대화식 호출.

API 키를 쓰지 않는다. 인증/할당량은 `codex` 가 담당(사용자가 `codex login` 1회, ChatGPT OAuth).
`codex exec -` 는 최종 답을 stdout 으로 내보내므로 일반 subprocess 로 캡처한다.
원본: 260612-od-flow-supoer3-mp4/services/codex/{auth,runner}.py (병합).
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from .errors import LLMError, LLMNotInstalled, LLMNotAuthenticated, LLMQuotaExceeded

# ── 설정 ──────────────────────────────────────────────────────────────────
CODEX_BIN = os.environ.get("CODEX_BIN", "codex")
AUTH_PATH = os.environ.get("CODEX_AUTH_PATH", str(Path.home() / ".codex" / "auth.json"))
CODEX_TIMEOUT = int(os.environ.get("CODEX_EXEC_TIMEOUT", "900"))
CODEX_MODEL_ENV = os.environ.get("CODEX_MODEL", "").strip()
_MODEL_FILE = Path(__file__).resolve().parents[2] / "data" / "codex_model.json"

_FALLBACK_CODEX_PATHS = [
    os.path.expanduser("~/.local/bin/codex"),
    os.path.expandvars(r"%APPDATA%\npm\codex.cmd"),
    os.path.expandvars(r"%APPDATA%\npm\codex"),
]

_GUARD_SYSTEM = (
    "You are a text and document generation assistant. "
    "Do NOT run shell commands, do NOT read or write files, do NOT use any tools, "
    "and do NOT perform any coding or repository actions. "
    "Respond with ONLY the requested content as your message - nothing else."
)


# ── 예외(공급자별) ──────────────────────────────────────────────────────────
class CodexError(LLMError):
    pass


class CodexNotInstalled(LLMNotInstalled):
    pass


class CodexNotAuthenticated(LLMNotAuthenticated):
    pass


class CodexQuotaExceeded(LLMQuotaExceeded):
    pass


class CodexResult:
    __slots__ = ("text", "raw")

    def __init__(self, text: str, raw: Any = None):
        self.text = text
        self.raw = raw


# ── 실행 파일 탐지 / 인증 ─────────────────────────────────────────────────────
def codex_path() -> Optional[str]:
    if os.path.sep in CODEX_BIN or (os.path.altsep and os.path.altsep in CODEX_BIN):
        return CODEX_BIN if os.path.isfile(CODEX_BIN) else None
    found = shutil.which(CODEX_BIN)
    if found:
        return found
    for p in _FALLBACK_CODEX_PATHS:
        if p and os.path.isfile(p):
            return p
    return None


def is_installed() -> bool:
    return codex_path() is not None


def is_authenticated() -> bool:
    """`codex login status` exit 0 이면 로그인된 것으로 판정."""
    path = codex_path()
    if not path:
        return False
    try:
        p = subprocess.run([path, "login", "status"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=20)
        return p.returncode == 0
    except Exception:
        return False


def _decode_jwt_email(token: str) -> Optional[str]:
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
        for k in ("email", "https://api.openai.com/profile", "preferred_username"):
            v = payload.get(k)
            if isinstance(v, str) and "@" in v:
                return v.strip().lower()
            if isinstance(v, dict) and isinstance(v.get("email"), str):
                return v["email"].strip().lower()
    except Exception:
        pass
    return None


def _deep_find(obj, keys) -> Optional[str]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys and isinstance(v, str) and v.strip():
                return v.strip()
        for v in obj.values():
            r = _deep_find(v, keys)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _deep_find(v, keys)
            if r:
                return r
    return None


def get_account_email() -> Optional[str]:
    try:
        if os.path.isfile(AUTH_PATH):
            with open(AUTH_PATH, "r", encoding="utf-8") as f:
                obj = json.load(f)
            email = _deep_find(obj, {"email", "account_email", "preferred_username"})
            if email and "@" in email:
                return email.strip().lower()
            idt = _deep_find(obj, {"id_token", "idToken", "access_token", "accessToken"})
            if idt and idt.count(".") >= 2:
                e = _decode_jwt_email(idt)
                if e:
                    return e
    except Exception:
        pass
    return None


def logout() -> bool:
    path = codex_path()
    if not path:
        return False
    try:
        subprocess.run([path, "logout"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=20)
        return True
    except Exception:
        try:
            if os.path.isfile(AUTH_PATH):
                os.remove(AUTH_PATH)
                return True
        except Exception:
            pass
        return False


def login_terminal_cmd() -> List[str]:
    return [codex_path() or CODEX_BIN, "login"]


# ── 모델 선택 ────────────────────────────────────────────────────────────────
def get_model() -> str:
    try:
        if _MODEL_FILE.is_file():
            m = json.loads(_MODEL_FILE.read_text(encoding="utf-8")).get("model", "")
            if isinstance(m, str) and m.strip():
                return m.strip()
    except Exception:
        pass
    return CODEX_MODEL_ENV


def set_model(name: str) -> None:
    try:
        _MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
        _MODEL_FILE.write_text(json.dumps({"model": (name or "").strip()}, ensure_ascii=False),
                               encoding="utf-8")
    except Exception:
        pass


_MODELS_CACHE: Optional[List[str]] = None
_MODEL_ID_RE = re.compile(r"^(gpt|o\d|chatgpt|codex)[A-Za-z0-9.\-_]*$", re.IGNORECASE)


def _parse_models(out: str) -> List[str]:
    out = (out or "").strip()
    if "{" in out and '"models"' in out:
        try:
            blob = out[out.index("{"): out.rindex("}") + 1]
            data = json.loads(blob)
            ids: List[str] = []
            for m in data.get("models", []):
                if not isinstance(m, dict):
                    continue
                if str(m.get("visibility", "")).lower() == "hide":
                    continue
                slug = (m.get("slug") or m.get("id") or m.get("name") or "").strip()
                if slug and slug not in ids:
                    ids.append(slug)
            if ids:
                return ids
        except Exception:
            pass
    models: List[str] = []
    for line in out.splitlines():
        s = line.strip().strip("-*> \t")
        tok = s.split()[0] if s.split() else ""
        if _MODEL_ID_RE.match(tok) and tok not in models:
            models.append(tok)
    return models


def list_models(force: bool = False) -> List[str]:
    global _MODELS_CACHE
    if _MODELS_CACHE is not None and not force:
        return _MODELS_CACHE
    path = codex_path()
    if not path:
        return []
    models: List[str] = []
    try:
        p = subprocess.run([path, "debug", "models"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=45)
        models = _parse_models((p.stdout or "") + "\n" + (p.stderr or ""))
    except Exception:
        pass
    if models:
        _MODELS_CACHE = models
    return models


# ── 호출 ────────────────────────────────────────────────────────────────────
def _compose_prompt(messages: List[Dict[str, str]]) -> str:
    parts: List[str] = [_GUARD_SYSTEM]
    for m in messages:
        role = (m.get("role") or "user").lower()
        content = m.get("content") or ""
        if not content:
            continue
        if role == "system":
            parts.append(f"[지침]\n{content}")
        elif role == "assistant":
            parts.append(f"[이전 답변]\n{content}")
        else:
            parts.append(f"[요청]\n{content}")
    return "\n\n".join(parts)


def _classify_error(stdout: str, stderr: str, rc: int) -> LLMError:
    blob = f"{stdout}\n{stderr}".lower()
    if any(k in blob for k in ("not logged in", "please run", "codex login", "unauthorized",
                               "401", "authenticate", "sign in")):
        return CodexNotAuthenticated(
            "codex 에 ChatGPT 로그인이 필요합니다. 터미널에서 `codex login` 을 실행해 로그인하세요.")
    if any(k in blob for k in ("quota", "rate limit", "429", "too many requests",
                               "usage limit", "exceeded")):
        return CodexQuotaExceeded(
            "ChatGPT 계정 사용 한도를 초과했습니다. 잠시 후 다시 시도하거나 상위 구독(Plus/Pro)을 사용하세요.")
    snippet = (stderr or stdout or "").strip()[:300]
    return CodexError(f"codex 호출 실패(exit={rc}): {snippet}")


class CodexClient:
    def __init__(self, bin_path: Optional[str] = None, default_model: Optional[str] = None,
                 timeout: Optional[int] = None):
        self.bin = bin_path or CODEX_BIN
        self.default_model = default_model
        self.timeout = timeout or CODEX_TIMEOUT

    def chat(self, model: Optional[str], messages: List[Dict[str, str]],
             max_tokens: int = 4000) -> CodexResult:
        return CodexResult(self._run(_compose_prompt(messages), model))

    def quick(self, prompt: str, model: Optional[str] = None) -> str:
        return self._run(_compose_prompt([{"role": "user", "content": prompt}]), model)

    def _run(self, prompt: str, model: Optional[str]) -> str:
        path = codex_path() if self.bin == CODEX_BIN else (
            self.bin if os.path.isfile(self.bin) else shutil.which(self.bin))
        if not path:
            raise CodexNotInstalled(
                "OpenAI Codex CLI(`codex`)가 설치되어 있지 않습니다. "
                "설치 후 `codex login` 으로 ChatGPT 로그인하세요.")
        sel = (model or "").strip() or get_model()
        model_opt = (["-m", sel] if sel else [])
        # 프롬프트는 stdin(`exec -`)으로 전달(Windows cmd 8KB 명령줄 한계 회피).
        cmd = [path, "exec", "-", "-s", "read-only", "--skip-git-repo-check", *model_opt]
        try:
            proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=self.timeout + 30)
        except FileNotFoundError as e:
            raise CodexNotInstalled(f"codex 실행 실패: {e}") from e
        except subprocess.TimeoutExpired as e:
            raise CodexError(f"codex 응답 시간 초과({self.timeout}s).") from e
        text = (proc.stdout or "").strip()
        if not text:
            raise _classify_error(proc.stdout or "", proc.stderr or "", proc.returncode)
        return text


client = CodexClient()
