"""05 lesson JSON + 영상 → 정답 체크 정적 웹 (파이프라인 06 폴더, WOWPASS 디자인).

<book>/05/*/source/lesson_*.json 을 모아 <book>/06/ 생성:
  06/check.html         WOWPASS 디자인 문제풀이+채점 화면
  06/problems.js        window.PROBLEMS (회차별, 지문/SQL/표/도식 포함)
  06/videos.js          window.VIDEOS (회차→해설영상 링크)
  06/assets/            present 디자인 자산(style.css, app.js, ui.js, fonts, logo)
  06/figs/              문제 도식 SVG (02/04/03/assets 에서 복사)
  06/videos/            해설 영상 (기본: 1회 5개만 복사 → 서버에 폴더째 업로드)

채점은 브라우저(클라이언트) JS → 서버 코드 0 → 06 폴더째 리눅스/PHP 서버에 올리면 그대로 동작.
이론은 화면 맨 앞 탭(자료 생기면 추가). hwpx 는 별도(사용자 MCP).

사용:
  python scripts/build_check.py
  python scripts/build_check.py --book D:/... --video-rounds 1,2   # 영상 복사할 회차
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = Path(__file__).with_name("check_template.html")
PRESENT_ASSETS = ROOT / "_context" / "present" / "assets"
_IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")


def _parse_bundle(bundle: str) -> tuple[int, int]:
    """m01-3 → (round=1, part=3). part 없으면 0."""
    m = re.search(r"m0*(\d+)(?:-(\d+))?", bundle or "")
    if not m:
        return 0, 0
    return int(m.group(1)), int(m.group(2) or 0)


def _svg_index(book: Path) -> dict[str, Path]:
    idx: dict[str, Path] = {}
    for sub in ("02/assets", "04/assets", "03/assets"):
        d = book / sub
        if d.is_dir():
            for f in d.glob("*.svg"):
                idx.setdefault(f.name, f)
    return idx


def _inline(text: str) -> set[str]:
    return {Path(u).name for u in _IMG_RE.findall(text or "")}


def collect(book: Path, figs_dir: Path):
    svg_idx = _svg_index(book)
    figs_dir.mkdir(parents=True, exist_ok=True)
    copied: set[str] = set()
    missing: set[str] = set()

    def ensure(name: str):
        base = Path(name).name
        if base in copied or base in missing:
            return
        src = svg_idx.get(base)
        if src:
            shutil.copy2(src, figs_dir / base)
            copied.add(base)
        else:
            missing.add(base)

    probs: list[dict] = []
    for lj in sorted((book / "05").glob("*/source/lesson_*.json")):
        try:
            d = json.loads(lj.read_text(encoding="utf-8"))
        except Exception:
            continue
        bundle = lj.parent.parent.name
        rn, _part = _parse_bundle(bundle)
        subj = d.get("subject") or ""
        for b in d.get("blocks") or []:
            if b.get("kind") != "problem" and not b.get("question"):
                continue
            q = b.get("question") or ""
            passage = b.get("passage") or ""
            expl = b.get("explanation") or ""
            inl_q = _inline(q) | _inline(passage)
            inl_e = _inline(expl)
            asset_field = {Path(a).name for a in (b.get("assets") or [])}
            figures = sorted(asset_field - inl_q - inl_e)
            for name in (asset_field | inl_q | inl_e):
                ensure(name)
            probs.append({
                "round_num": rn, "round": f"{rn}회" if rn else bundle, "bundle": bundle,
                "subject": b.get("subject") or subj, "number": b.get("number"),
                "difficulty": b.get("difficulty") or "", "question": q,
                "passage": passage, "sql": b.get("sql") or "", "table": b.get("table") or None,
                "figures": figures, "choices": [str(c) for c in (b.get("choices") or [])],
                "answer_index": b.get("answer_index"), "answer": b.get("answer") or "",
                "explanation": expl, "tags": b.get("tags") or [],
            })
    probs.sort(key=lambda p: (p["round_num"], p.get("number") or 0))
    return probs, copied, missing


def _num_range(bundle_dir: Path) -> tuple[int, int] | None:
    """번들의 문제 번호 min~max (라벨 '1~10번' 용)."""
    for lj in (bundle_dir / "source").glob("lesson_*.json"):
        try:
            d = json.loads(lj.read_text(encoding="utf-8"))
        except Exception:
            continue
        nums = [b.get("number") for b in (d.get("blocks") or []) if isinstance(b.get("number"), int)]
        if nums:
            return min(nums), max(nums)
    return None


def copy_videos(book: Path, out: Path, rounds: set[int]) -> dict:
    """지정 회차의 draft/*.static.mp4 를 06/videos 로 복사하고 VIDEOS 맵 반환.

    라벨은 문제 번호 범위: 'N회 1~10번' (파트=10문제 단위).
    """
    vdir = out / "videos"
    vids: dict[str, list] = {}
    for d in sorted((book / "05").glob("*/")):
        bundle = d.name
        rn, part = _parse_bundle(bundle)
        if rn not in rounds:
            continue
        mp4 = d / "draft" / f"{bundle}.static.mp4"
        if not mp4.exists():
            continue
        vdir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(mp4, vdir / mp4.name)
        rng = _num_range(d)
        label = f"{rn}회 {rng[0]}~{rng[1]}번" if rng else (f"{rn}회 {part}부" if part else f"{rn}회")
        vids.setdefault(f"{rn}회", []).append(
            {"label": label, "src": f"videos/{mp4.name}", "part": part})
    for k in vids:
        vids[k].sort(key=lambda v: v.get("part") or 0)
    return vids


def build_theory(book: Path, out: Path) -> tuple[list[dict], dict]:
    """03 요약노트 → 이론 탭 목록 + 내용(JS 에 구워넣을 dict) 반환.

    fetch/iframe 없이 file://·서버 둘 다 되도록, 각 요약 HTML 의 <style>+<body> 를 추출해
    theory_content.js(window.THEORY_HTML)로 굽는다. 도식 SVG 는 06/theory/assets 로 복사하고
    상대경로를 theory/ 기준으로 보정. 한글 파일명은 ASCII 키로 치환.
    """
    src = book / "03"
    if not src.is_dir():
        return [], {}
    tdir = out / "theory"
    tdir.mkdir(parents=True, exist_ok=True)
    if (src / "assets").is_dir():
        shutil.copytree(src / "assets", tdir / "assets", dirs_exist_ok=True)

    files = sorted(src.glob("summary_*.html"))
    name_map: dict[str, str] = {}
    i = 0
    for f in files:
        if f.name.isascii():
            name_map[f.name] = f.name
        else:
            i += 1
            name_map[f.name] = f"summary_ko{i}.html"

    def subject_of(html: str) -> tuple[int, str]:
        m = re.search(r"<h1[^>]*>([^<]*)</h1>", html) or re.search(r"<title>([^<]*)</title>", html)
        t = (m.group(1) if m else "").strip()
        mm = re.search(r"(\d+)\s*과목\s*[·:\-—\s]*(.*)", t)
        return (int(mm.group(1)), mm.group(2).strip(" —-·")) if mm else (99, t)

    content: dict[str, str] = {}
    items: list[dict] = []
    for f in files:
        raw = f.read_text(encoding="utf-8")
        styles = "".join(re.findall(r"<style[^>]*>(.*?)</style>", raw, re.S))
        mb = re.search(r"<body[^>]*>(.*?)</body>", raw, re.S)
        body = mb.group(1) if mb else raw
        # 내부 상호 링크 한글→ASCII
        for old, new in name_map.items():
            if old != new:
                body = body.replace(old, new)
        # 상대경로(assets 등) → theory/ 기준으로 (http:,data:,#,/,theory/ 는 제외)
        body = re.sub(r'(src|href)="(?!https?:|data:|#|/|theory/)([^"]+)"', r'\1="theory/\2"', body)
        # <style> 의 body 셀렉터 → :host (Shadow DOM 격리)
        styles = re.sub(r'(^|[^-\w.#])body\b', r'\1:host', styles)
        key = f"theory/{name_map[f.name]}"
        content[key] = "<style>:host{display:block;background:#fff}</style><style>" + styles + "</style>" + body
        if f.stem != "summary_index":
            n, name = subject_of(raw)
            lab = f"{n}과목 · {name}" if n != 99 else (f.stem.replace("summary_", "") + " 요약")
            items.append({"label": lab, "href": key, "sub": n})
    items.sort(key=lambda x: x["sub"])
    return items, content


def main(argv: list[str] | None = None) -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(prog="build_check.py",
                                 description="05 → 정답 체크 정적 웹(06, WOWPASS 디자인)")
    ap.add_argument("--book", default="D:/00work/ocr-output-260723")
    ap.add_argument("--out", default="")
    ap.add_argument("--video-rounds", default="all", help="영상 복사할 회차(콤마). 예: 1,2 · 'all'=전 회차 · 'none'=복사 안 함")
    args = ap.parse_args(argv)

    book = Path(args.book).resolve()
    out = Path(args.out).resolve() if args.out else (book / "06")
    out.mkdir(parents=True, exist_ok=True)
    if not TEMPLATE.exists():
        raise SystemExit(f"[error] 템플릿 없음: {TEMPLATE}")
    if not PRESENT_ASSETS.is_dir():
        raise SystemExit(f"[error] present 자산 없음: {PRESENT_ASSETS}")

    # 1) 디자인 자산 복사 (style.css/app.js/ui.js/fonts/logo)
    shutil.copytree(PRESENT_ASSETS, out / "assets", dirs_exist_ok=True)

    # 2) 문제 수집 + 도식 SVG → figs
    probs, copied, missing = collect(book, out / "figs")

    # 3) 영상 복사 → videos + VIDEOS 맵
    vr = args.video_rounds.strip().lower()
    if vr in ("", "none"):
        vids = {}
    else:
        if vr == "all":
            rounds = {_parse_bundle(d.name)[0] for d in (book / "05").glob("*/") if d.is_dir()}
            rounds.discard(0)
        else:
            rounds = {int(x) for x in re.findall(r"\d+", vr)}
        vids = copy_videos(book, out, rounds)

    # 4) 이론(03 요약노트) → 목록 + 내용(구워넣기)
    theory, theory_html = build_theory(book, out)

    # 5) 데이터 + 화면 파일
    (out / "problems.js").write_text(
        "window.PROBLEMS = " + json.dumps(probs, ensure_ascii=False) + ";\n", encoding="utf-8")
    (out / "videos.js").write_text(
        "window.VIDEOS = " + json.dumps(vids, ensure_ascii=False) + ";\n", encoding="utf-8")
    (out / "theory.js").write_text(
        "window.THEORY = " + json.dumps(theory, ensure_ascii=False) + ";\n", encoding="utf-8")
    (out / "theory_content.js").write_text(
        "window.THEORY_HTML = " + json.dumps(theory_html, ensure_ascii=False) + ";\n", encoding="utf-8")
    shutil.copy2(TEMPLATE, out / "check.html")

    n_rounds = len(set(p["round_num"] for p in probs if p["round_num"]))
    n_vid = sum(len(v) for v in vids.values())
    print(f"[check] {len(probs)}문제 · {n_rounds}회 → {out}\\check.html")
    print(f"        지문 {sum(1 for p in probs if p['passage'])} · SQL {sum(1 for p in probs if p['sql'])}"
          f" · 표 {sum(1 for p in probs if p['table'])} · SVG {len(copied)} · 영상 {n_vid}")
    if missing:
        print(f"[warn] SVG 못 찾음 {len(missing)}: {', '.join(sorted(missing))}")
    print("        → 06 폴더째 리눅스/PHP 서버에 업로드하면 그대로 동작합니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
