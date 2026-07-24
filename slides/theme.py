"""슬라이드 색상 팔레트 — 밝은(라이트) 디자인 시스템.

motion-mp4-playwright(framecast)의 bright-* 팔레트를 이식했다: 거의 흰색 배경 +
2-스톱 그라디언트 + 진한 슬레이트 텍스트 + 회색 보조 + 하나의 강조색(accent)이
언더라인/불릿/뱃지/배경 블롭을 모두 통일한다. theme 키로 고르거나 subject/chapter 로 자동 배정.

키: bg_top→bg_bottom(세로 그라디언트), text(제목/본문 진한색), sub(보조 회색),
    accent(강조 파랑), accent2(보조 강조/블롭), answer(정답 강조 초록), card(흰 카드), line(옅은 구분선).
"""
from __future__ import annotations

# 각 팔레트: (r,g,b). bright 계열 = 밝은 배경 + 어두운 텍스트.
PALETTES: dict[str, dict] = {
    # bright-blue (기본)
    "sqld":    {"bg_top": (247, 249, 252), "bg_bottom": (234, 241, 251), "accent": (37, 99, 235),  "accent2": (124, 58, 237), "answer": (22, 163, 74),  "text": (31, 41, 55),  "sub": (100, 116, 139), "card": (255, 255, 255), "line": (226, 232, 240)},
    "default": {"bg_top": (247, 249, 252), "bg_bottom": (234, 241, 251), "accent": (37, 99, 235),  "accent2": (124, 58, 237), "answer": (22, 163, 74),  "text": (31, 41, 55),  "sub": (100, 116, 139), "card": (255, 255, 255), "line": (226, 232, 240)},
    # bright-slate
    "slate":   {"bg_top": (248, 250, 252), "bg_bottom": (238, 242, 247), "accent": (79, 70, 229),  "accent2": (14, 165, 233), "answer": (22, 163, 74),  "text": (15, 23, 42),   "sub": (100, 116, 139), "card": (255, 255, 255), "line": (226, 232, 240)},
    # bright-mint
    "math":    {"bg_top": (244, 251, 249), "bg_bottom": (226, 245, 239), "accent": (15, 157, 118), "accent2": (37, 99, 235),  "answer": (37, 99, 235),  "text": (18, 49, 42),   "sub": (92, 122, 114),  "card": (255, 255, 255), "line": (215, 236, 230)},
    # bright-rose
    "eng":     {"bg_top": (255, 247, 250), "bg_bottom": (253, 232, 240), "accent": (224, 65, 122), "accent2": (245, 158, 11),  "answer": (22, 163, 74),  "text": (43, 23, 33),   "sub": (138, 107, 118), "card": (255, 255, 255), "line": (242, 221, 229)},
    # bright-slate(violet accent) for science
    "science": {"bg_top": (248, 250, 252), "bg_bottom": (238, 242, 247), "accent": (124, 58, 237), "accent2": (14, 165, 233), "answer": (22, 163, 74),  "text": (15, 23, 42),   "sub": (100, 116, 139), "card": (255, 255, 255), "line": (226, 232, 240)},
    # bright-warm
    "amber":   {"bg_top": (255, 250, 245), "bg_bottom": (253, 238, 224), "accent": (234, 111, 30), "accent2": (224, 65, 122),  "answer": (22, 163, 74),  "text": (43, 35, 32),   "sub": (138, 122, 109), "card": (255, 255, 255), "line": (240, 227, 214)},
    # bright-forest
    "teal":    {"bg_top": (245, 250, 244), "bg_bottom": (230, 243, 226), "accent": (47, 158, 68),  "accent2": (15, 118, 110),  "answer": (37, 99, 235),  "text": (22, 40, 26),   "sub": (95, 122, 94),   "card": (255, 255, 255), "line": (220, 235, 215)},
}

# 회차별 자동 순환에 쓸 순서(테마 미지정 시 chapter 로 색을 돌린다).
_CYCLE = ["sqld", "slate", "math", "eng", "science", "amber", "teal", "default"]

# subject 힌트 → 팔레트
_SUBJECT_HINT = {
    "sqld": "sqld", "sql": "sqld", "데이터": "sqld",
    "수학": "math", "math": "math",
    "영어": "eng", "english": "eng", "eng": "eng",
    "과학": "science", "science": "science", "물리": "science", "화학": "science",
}


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def get_palette(theme: str = "", subject: str = "", chapter: int = 0) -> dict:
    """theme > subject > chapter 순으로 팔레트를 결정한다.

    theme 에 hex(#2563eb)를 주면 그 색을 accent 로 쓰는 커스텀 bright 팔레트가 된다.
    """
    t = (theme or "").strip()
    if t.startswith("#"):
        try:
            base = dict(PALETTES["default"])
            base["accent"] = _hex_to_rgb(t)
            return base
        except Exception:
            pass
    if t and t.lower() in PALETTES:
        return dict(PALETTES[t.lower()])
    subj = (subject or "").strip().lower()
    for key, pal in _SUBJECT_HINT.items():
        if key in subj:
            return dict(PALETTES[pal])
    if chapter:
        return dict(PALETTES[_CYCLE[(int(chapter) - 1) % len(_CYCLE)]])
    return dict(PALETTES["default"])
