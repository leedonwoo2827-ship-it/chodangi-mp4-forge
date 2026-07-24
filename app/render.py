"""mp4maker 를 subprocess 로 돌리고 stdout 진행률 태그를 파싱한다.

mp4maker 는 CLI(`python -m mp4maker <bundle>`)로 호출하도록 설계됐고, 파싱 가능한
태그를 stdout 으로 흘린다:

    [bundle] chNN '<title>'  scenes=N
    [render] N scenes  jobs=J  res=WxH@FPSfps
    [scene]  scNN done  (T.Ts)  progress=K/N      ← 진행률
    [done]   <output path>                          ← 산출물
    [total]  T.Ts

종료코드 0=성공, 2=입력/검증 오류.

⚠ Windows + uvicorn --reload 환경에서는 이벤트 루프가 비동기 subprocess를 지원하지
않을 수 있어(NotImplementedError), asyncio.create_subprocess_exec 대신
일반 subprocess.Popen 을 스레드(asyncio.to_thread)에서 돌린다 — 어떤 루프에서도 안전.
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
from pathlib import Path

MEDIAFORGE_ROOT = Path(__file__).resolve().parents[1]

_RE_PROGRESS = re.compile(r"\[scene\]\s+sc(\d+)\s+done.*progress=(\d+)/(\d+)")
_RE_DONE = re.compile(r"\[done\]\s+(.+)$")
_RE_BUNDLE = re.compile(r"\[bundle\]\s+(ch\d+)\s+'(.*)'\s+scenes=(\d+)")
_RE_TOTAL = re.compile(r"\[total\]\s+([\d.]+)s")
_RE_ERROR = re.compile(r"\[(?:error|ERROR)\]\s*(.*)$")


def _parse_only(only: list[int] | None) -> str:
    if not only:
        return ""
    return ",".join(str(int(n)) for n in only)


def _build_env() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(MEDIAFORGE_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run_blocking(args: list[str], on_event) -> dict:
    """동기 subprocess 실행 + 라인 단위 파싱 (스레드에서 호출)."""
    def emit(ev: dict) -> None:
        if on_event is not None:
            try:
                on_event(ev)
            except Exception:
                pass

    proc = subprocess.Popen(
        args,
        cwd=str(MEDIAFORGE_ROOT),
        env=_build_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    outputs: list[str] = []
    log_lines: list[str] = []
    completed = 0
    total = 0
    final_mp4: str | None = None

    assert proc.stdout is not None
    for raw in proc.stdout:
        line = raw.rstrip("\r\n")
        log_lines.append(line)
        emit({"type": "log", "line": line})

        m = _RE_PROGRESS.search(line)
        if m:
            completed, total = int(m.group(2)), int(m.group(3))
            emit({"type": "progress", "scene": int(m.group(1)),
                  "completed": completed, "total": total})
            continue
        m = _RE_BUNDLE.search(line)
        if m:
            total = int(m.group(3))
            emit({"type": "bundle", "chapter": m.group(1),
                  "title": m.group(2), "scenes": total})
            continue
        m = _RE_DONE.search(line)
        if m:
            path = m.group(1).strip()
            outputs.append(path)
            if path.lower().endswith("_final.mp4"):
                final_mp4 = path
            emit({"type": "done", "path": path})
            continue
        m = _RE_TOTAL.search(line)
        if m:
            emit({"type": "total", "seconds": float(m.group(1))})
            continue
        m = _RE_ERROR.search(line)
        if m:
            emit({"type": "error", "message": m.group(1)})

    rc = proc.wait()
    return {
        "ok": rc == 0,
        "returncode": rc,
        "outputs": outputs,
        "final_mp4": final_mp4,
        "completed": completed,
        "total": total,
        "log": "\n".join(log_lines),
    }


async def render(
    bundle_dir: str | Path,
    *,
    only: list[int] | None = None,
    dry_run: bool = False,
    keep_work: bool = False,
    extra_args: list[str] | None = None,
    on_event=None,
) -> dict:
    """mp4maker 실행. on_event(dict) 콜백으로 진행 상황을 흘려준다.

    이벤트 종류: {"type":"bundle"|"progress"|"done"|"total"|"log"|"error", ...}
    반환: {"ok","returncode","outputs","final_mp4","completed","total","log"}
    """
    bundle = Path(bundle_dir).resolve()
    args = [sys.executable, "-m", "mp4maker", str(bundle)]
    if dry_run:
        args.append("--dry-run")
    if keep_work:
        args.append("--keep-work")
    if only:
        args += ["--only", _parse_only(only)]
    if extra_args:
        args += list(extra_args)

    return await asyncio.to_thread(_run_blocking, args, on_event)


def _probe_blocking() -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "mp4maker", "--probe"],
        cwd=str(MEDIAFORGE_ROOT),
        env=_build_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {"ok": proc.returncode == 0, "returncode": proc.returncode, "text": proc.stdout}


async def probe() -> dict:
    """`python -m mp4maker --probe` — ffmpeg/폰트/패키지 점검."""
    return await asyncio.to_thread(_probe_blocking)
