"""mediaforge 통합 FastAPI 앱.

- voicewright 의 코어(엔진/배치/발음사전)와 발음사전 편집 API/페이지를 재사용
- mediaforge 파이프라인 API(/api/mf/*): 번들·이미지 가져오기·음성·렌더·한번에
- 단일 포트(기본 8830)·단일 UI. mp4maker 는 subprocess 로 흡수.

실행: uvicorn app.main:app  (또는 run.bat / run.sh)
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# voicewright settings 가 읽을 경로를 mediaforge 기준으로 고정 (import 전에).
os.environ.setdefault("VOICEWRIGHT_VOICE_MAP", str(ROOT / "config" / "voice_map.yaml"))
os.environ.setdefault("VOICEWRIGHT_PRONUNCIATION_MAP", str(ROOT / "config" / "pronunciation_map.yaml"))
os.environ.setdefault("VOICEWRIGHT_ASSETS_DIR", str(ROOT / "assets"))
os.environ.setdefault("VOICEWRIGHT_WORKSPACE", os.environ.get("MF_OUTPUT_DIR") or str(ROOT / "munje"))

import logging  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

VW_WEB = ROOT / "voicewright" / "web"
MF_TEMPLATES = ROOT / "app" / "web" / "templates"


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    app = FastAPI(title="compy-ui", version="0.1.0",
                  description="문제집(JSON)→슬라이드→음성/자막→MP4 (로컬, ComfyUI 불필요)")

    # voicewright 의 정적 자산 재사용 (/dict 페이지가 /static/dict.* 를 참조)
    app.mount("/static", StaticFiles(directory=str(VW_WEB / "static")), name="static")

    # voicewright API 재사용: /api/dict*, /api/voices, /api/to_pronunciation,
    # /api/synthesize_scene 등 (발음사전 편집·미리듣기). 번들 파이프라인은 /api/mf.
    from voicewright.server.routes_api import router as vw_api
    from .routes_pipeline import router as mf_router

    app.include_router(vw_api, prefix="/api", tags=["voicewright"])
    app.include_router(mf_router, prefix="/api/mf", tags=["mediaforge"])

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return (MF_TEMPLATES / "index.html").read_text(encoding="utf-8")

    @app.get("/dict", response_class=HTMLResponse)
    async def dict_page() -> str:
        # voicewright 발음 사전 편집 페이지 그대로 재사용
        return (VW_WEB / "templates" / "dict.html").read_text(encoding="utf-8")

    return app


app = create_app()
