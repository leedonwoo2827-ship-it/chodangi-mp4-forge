"""도식(SVG/이미지) 참조 처리 — "지금 돌아가게" 조치.

배경: 상위 플러그인이 만든 lesson JSON 은 문제/해설 텍스트 안에 마크다운 이미지
(`![alt](assets/xxx.svg)`)로 도식을 참조하지만, 해당 SVG 가 04/ 로 함께 복사돼 오지
않았다(파일은 02/assets 에 실재). 또한 현재 슬라이드 렌더러(slides/layout.py)는
이미지를 렌더하지 않고 텍스트만 그리므로, 마크다운이 그대로 화면/음성에 노출된다.

이 모듈은 두 가지를 한다(둘 다 크래시 없이 안전):
1) strip_image_markdown: 슬라이드/음성 텍스트에서 `![alt](url)` 를 제거(→ 날 텍스트/오독 방지).
2) copy_lesson_figures: lesson 이 참조하는 SVG 를 소스(기본 02/assets)에서 번들로 복사.
   (선택) cairosvg 가 설치돼 있으면 PNG 로도 래스터라이즈해 둔다(없으면 조용히 스킵).

향후 상위 플러그인이 04/assets 를 제대로 채우거나 렌더러가 도식을 그리게 되면,
여기 소스 경로(MF_ASSETS_SRC)만 바꾸면 된다.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

# 마크다운 이미지: ![alt](url "title")  — url 안의 공백/타이틀도 관대하게 처리
_IMG_MD_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\(\s*(?P<url>[^)\s]+)(?:\s+[^)]*)?\)")

# 인라인 강조 마크다운 — 현재 렌더러/자막/TTS 는 마크다운을 해석하지 않아 리터럴로 노출되므로 제거.
# 단일 '*'(SELECT * 등)는 건드리지 않는다.
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.S)
_CODE_RE = re.compile(r"`([^`]+)`")


def strip_inline_markdown(text: str) -> str:
    """`**볼드**` 와 백틱 `코드` 표시를 텍스트만 남기고 제거."""
    if not text:
        return text or ""
    text = _BOLD_RE.sub(r"\1", text)
    text = _CODE_RE.sub(r"\1", text)
    return text

# 텍스트에서 참조하는 이미지 필드들(문제집 lesson 블록 기준)
_TEXT_FIELDS = ("question", "explanation", "explanation_speech", "passage",
                "narration", "narration_question", "narration_answer")


def iter_image_refs(text: str):
    """text 안의 (alt, url) 마크다운 이미지 참조를 순서대로 yield."""
    for m in _IMG_MD_RE.finditer(text or ""):
        yield m.group("alt"), m.group("url")


def strip_image_markdown(text: str, *, keep_alt: bool = False) -> str:
    """`![alt](url)` 를 제거. keep_alt=True 면 alt 텍스트만 남긴다.

    연속 공백/줄바꿈을 적당히 정리해 자연스러운 낭독/표시가 되게 한다.
    """
    if not text:
        return text or ""

    def _repl(m: re.Match) -> str:
        return (m.group("alt") or "").strip() if keep_alt else ""

    out = _IMG_MD_RE.sub(_repl, text)
    # 이미지 제거로 생긴 빈 줄/중복 공백 정리
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = re.sub(r"[ \t]+\n", "\n", out)
    return out.strip()


def clean_lesson_text_inplace(doc: dict, *, keep_alt: bool = False) -> int:
    """lesson 문서의 모든 블록 텍스트 필드에서 이미지 마크다운을 제거(제자리 수정).

    Returns: 제거한 이미지 참조 개수.
    """
    removed = 0
    for b in (doc.get("blocks") or []):
        if not isinstance(b, dict):
            continue
        for f in _TEXT_FIELDS:
            v = b.get(f)
            if not isinstance(v, str) or not v:
                continue
            if "![" in v:
                removed += sum(1 for _ in iter_image_refs(v))
                v = strip_image_markdown(v, keep_alt=keep_alt)
            b[f] = strip_inline_markdown(v)
    return removed


def _svg_to_png(svg_path: Path, png_path: Path) -> bool:
    """cairosvg 가 있으면 SVG→PNG 변환. 없거나 실패하면 False (조용히)."""
    try:
        import cairosvg  # type: ignore
    except Exception:
        return False
    try:
        cairosvg.svg2png(url=str(svg_path), write_to=str(png_path),
                         output_width=1280, output_height=720)
        return True
    except Exception:
        return False


def copy_lesson_figures(doc: dict, dest_dir: Path, src_dirs) -> dict:
    """lesson 이 참조하는 이미지(주로 .svg)를 src_dirs 에서 찾아 dest_dir 로 복사.

    - src_dirs: 소스 폴더 경로(들). 참조 url 의 파일명(basename)으로 매칭.
    - dest_dir: 번들의 assets 폴더(예: munje/chNN/images 또는 assets).
    - .svg 는 cairosvg 가 있으면 같은 이름 .png 로도 저장(베스트-에포트).

    Returns manifest: {"copied":[...], "missing":[...], "rasterized":[...]}.
    파일이 없어도 예외를 던지지 않는다(경고만).
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    src_dirs = [Path(s) for s in (src_dirs if isinstance(src_dirs, (list, tuple)) else [src_dirs])]

    wanted: dict[str, str] = {}   # basename -> original url
    for b in (doc.get("blocks") or []):
        if not isinstance(b, dict):
            continue
        for f in _TEXT_FIELDS:
            v = b.get(f)
            if isinstance(v, str) and "![" in v:
                for _alt, url in iter_image_refs(v):
                    wanted[Path(url).name] = url

    copied, missing, rasterized = [], [], []
    for name in sorted(wanted):
        found = None
        for sd in src_dirs:
            cand = sd / name
            if cand.is_file():
                found = cand
                break
        if not found:
            missing.append(name)
            continue
        target = dest_dir / name
        try:
            shutil.copy2(found, target)
            copied.append(name)
        except OSError:
            missing.append(name)
            continue
        if target.suffix.lower() == ".svg":
            if _svg_to_png(target, target.with_suffix(".png")):
                rasterized.append(target.with_suffix(".png").name)

    return {"copied": copied, "missing": missing, "rasterized": rasterized}
