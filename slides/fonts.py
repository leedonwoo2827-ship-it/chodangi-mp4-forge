"""Pillow 슬라이드용 한글 폰트 로더.

우선순위: 프로젝트 번들(assets/fonts/Pretendard-*.ttf) → mp4maker.fonts.find_font()
가 찾아준 시스템 폰트 경로(맑은 고딕 등). 크기·굵기별로 ImageFont 를 캐시한다.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

_ROOT = Path(__file__).resolve().parents[1]
_FONT_DIR = _ROOT / "assets" / "fonts"

_BOLD_CANDIDATES = ["Pretendard-Bold.ttf", "Pretendard-SemiBold.ttf", "Pretendard-Bold.otf"]
_REG_CANDIDATES = ["Pretendard-Regular.ttf", "Pretendard-Medium.ttf", "Pretendard-Regular.otf"]


def _bundled(bold: bool) -> Path | None:
    for fn in (_BOLD_CANDIDATES if bold else _REG_CANDIDATES):
        p = _FONT_DIR / fn
        if p.is_file():
            return p
    return None


@lru_cache(maxsize=1)
def _system_font_path() -> Path | None:
    """mp4maker.fonts.find_font() 가 알려주는 시스템 한글 TTF 경로."""
    try:
        from mp4maker.fonts import find_font
        _, path = find_font()
        return path
    except Exception:
        return None


@lru_cache(maxsize=128)
def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = _bundled(bold) or _bundled(not bold) or _system_font_path()
    if path is not None:
        try:
            return ImageFont.truetype(str(path), size=size)
        except Exception:
            pass
    # 최후 폴백(한글이 깨질 수 있으나 크래시 방지)
    try:
        return ImageFont.truetype("malgun.ttf", size=size)
    except Exception:
        return ImageFont.load_default()


def font_source() -> str:
    p = _bundled(True) or _bundled(False)
    if p:
        return f"bundled Pretendard ({p.name})"
    sp = _system_font_path()
    return f"system ({sp})" if sp else "PIL default (한글 깨질 수 있음 — assets/fonts 에 Pretendard 넣으세요)"
