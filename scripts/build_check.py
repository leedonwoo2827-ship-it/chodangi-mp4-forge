"""05 lesson JSON들 → 정답 체크 정적 웹 (파이프라인 06 폴더).

<book>/05/*/source/lesson_*.json 을 모아 <book>/06/{problems.js, check.html} 생성.
- 5개 파트(m0N-1..m0N-5)를 'N회'로 묶고, 회차→번호 순 정렬.
- 채점은 브라우저(클라이언트) JS. 서버 코드 0 → 06 폴더째 리눅스/PHP 서버에 올리면 그대로 동작.
- 이론(theory)은 화면 맨 앞 항목(자료 생기면 추가). hwpx 는 별도(사용자 MCP).

사용:
  python scripts/build_check.py                         # 기본 book, 06 으로
  python scripts/build_check.py --book D:/... --out D:/.../07
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

TEMPLATE = Path(__file__).with_name("check_template.html")


def _round_num(bundle: str, fallback: str = "") -> int:
    m = re.search(r"m0*(\d+)", (bundle or "")) or re.search(r"(\d+)", (fallback or ""))
    return int(m.group(1)) if m else 0


def collect(book: Path) -> list[dict]:
    probs: list[dict] = []
    for lj in sorted((book / "05").glob("*/source/lesson_*.json")):
        try:
            d = json.loads(lj.read_text(encoding="utf-8"))
        except Exception:
            continue
        bundle = lj.parent.parent.name           # …/05/<bundle>/source/lesson_*.json
        rn = _round_num(bundle, str(d.get("round", "")))
        subj = d.get("subject") or ""
        for b in d.get("blocks") or []:
            if b.get("kind") != "problem" and not b.get("question"):
                continue
            probs.append({
                "round_num": rn,
                "round": f"{rn}회" if rn else (d.get("round") or bundle),
                "bundle": bundle,
                "subject": b.get("subject") or subj,
                "number": b.get("number"),
                "difficulty": b.get("difficulty") or "",
                "question": b.get("question") or "",
                "choices": [str(c) for c in (b.get("choices") or [])],
                "answer_index": b.get("answer_index"),
                "answer": b.get("answer") or "",
                "explanation": b.get("explanation") or "",
                "tags": b.get("tags") or [],
            })
    probs.sort(key=lambda p: (p["round_num"], p.get("number") or 0))
    return probs


def main(argv: list[str] | None = None) -> int:
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(prog="build_check.py",
                                 description="05 lesson JSON → 정답 체크 정적 웹(06)")
    ap.add_argument("--book", default="D:/00work/ocr-output-260723", help="책 루트")
    ap.add_argument("--out", default="", help="출력 폴더(기본: <book>/06)")
    args = ap.parse_args(argv)

    book = Path(args.book).resolve()
    out = Path(args.out).resolve() if args.out else (book / "06")
    out.mkdir(parents=True, exist_ok=True)

    if not TEMPLATE.exists():
        raise SystemExit(f"[error] 템플릿 없음: {TEMPLATE}")

    probs = collect(book)
    (out / "problems.js").write_text(
        "window.PROBLEMS = " + json.dumps(probs, ensure_ascii=False) + ";\n", encoding="utf-8")
    shutil.copy2(TEMPLATE, out / "check.html")

    n_rounds = len(set(p["round_num"] for p in probs if p["round_num"]))
    print(f"[check] {len(probs)}문제 · {n_rounds}회 → {out}\\check.html")
    print("        폴더째 서버로 올리거나, check.html 을 브라우저로 열면 됩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
