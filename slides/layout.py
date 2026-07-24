"""Pillow 슬라이드 레이아웃 — 종류별 프레임을 그린다.

각 build_* 는 (base_image, elements) 를 돌려준다.
    base_image : 배경 + 항상 보이는 헤더(RGBA 1920x1080)
    elements   : [(layer_image, appear_time_sec), ...]  순차 등장 요소(각 전체화면 RGBA, 해당 요소만 그리고 나머지 투명)
정적 렌더는 base 위에 elements 를 순서대로 합성하면 된다.
모션 렌더(animate.py)는 base 위에 각 layer 를 appear_time 에 페이드인한다.
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from .fonts import load_font

W, H = 1920, 1080
PAD_X = 110
TOP_Y = 84
SAFE_BOTTOM = H - 150          # 이 아래로는 텍스트 금지(자막 안전영역)
CONTENT_W = W - 2 * PAD_X

APPEAR_START = 0.4
APPEAR_STEP = 0.5

_scratch = ImageDraw.Draw(Image.new("RGBA", (8, 8)))


# ----------------------------- 저수준 헬퍼 -----------------------------
def _measure(s: str, font: ImageFont.FreeTypeFont) -> float:
    return _scratch.textlength(s, font=font)


def _line_h(font: ImageFont.FreeTypeFont, gap: float = 0.35) -> int:
    a, d = font.getmetrics()
    return int((a + d) * (1 + gap))


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    out: list[str] = []
    for raw in (text or "").split("\n"):
        words = raw.split(" ")
        cur = ""
        for w in words:
            trial = w if not cur else cur + " " + w
            if _measure(trial, font) <= max_w:
                cur = trial
                continue
            if cur:
                out.append(cur)
                cur = ""
            if _measure(w, font) <= max_w:
                cur = w
            else:                                   # 공백 없는 긴 토큰 → 글자 단위
                piece = ""
                for ch in w:
                    if _measure(piece + ch, font) <= max_w:
                        piece += ch
                    else:
                        if piece:
                            out.append(piece)
                        piece = ch
                cur = piece
        out.append(cur)
    return out or [""]


def fit_text(text: str, base: int, min_size: int, max_w: int, max_h: int,
             bold: bool = False, gap: float = 0.35):
    """폰트를 base→min 으로 줄여가며 (max_w,max_h) 박스에 들어가는 크기를 찾는다.

    Returns (font, lines, line_height).
    """
    size = base
    while size >= min_size:
        font = load_font(size, bold=bold)
        lines = wrap_text(text, font, max_w)
        lh = _line_h(font, gap)
        if len(lines) * lh <= max_h:
            return font, lines, lh
        size -= 3
    font = load_font(min_size, bold=bold)
    lines = wrap_text(text, font, max_w)
    return font, lines, _line_h(font, gap)


def draw_lines(draw: ImageDraw.ImageDraw, lines, x: int, y: int,
               font, fill, lh: int, center_w: int | None = None) -> int:
    for ln in lines:
        dx = x
        if center_w is not None:
            dx = x + (center_w - int(_measure(ln, font))) // 2
        draw.text((dx, y), ln, font=font, fill=fill)
        y += lh
    return y


def _blank() -> Image.Image:
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def _gradient(pal: dict) -> Image.Image:
    """135° 2-스톱 그라디언트(bg_top→bg_bottom) + 우상단/좌하단 흐릿한 강조 블롭."""
    top, bot = pal["bg_top"], pal["bg_bottom"]
    base = Image.new("RGBA", (W, H))
    px = base.load()
    for y in range(H):
        t = y / (H - 1)
        r = int(top[0] + (bot[0] - top[0]) * t)
        g = int(top[1] + (bot[1] - top[1]) * t)
        b = int(top[2] + (bot[2] - top[2]) * t)
        for x in range(W):
            px[x, y] = (r, g, b, 255)
    # 배경 블롭(강조색 흐릿한 원) — framecast의 밝은 톤 재현
    a1 = tuple(pal.get("accent", (37, 99, 235)))
    a2 = tuple(pal.get("accent2", a1))
    blob = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(blob)
    bd.ellipse((W - 560, -200, W + 160, 520), fill=a1 + (42,))     # 우상단 ~720px
    bd.ellipse((-140, H - 380, 420, H + 180), fill=a2 + (42,))     # 좌하단 ~560px
    blob = blob.filter(ImageFilter.GaussianBlur(70))
    return Image.alpha_composite(base, blob)


def _chip(base: Image.Image, text: str, pal: dict, x: int = PAD_X, y: int = TOP_Y,
          bg=None, fg=(255, 255, 255)) -> tuple[int, int]:
    """라운드 칩을 (x,y)에 그린다. 반환값 = (칩 오른쪽 x, 칩 아래 y)."""
    d = ImageDraw.Draw(base)
    font = load_font(30, bold=True)
    tw = int(_measure(text, font))
    pad = 20
    bg = bg or pal["accent"]
    right = x + tw + pad * 2
    box = (x, y, right, y + 52)
    d.rounded_rectangle(box, radius=14, fill=bg + (255,) if len(bg) == 3 else bg)
    d.text((x + pad, y + 9), text, font=font, fill=fg)
    return right, y + 52


def _appear(i: int) -> float:
    return APPEAR_START + i * APPEAR_STEP


def _circled(n: int) -> str:
    return "①②③④⑤⑥⑦⑧⑨⑩"[n] if 0 <= n < 10 else f"{n + 1}."


def _strip_lead_circle(s: str) -> str:
    """보기 문자열이 이미 ①②③④ 로 시작하면 그 기호를 뗀다(렌더러가 별도로 그리므로 중복 방지)."""
    s = (s or "").lstrip()
    if s and s[0] in "①②③④⑤⑥⑦⑧⑨⑩":
        s = s[1:].lstrip(" .、·)")
    return s


# ----------------------------- 종류별 빌더 -----------------------------
def build_section(slide: dict, pal: dict):
    base = _gradient(pal)
    d = ImageDraw.Draw(base)
    title = slide.get("title") or ""
    subtitle = slide.get("subtitle") or ""
    tfont, tlines, tlh = fit_text(title, 92, 48, CONTENT_W, 360, bold=True)
    total_h = len(tlines) * tlh + (70 if subtitle else 0)
    y = (H - total_h) // 2
    # accent underline mark
    d.rounded_rectangle((PAD_X, y - 40, PAD_X + 90, y - 28), radius=6, fill=pal["accent"] + (255,))
    y = draw_lines(d, tlines, PAD_X, y, tfont, pal["text"] + (255,), tlh, center_w=CONTENT_W)
    if subtitle:
        sfont, slines, slh = fit_text(subtitle, 40, 26, CONTENT_W, 120)
        draw_lines(d, slines, PAD_X, y + 18, sfont, pal["sub"] + (255,), slh, center_w=CONTENT_W)
    return base, []


def build_concept(slide: dict, pal: dict):
    base = _gradient(pal)
    _, y = _chip(base, "개념", pal)
    d = ImageDraw.Draw(base)
    heading = slide.get("heading") or ""
    hfont, hlines, hlh = fit_text(heading, 66, 40, CONTENT_W, 200, bold=True)
    y = draw_lines(d, hlines, PAD_X, y + 24, hfont, pal["text"] + (255,), hlh)
    y += 30
    bullets = [str(x) for x in (slide.get("bullets") or [])]
    elements = []
    avail = SAFE_BOTTOM - y
    per = max(1, len(bullets))
    bfont, _, _ = fit_text("\n".join(bullets) or " ", 44, 30, CONTENT_W - 60, avail)
    blh = _line_h(bfont, 0.35)
    cy = y
    for i, bt in enumerate(bullets):
        layer = _blank()
        ld = ImageDraw.Draw(layer)
        bx, by = PAD_X + 4, cy + blh // 2 - 11
        ld.rounded_rectangle((bx, by, bx + 22, by + 22), radius=6, fill=pal["accent"] + (255,))
        lines = wrap_text(bt, bfont, CONTENT_W - 60)
        draw_lines(ld, lines, PAD_X + 48, cy, bfont, pal["text"] + (255,), blh)
        elements.append((layer, _appear(i)))
        cy += blh * len(lines) + 18
    return base, elements


def build_ox(slide: dict, pal: dict):
    base = _gradient(pal)
    _, y = _chip(base, "OX 정리", pal)
    d = ImageDraw.Draw(base)
    heading = slide.get("heading") or ""
    hfont, hlines, hlh = fit_text(heading, 60, 38, CONTENT_W, 160, bold=True)
    y = draw_lines(d, hlines, PAD_X, y + 24, hfont, pal["text"] + (255,), hlh)
    y += 24
    items = slide.get("items") or []
    elements = []
    qfont = load_font(40, bold=False)
    nfont = load_font(30)
    qlh = _line_h(qfont, 0.3)
    cy = y
    for i, it in enumerate(items):
        q = str(it.get("q") or "")
        a = str(it.get("a") or "").upper()
        note = str(it.get("note") or "")
        is_o = a in ("O", "0", "참", "TRUE", "T")
        badge = pal["answer"] if is_o else (220, 68, 60)
        layer = _blank()
        ld = ImageDraw.Draw(layer)
        # O/X 배지
        ld.ellipse((PAD_X, cy, PAD_X + 56, cy + 56), outline=badge + (255,), width=5)
        bt = "O" if is_o else "X"
        bf = load_font(38, bold=True)
        bw = int(_measure(bt, bf))
        ld.text((PAD_X + 28 - bw // 2, cy + 5), bt, font=bf, fill=badge + (255,))
        qlines = wrap_text(q, qfont, CONTENT_W - 90)
        yy = draw_lines(ld, qlines, PAD_X + 78, cy, qfont, pal["text"] + (255,), qlh)
        if note:
            nlines = wrap_text("→ " + note, nfont, CONTENT_W - 90)
            yy = draw_lines(ld, nlines, PAD_X + 78, yy + 2, nfont, pal["sub"] + (255,), _line_h(nfont, 0.25))
        elements.append((layer, _appear(i)))
        cy = max(yy, cy + 64) + 22
        if cy > SAFE_BOTTOM:
            break
    return base, elements


def build_table(slide: dict, pal: dict):
    base = _gradient(pal)
    _, y = _chip(base, "정리", pal)
    d = ImageDraw.Draw(base)
    heading = slide.get("heading") or ""
    hfont, hlines, hlh = fit_text(heading, 60, 38, CONTENT_W, 140, bold=True)
    y = draw_lines(d, hlines, PAD_X, y + 20, hfont, pal["text"] + (255,), hlh)
    y += 24
    cols = [str(c) for c in (slide.get("columns") or [])]
    rows = [[str(c) for c in r] for r in (slide.get("rows") or [])]
    ncol = max(1, len(cols) or (len(rows[0]) if rows else 1))
    col_w = CONTENT_W // ncol
    row_h = min(72, max(48, (SAFE_BOTTOM - y - 60) // max(1, len(rows) + 1)))
    cfont = load_font(min(38, row_h - 20), bold=False)
    hfont2 = load_font(min(36, row_h - 22), bold=True)
    elements = []
    # 헤더 행(항상 보임)
    if cols:
        d.rounded_rectangle((PAD_X, y, PAD_X + CONTENT_W, y + row_h), radius=10,
                            fill=pal["accent"] + (255,))
        for ci, c in enumerate(cols):
            d.text((PAD_X + ci * col_w + 18, y + (row_h - hfont2.size) // 2 - 2), c,
                   font=hfont2, fill=(255, 255, 255, 255))
        y += row_h + 6
    for ri, row in enumerate(rows):
        layer = _blank()
        ld = ImageDraw.Draw(layer)
        bg = (255, 255, 255, 18) if ri % 2 == 0 else (255, 255, 255, 8)
        ld.rounded_rectangle((PAD_X, y, PAD_X + CONTENT_W, y + row_h), radius=8, fill=bg)
        for ci in range(ncol):
            cell = row[ci] if ci < len(row) else ""
            fill = pal["accent"] if ci == 0 else pal["text"]
            ld.text((PAD_X + ci * col_w + 18, y + (row_h - cfont.size) // 2 - 2),
                    cell, font=cfont, fill=fill + (255,))
        elements.append((layer, _appear(ri)))
        y += row_h + 6
        if y > SAFE_BOTTOM:
            break
    return base, elements


def build_problem(slide: dict, pal: dict):
    base = _gradient(pal)
    num = slide.get("number")
    meta = slide.get("meta") or {}
    chip = f"문제 {num}" if num is not None else "문제"
    right, y = _chip(base, chip, pal)
    if meta.get("difficulty"):
        _chip(base, f"난이도 {meta['difficulty']}", pal, x=right + 12, y=TOP_Y,
              bg=pal.get("line", (226, 232, 240)), fg=pal["sub"] + (255,))
    d = ImageDraw.Draw(base)
    passage = (slide.get("passage") or "").strip()
    y += 26
    if passage:
        pfont, plines, plh = fit_text(passage, 34, 26, CONTENT_W, 150)
        y = draw_lines(d, plines, PAD_X, y, pfont, pal["sub"] + (255,), plh) + 10
    question = slide.get("question") or ""
    qfont, qlines, qlh = fit_text(question, 54, 34, CONTENT_W, 300, bold=True)
    y = draw_lines(d, qlines, PAD_X, y, qfont, pal["text"] + (255,), qlh)
    y += 34
    choices = [_strip_lead_circle(str(c)) for c in (slide.get("choices") or [])]
    # 보기가 너무 길면 문제 화면에선 생략(교재 참고) — TTS는 보기를 그대로 낭독한다.
    # slide["hide_choices"] 로 명시 가능, 없으면 길이로 자동 판단.
    hide = slide.get("hide_choices")
    if hide is None and choices:
        total = sum(len(c) for c in choices)
        hide = total > 220 or any(len(c) > 90 for c in choices)
    elements = []
    if choices and not hide:
        avail = SAFE_BOTTOM - y
        joined = "\n".join(choices)
        cfont, _, _ = fit_text(joined, 44, 28, CONTENT_W - 70, avail)
        clh = _line_h(cfont, 0.3)
        cy = y
        for i, ch in enumerate(choices):
            layer = _blank()
            ld = ImageDraw.Draw(layer)
            ld.text((PAD_X, cy), _circled(i), font=load_font(cfont.size, bold=True),
                    fill=pal["accent"] + (255,))
            lines = wrap_text(ch, cfont, CONTENT_W - 70)
            draw_lines(ld, lines, PAD_X + 56, cy, cfont, pal["text"] + (255,), clh)
            elements.append((layer, _appear(i)))
            cy += clh * len(lines) + 16
    elif choices and hide:
        hint = "① ~ " + _circled(len(choices) - 1) + " 보기는 교재를 참고하세요"
        d.text((PAD_X, y + 8), hint, font=load_font(38, bold=False), fill=pal["sub"] + (255,))
    return base, elements


def build_answer(slide: dict, pal: dict):
    base = _gradient(pal)
    num = slide.get("number")
    page, total = slide.get("page") or 1, slide.get("total_pages") or 1
    chip = f"정답 및 해설 {num}" if num is not None else "정답 및 해설"
    if total > 1:
        chip += f" ({page}/{total})"
    _, y = _chip(base, chip, pal, bg=pal["answer"])
    d = ImageDraw.Draw(base)
    # 출처(회차·번호) 칩 — 우상단, 작고 은은하게
    src = str(slide.get("source") or "").strip()
    if src:
        sfont = load_font(26, bold=False)
        label = f"출처 · {src}"
        sw = int(_measure(label, sfont))
        rx = W - PAD_X - sw - 32
        d.rounded_rectangle((rx, TOP_Y + 4, rx + sw + 32, TOP_Y + 46), radius=12,
                            fill=(255, 255, 255, 26))
        d.text((rx + 16, TOP_Y + 11), label, font=sfont, fill=pal["sub"] + (255,))
    y += 26
    elements = []
    choices = [_strip_lead_circle(str(c)) for c in (slide.get("choices") or [])]
    ai = slide.get("answer_index")
    ans = str(slide.get("answer") or "").strip()
    show_choices = slide.get("show_choices", True)

    if show_choices:
        # 정답 강조 박스(팝)
        if choices and isinstance(ai, int) and 0 <= ai < len(choices):
            correct = f"{_circled(ai)}  {choices[ai]}"
        elif ans:
            correct = f"정답: {ans}"
        else:
            correct = "정답"
        afont, alines, alh = fit_text(correct, 50, 32, CONTENT_W - 60, 170, bold=True)
        box_h = len(alines) * alh + 28
        layer = _blank()
        ld = ImageDraw.Draw(layer)
        ld.rounded_rectangle((PAD_X, y, PAD_X + CONTENT_W, y + box_h), radius=14,
                             fill=pal["answer"] + (46,), outline=pal["answer"] + (255,), width=4)
        draw_lines(ld, alines, PAD_X + 30, y + 14, afont, pal["text"] + (255,), alh)
        elements.append((layer, APPEAR_START))
        y += box_h + 26

    explanation = (slide.get("explanation") or "").strip()
    if explanation:
        label = "해설" if page == 1 else f"해설 (계속 {page}/{total})"
        d.text((PAD_X, y), label, font=load_font(30, bold=True), fill=pal["accent"] + (255,))
        y += 46
        efont, elines, elh = fit_text(explanation, 40, 26, CONTENT_W, SAFE_BOTTOM - y)
        layer = _blank()
        ld = ImageDraw.Draw(layer)
        draw_lines(ld, elines, PAD_X, y, efont, pal["text"] + (255,), elh)
        elements.append((layer, APPEAR_START + (0.5 if show_choices else 0.0)))
    return base, elements


def build_countdown_base(slide: dict, pal: dict) -> Image.Image:
    """카운트다운 배경 = 앞 문제 전체(질문+보기)를 그대로 보여준다. 타이머는 프레임별로."""
    prob = {"kind": "problem", "number": slide.get("number"),
            "question": slide.get("question") or "", "choices": slide.get("choices") or [],
            "passage": slide.get("passage") or "", "meta": slide.get("meta") or {}}
    base, elements = build_problem(prob, pal)
    for layer, _t in elements:               # 보기까지 모두 펼쳐 정적으로
        base = Image.alpha_composite(base, layer)
    return base


def draw_countdown_number(base: Image.Image, n: int, pal: dict) -> Image.Image:
    """문제 위에 우하단 타이머 배지(숫자 n)를 그린 RGB 프레임."""
    img = base.copy()
    d = ImageDraw.Draw(img)
    cx, cy, r = W - 175, H - 175, 95
    # 흰 원 + 강조색 테두리(라이트 톤). 뒤에 옅은 강조 글로우.
    d.ellipse((cx - r - 10, cy - r - 10, cx + r + 10, cy + r + 10),
              fill=pal["accent"] + (28,))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 240),
              outline=pal["accent"] + (255,), width=10)
    nf = load_font(120, bold=True)
    s = str(n)
    bb = d.textbbox((0, 0), s, font=nf)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    d.text((cx - tw // 2 - bb[0], cy - th // 2 - bb[1]), s, font=nf, fill=pal["accent"] + (255,))
    hint = load_font(28, bold=True)
    hl = "생각할 시간"
    hw = int(_measure(hl, hint))
    d.text((cx - hw // 2, cy - r - 44), hl, font=hint, fill=pal["sub"] + (255,))
    return img.convert("RGB")


def build_gap(slide: dict, pal: dict) -> Image.Image:
    """해설→다음 문제 사이 간격 슬라이드 — 은은한 '다음 문제 ▶'."""
    base = _gradient(pal)
    d = ImageDraw.Draw(base)
    f = load_font(46, bold=True)
    t = "다음 문제 ▶"
    tw = int(_measure(t, f))
    d.text(((W - tw) // 2, H // 2 - 30), t, font=f, fill=pal["sub"] + (230,))
    return base.convert("RGB")


_BUILDERS = {
    "section": build_section,
    "concept": build_concept,
    "ox": build_ox,
    "table": build_table,
    "problem": build_problem,
    "answer": build_answer,
}


def build(slide: dict, pal: dict):
    """slide['kind'] 에 맞는 빌더로 (base, elements) 생성. 미지원이면 section 폴백."""
    kind = (slide or {}).get("kind") or "section"
    builder = _BUILDERS.get(kind, build_section)
    return builder(slide or {}, pal)


def compose_static(base: Image.Image, elements) -> Image.Image:
    """base 위에 모든 element 를 합성한 최종 프레임(포스터/정적)."""
    out = base.copy()
    for layer, _t in elements:
        out = Image.alpha_composite(out, layer)
    return out.convert("RGB")
