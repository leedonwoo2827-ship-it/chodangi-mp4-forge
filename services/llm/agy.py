"""agy(Google Antigravity CLI) LLM 래퍼 — 인증 상태 + 비대화식 호출.

API 키를 쓰지 않는다. 인증/할당량은 `agy` 가 담당(사용자가 `agy` 1회 실행 → Google 로그인).
agy 는 응답을 콘솔에 직접 쓰므로 PTY 로 캡처(백엔드 없으면 subprocess 폴백).
원본: 260612-od-flow-supoer3-mp4/services/agy/{auth,runner}.py (병합).
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .errors import LLMError, LLMNotInstalled, LLMNotAuthenticated, LLMQuotaExceeded

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07|\x1b[@-Z\\-_]")


def _strip_ansi(s: str) -> str:
    s = _ANSI_RE.sub("", s or "")
    return s.replace("\r\n", "\n").replace("\r", "\n")


# ── 설정 ──────────────────────────────────────────────────────────────────
AGY_BIN = os.environ.get("AGY_BIN", "agy")
AGY_TIMEOUT = int(os.environ.get("AGY_PRINT_TIMEOUT", "300"))
DEFAULT_MODEL = os.environ.get("STUDIO_DEFAULT_MODEL", "gemini-3-pro")
AGY_MODEL = os.environ.get("AGY_MODEL", "").strip()
_MODEL_FILE = Path(__file__).resolve().parents[2] / "data" / "agy_model.json"
_FALLBACK_MODELS = ("Gemini 3 Pro", "Gemini 3 Flash")

_WIN = sys.platform == "win32"
WIN_CRED_TARGET = os.environ.get("AGY_CRED_TARGET", "").strip()
_WIN_CRED_KEYWORDS = ("antigravity", "gemini", "cloudcode")
CREDS_PATH = os.environ.get("AGY_CREDS_PATH", "").strip()

_FALLBACK_AGY_PATHS = [
    os.path.expandvars(r"%LOCALAPPDATA%\agy\bin\agy.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\agy\bin\agy.cmd"),
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\agy\bin\agy.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Antigravity\agy.exe"),
    os.path.expanduser("~/.local/bin/agy"),
    os.path.expanduser("~/.agy/bin/agy"),
]

_GUARD_SYSTEM = (
    "You are a text and document generation assistant. "
    "Do NOT run shell commands, do NOT read or write files, do NOT use any tools, "
    "and do NOT perform any coding or repository actions. "
    "Respond with ONLY the requested content as your message - nothing else."
)


class AgyError(LLMError):
    pass


class AgyNotInstalled(LLMNotInstalled, AgyError):
    pass


class AgyNotAuthenticated(LLMNotAuthenticated, AgyError):
    pass


class AgyQuotaExceeded(LLMQuotaExceeded, AgyError):
    pass


class AgyResult:
    __slots__ = ("text", "raw")

    def __init__(self, text: str, raw: Any = None):
        self.text = text
        self.raw = raw


# ── 실행 파일 탐지 ───────────────────────────────────────────────────────────
def agy_path() -> Optional[str]:
    if os.path.sep in AGY_BIN or (os.path.altsep and os.path.altsep in AGY_BIN):
        return AGY_BIN if os.path.isfile(AGY_BIN) else None
    found = shutil.which(AGY_BIN)
    if found:
        return found
    for p in _FALLBACK_AGY_PATHS:
        if p and os.path.isfile(p):
            return p
    return None


def is_installed() -> bool:
    return agy_path() is not None


def login_terminal_cmd() -> List[str]:
    return [agy_path() or AGY_BIN]


# ── Windows 자격증명 / 파일 기반 인증 ─────────────────────────────────────────
def _win_cred_targets() -> list[str]:
    if not _WIN:
        return []
    if WIN_CRED_TARGET:
        return [WIN_CRED_TARGET]
    targets: list[str] = []
    try:
        import win32cred
        for c in win32cred.CredEnumerate(None, 0):
            t = (c.get("TargetName") or "")
            if any(s in t.lower() for s in _WIN_CRED_KEYWORDS):
                targets.append(t)
    except Exception:
        pass
    if "gemini:antigravity" not in targets:
        targets.append("gemini:antigravity")
    return targets


def _win_cred_blob(target: str):
    try:
        import win32cred
        c = win32cred.CredRead(target, win32cred.CRED_TYPE_GENERIC)
        return c.get("CredentialBlob")
    except Exception:
        return None


def _win_cred_entries() -> list[tuple[str, bytes]]:
    out = []
    for t in _win_cred_targets():
        blob = _win_cred_blob(t)
        if blob is not None:
            out.append((t, blob))
    return out


def _blob_to_obj(blob) -> Optional[dict]:
    if not blob:
        return None
    raw = bytes(blob) if not isinstance(blob, (bytes, bytearray)) else blob
    for enc in ("utf-8", "utf-16-le", "utf-16"):
        try:
            s = raw.decode(enc, errors="ignore").strip().strip("\x00").strip()
            if s and s[0] in "{[":
                return json.loads(s)
        except Exception:
            continue
    return None


def _agy_dirs() -> list[Path]:
    dirs = [Path.home() / ".antigravity", Path.home() / ".config" / "antigravity"]
    for ev in ("LOCALAPPDATA", "APPDATA"):
        base = os.environ.get(ev)
        if base:
            dirs.append(Path(base) / "Antigravity")
            dirs.append(Path(base) / "antigravity")
    seen, out = set(), []
    for d in dirs:
        s = str(d).lower()
        if s not in seen:
            seen.add(s)
            out.append(d)
    return out


def _cred_json_files() -> list[Path]:
    files: list[Path] = []
    if CREDS_PATH and os.path.isfile(CREDS_PATH):
        files.append(Path(CREDS_PATH))
    for d in _agy_dirs():
        try:
            if not d.is_dir():
                continue
            for p in sorted(d.rglob("*.json")):
                if p.is_file() and p not in files:
                    files.append(p)
                if len(files) > 60:
                    break
        except Exception:
            continue
    return files


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


def _decode_jwt_email(id_token: str) -> Optional[str]:
    try:
        payload_b64 = id_token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
        email = payload.get("email")
        return email.strip().lower() if isinstance(email, str) and email else None
    except Exception:
        return None


def _userinfo_email(access_token: str) -> Optional[str]:
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        email = data.get("email")
        return email.strip().lower() if isinstance(email, str) and email else None
    except Exception:
        return None


def _email_from_obj(obj) -> Optional[str]:
    email = _deep_find(obj, {"email", "user_email", "account_email", "account"})
    if email and "@" in email:
        return email.strip().lower()
    idt = _deep_find(obj, {"id_token", "idToken"})
    if idt and idt.count(".") >= 2:
        e = _decode_jwt_email(idt)
        if e:
            return e
    at = _deep_find(obj, {"access_token", "accessToken"})
    if at:
        e = _userinfo_email(at)
        if e:
            return e
    return None


def _looks_like_creds(obj) -> bool:
    return bool(_deep_find(obj, {"email", "id_token", "idToken", "access_token",
                                 "accessToken", "refresh_token", "refreshToken"}))


def get_account_email() -> Optional[str]:
    for _t, blob in _win_cred_entries():
        obj = _blob_to_obj(blob)
        if obj:
            email = _email_from_obj(obj)
            if email:
                return email
    for p in _cred_json_files():
        try:
            with open(p, "r", encoding="utf-8") as f:
                obj = json.load(f)
        except Exception:
            continue
        email = _email_from_obj(obj)
        if email:
            return email
    return None


def is_authenticated() -> bool:
    if not is_installed():
        return False
    if _win_cred_entries():
        return True
    return get_account_email() is not None


def logout() -> bool:
    removed = False
    if _WIN:
        try:
            import win32cred
            for t in _win_cred_targets():
                try:
                    win32cred.CredDelete(t, win32cred.CRED_TYPE_GENERIC)
                    removed = True
                except Exception:
                    pass
        except Exception:
            pass
    for p in _cred_json_files():
        try:
            with open(p, "r", encoding="utf-8") as f:
                obj = json.load(f)
        except Exception:
            continue
        if _looks_like_creds(obj):
            try:
                os.remove(p)
                removed = True
            except Exception:
                pass
    return removed


# ── 모델 선택 ────────────────────────────────────────────────────────────────
def get_model() -> str:
    try:
        if _MODEL_FILE.is_file():
            m = json.loads(_MODEL_FILE.read_text(encoding="utf-8")).get("model", "")
            if isinstance(m, str) and m.strip():
                return m.strip()
    except Exception:
        pass
    return AGY_MODEL


def set_model(name: str) -> None:
    try:
        _MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
        _MODEL_FILE.write_text(json.dumps({"model": (name or "").strip()}, ensure_ascii=False),
                               encoding="utf-8")
    except Exception:
        pass


_MODELS_CACHE: Optional[List[str]] = None
_MODEL_LINE_RE = re.compile(r"^(Gemini|Claude|GPT|gemini|claude|gpt)[A-Za-z0-9 .\-()/]*$")


def _parse_models(out: str) -> List[str]:
    models: List[str] = []
    for line in (out or "").splitlines():
        s = _strip_ansi(line).strip()
        s = re.sub(r"^[>\-\*\s\d.\)]+", "", s).strip()
        if _MODEL_LINE_RE.match(s) and s not in models:
            models.append(s)
    return models


def list_models(force: bool = False) -> List[str]:
    global _MODELS_CACHE
    if _MODELS_CACHE is not None and not force:
        return _MODELS_CACHE
    path = agy_path()
    if not path:
        return list(_FALLBACK_MODELS)
    out = _pty_capture([path, "models"], timeout=30, idle_break=6) or ""
    models = _parse_models(out)
    if not models:
        try:
            p = subprocess.run([path, "models"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=30)
            models = _parse_models((p.stdout or "") + "\n" + (p.stderr or ""))
        except Exception:
            pass
    if not models:
        models = list(_FALLBACK_MODELS)
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


def _classify_error(stdout: str, stderr: str, returncode: int) -> AgyError:
    blob = f"{stdout}\n{stderr}".lower()
    if "auth" in blob or "login" in blob or "sign in" in blob or "unauthenticated" in blob:
        return AgyNotAuthenticated(
            "agy 에 Google 로그인이 필요합니다. 터미널에서 `agy` 를 한 번 실행해 "
            "Google 계정으로 로그인한 뒤 다시 시도하세요.")
    if any(k in blob for k in ("quota", "resource_exhausted", "rate limit",
                               "429", "too many requests", "exceeded")):
        return AgyQuotaExceeded(
            "Google 계정의 사용 할당량(quota)을 초과했습니다. 잠시 후 다시 시도하거나 "
            "더 큰 할당량의 Google AI Pro/Ultra 계정으로 `agy` 에 로그인하세요.")
    snippet = (stderr or stdout or "").strip()[:300]
    return AgyError(f"agy 호출 실패(exit={returncode}): {snippet}")


def _text_from_obj(obj: Any) -> str:
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        for key in ("response", "output", "text", "result", "content", "message"):
            v = obj.get(key)
            if isinstance(v, str) and v.strip():
                return v
            if isinstance(v, dict):
                inner = _text_from_obj(v)
                if inner:
                    return inner
    return ""


def _extract_text(stdout: str) -> str:
    raw = (stdout or "").strip()
    if not raw:
        return ""
    try:
        return _text_from_obj(json.loads(raw)) or raw
    except Exception:
        pass
    for line in reversed(raw.splitlines()):
        line = line.strip()
        if not line or line[0] not in "{[":
            continue
        try:
            t = _text_from_obj(json.loads(line))
            if t:
                return t
        except Exception:
            continue
    return raw


def _pty_capture(argv: List[str], timeout: int = 120, idle_break: int = 30) -> Optional[str]:
    try:
        from .pty_terminal import PtyProcess, backend_available
    except Exception:
        return None
    if not backend_available() or PtyProcess is None:
        return None
    try:
        proc = PtyProcess.spawn(argv, dimensions=(60, 220))
    except Exception:
        return None
    chunks: List[str] = []
    deadline = time.monotonic() + timeout
    last_data = time.monotonic()
    try:
        while True:
            if time.monotonic() > deadline:
                break
            try:
                data = proc.read(65536)
            except EOFError:
                break
            except Exception:
                break
            if data:
                chunks.append(data)
                last_data = time.monotonic()
            else:
                if not proc.isalive():
                    break
                if chunks and (time.monotonic() - last_data) > idle_break:
                    break
                time.sleep(0.05)
    finally:
        try:
            if proc.isalive():
                proc.terminate(force=True)
        except Exception:
            pass
    return _strip_ansi("".join(chunks))


class AgyClient:
    def __init__(self, bin_path: Optional[str] = None, default_model: Optional[str] = None,
                 timeout: Optional[int] = None):
        self.bin = bin_path or AGY_BIN
        self.default_model = default_model or DEFAULT_MODEL
        self.timeout = timeout or AGY_TIMEOUT

    def chat(self, model: Optional[str], messages: List[Dict[str, str]],
             max_tokens: int = 4000) -> AgyResult:
        return AgyResult(self._run(_compose_prompt(messages), model or self.default_model))

    def quick(self, prompt: str, model: Optional[str] = None) -> str:
        return self._run(_compose_prompt([{"role": "user", "content": prompt}]),
                         model or self.default_model)

    def _candidate_cmds(self, path: str, prompt: str) -> List[List[str]]:
        sel = get_model()
        model_opt = (["--model", sel] if sel else [])
        variants: List[List[str]] = [
            [path, "--print", prompt, "--dangerously-skip-permissions", *model_opt],
            [path, "--print", prompt, *model_opt],
            [path, "--print", prompt],
            [path, "-p", prompt],
        ]
        seen, uniq = set(), []
        for v in variants:
            key = tuple(v)
            if key not in seen:
                seen.add(key)
                uniq.append(v)
        return uniq

    def _run(self, prompt: str, model: str) -> str:
        path = agy_path() if self.bin == AGY_BIN else (
            self.bin if os.path.isfile(self.bin) else shutil.which(self.bin))
        if not path:
            raise AgyNotInstalled(
                "Antigravity CLI(`agy`)가 설치되어 있지 않습니다. 설치 후 `agy` 로 Google 로그인하세요.")
        sel = get_model()
        model_opt = (["--model", sel] if sel else [])
        argv = [path, "--print", prompt, "--dangerously-skip-permissions", *model_opt]
        out = _pty_capture(argv, timeout=self.timeout, idle_break=30)
        if out is not None:
            text = _extract_text(out)
            if text.strip():
                return text
            err = _classify_error(out, "", 0)
            if isinstance(err, (AgyNotAuthenticated, AgyQuotaExceeded)):
                raise err
        last_err: Optional[Exception] = None
        for cmd in self._candidate_cmds(path, prompt):
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True,
                                      encoding="utf-8", errors="replace",
                                      timeout=self.timeout + 30)
            except FileNotFoundError as e:
                raise AgyNotInstalled(f"agy 실행 실패: {e}") from e
            except subprocess.TimeoutExpired:
                last_err = AgyError(f"agy 응답 시간 초과({self.timeout}s).")
                continue
            if proc.returncode != 0:
                err = _classify_error(proc.stdout or "", proc.stderr or "", proc.returncode)
                if isinstance(err, (AgyNotAuthenticated, AgyQuotaExceeded)):
                    raise err
                last_err = err
                continue
            text = _extract_text(proc.stdout or "")
            if text.strip():
                return text
            last_err = _classify_error(proc.stdout or "", proc.stderr or "", proc.returncode)
        raise last_err or AgyError("agy 호출이 모든 방식에서 실패했습니다.")


client = AgyClient()
