"""deck.html → 슬라이드 PNG 캡처 (headless Chromium via Playwright).

pressplay connect_deck.py 역할. 05/<회차>/source/deck.html 의 각 `.slide`(1920×1080)를
헤드리스 크로미움으로 스크린샷해 밝은 슬라이드 PNG 를 만든다. Pillow 로 그리던 어두운
슬라이드를 대체한다(#3 일반영상 슬라이드 소스 전환).

카운트다운/간격 씬은 deck 슬라이드가 없으므로 여기 Pillow 헬퍼로 밝게 생성한다.

의존성: playwright(+chromium). 설치:
    pip install playwright && python -m playwright install chromium
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
CAPTURE_HIDE_CSS = ".nav,#fs{display:none!important}"
SLIDE_W, SLIDE_H = 1920, 1080


def capture_deck(deck_html: str | Path, out_dir: str | Path,
                 filenames: list[str]) -> tuple[list[Path], int, list[tuple[int, int]]]:
    """deck.html 의 `.slide` 들을 순서대로 PNG 로 캡처.

    filenames[i] = i번째 캡처 슬라이드 저장 파일명(캡처 씬 순서와 1:1).
    Returns (저장경로 목록, deck 내 실제 .slide 개수, 넘침 목록).
    넘침 목록 = `.slide` 콘텐츠가 1080px 를 넘어 잘린 슬라이드 [(0-based 인덱스, 초과 px)].
    (#2 build-deck 의 페이지 분할이 제대로 됐는지 렌더 시점에 확인하는 용도.)
    """
    from playwright.sync_api import sync_playwright  # 지연 import (선택 의존성)

    deck_html = Path(deck_html).resolve()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": SLIDE_W, "height": SLIDE_H},
                                device_scale_factor=1)
        page.goto(deck_html.as_uri(), wait_until="networkidle")
        page.add_style_tag(content=CAPTURE_HIDE_CSS)
        try:
            page.evaluate("document.fonts && document.fonts.ready")
        except Exception:
            pass
        page.wait_for_timeout(300)
        slides = page.query_selector_all(".slide")
        try:
            metrics = page.eval_on_selector_all(
                ".slide", "els => els.map(e => [e.scrollHeight, e.clientHeight])")
        except Exception:
            metrics = []
        overflow = [(i, sh - ch) for i, (sh, ch) in enumerate(metrics) if sh > ch + 1]
        n = min(len(slides), len(filenames))
        for i in range(n):
            try:
                slides[i].scroll_into_view_if_needed()
            except Exception:
                pass
            dest = out_dir / filenames[i]
            slides[i].screenshot(path=str(dest))
            saved.append(dest)
        browser.close()
    return saved, len(slides), overflow


# --------------------------------------------------------------------------- Pillow 헬퍼
def _num_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """assets 안의 트루타입 폰트(있으면)로 큰 숫자용 폰트 로드, 없으면 기본."""
    for pat in ("*.ttf", "*.otf", "*.TTF", "*.OTF"):
        for f in (ROOT / "assets").rglob(pat):
            try:
                return ImageFont.truetype(str(f), size)
            except Exception:
                continue
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()


def countdown_frames(base_png: str | Path, seconds: int) -> list[Image.Image]:
    """캡처한 문제 슬라이드(밝음) 위에 5→1 카운트다운을 '우하단에 작게' 얹은 프레임(각 1초).

    문제를 가리지 않도록 전체 화면을 어둡게 하지 않고, 우하단 원형 배지만 올린다.
    (#2 _deck.css 의 .slide.countdown 우하단 규약과 일치)
    """
    base = Image.open(base_png).convert("RGB").resize((SLIDE_W, SLIDE_H))
    font = _num_font(150)
    r = 110
    margin = 72
    cx, cy = SLIDE_W - margin - r, SLIDE_H - margin - r
    frames: list[Image.Image] = []
    for n in range(int(seconds), 0, -1):
        im = base.copy()
        d = ImageDraw.Draw(im, "RGBA")
        # 전체 스크림 없음 — 문제는 그대로 보인다. 우하단에 그림자 + 흰 원 배지만.
        d.ellipse([cx - r - 6, cy - r - 6, cx + r + 6, cy + r + 6], fill=(15, 23, 42, 70))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, 240))
        text = str(n)
        bbox = d.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text((cx - tw / 2 - bbox[0], cy - th / 2 - bbox[1]), text,
               fill=(37, 99, 235, 255), font=font)
        frames.append(im)
    return frames or [base]


def solid_frame(color: tuple[int, int, int] = (255, 255, 255)) -> Image.Image:
    """간격(gap) 씬용 밝은 단색 프레임."""
    return Image.new("RGB", (SLIDE_W, SLIDE_H), color)
