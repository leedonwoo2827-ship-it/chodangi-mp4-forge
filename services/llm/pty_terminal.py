"""크로스플랫폼 PTY(가상 터미널) — agy 콘솔 출력 캡처용.

- Windows: pywinpty(`winpty.PtyProcess`)
- POSIX  : ptyprocess(`ptyprocess.PtyProcessUnicode`)
동일 API(spawn/read/write/isalive/setwinsize)를 제공한다. 백엔드가 없으면
backend_available()==False 이고, agy 클라이언트는 일반 subprocess 폴백을 쓴다.
원본: 260612-od-flow-supoer3-mp4/services/agy/pty_terminal.py
"""
from __future__ import annotations

import os
import sys
from typing import List, Optional

_IMPORT_ERROR = None
try:  # Windows
    from winpty import PtyProcess  # type: ignore
    _BACKEND = "winpty"
except Exception as _e_win:  # POSIX
    try:
        from ptyprocess import PtyProcessUnicode as PtyProcess  # type: ignore
        _BACKEND = "ptyprocess"
    except Exception as _e_posix:  # pragma: no cover
        PtyProcess = None  # type: ignore
        _BACKEND = None
        _IMPORT_ERROR = f"winpty: {_e_win!r} / ptyprocess: {_e_posix!r}"


def backend_available() -> bool:
    return PtyProcess is not None


def default_shell() -> List[str]:
    override = os.environ.get("AGY_TERMINAL_SHELL")
    if override:
        return override.split()
    if sys.platform == "win32":
        return [os.environ.get("COMSPEC", "cmd.exe")]
    return [os.environ.get("SHELL", "/bin/bash")]


def diag() -> dict:
    from .agy import agy_path
    return {
        "platform": sys.platform,
        "pty_backend": _BACKEND,
        "pty_available": PtyProcess is not None,
        "pty_import_error": _IMPORT_ERROR,
        "shell": default_shell(),
        "agy_path": agy_path(),
        "agy_installed": agy_path() is not None,
    }
