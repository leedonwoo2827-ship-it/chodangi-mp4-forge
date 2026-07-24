"""슬라이드 렌더러 CLI.

    python -m slides <bundle_dir> [--motion off] [--only 1,3,5]

번들의 대본을 읽어 images/ (+ clips/) 에 슬라이드를 렌더한다. 레이아웃/모션을
파이프라인 없이 눈으로 확인할 때 쓴다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .fonts import font_source
from .render import generate_bundle_slides


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    p = argparse.ArgumentParser(prog="python -m slides",
                                description="문제집/강의 슬라이드 렌더 (images/ + clips/)")
    p.add_argument("bundle", help="번들 폴더 경로 (script/chNN_script.json 필요)")
    p.add_argument("--motion", choices=["on", "off"], default="on",
                   help="요소 순차 등장 모션 클립 생성 (기본 on; off=정적 PNG만)")
    p.add_argument("--only", default="", help="특정 씬만 (예: '1' 또는 '1,3,5')")
    args = p.parse_args(argv)

    only = None
    if args.only.strip():
        only = [int(x) for x in args.only.split(",") if x.strip()]

    print(f"[slides] font: {font_source()}")
    print(f"[slides] bundle: {Path(args.bundle).resolve()}  motion={args.motion}")

    def cb(ev: dict) -> None:
        if ev.get("type") == "log":
            print(ev.get("line", ""), flush=True)
        elif ev.get("type") == "progress" and ev.get("scene"):
            print(f"[slides] 씬 {ev['scene']}  ({ev['completed']}/{ev['total']})", flush=True)

    res = generate_bundle_slides(args.bundle, only=only, motion=(args.motion == "on"),
                                 on_progress=cb)
    print(f"\n[slides] 이미지 {len(res['images'])}개 · 클립 {len(res['clips'])}개"
          f"{' (모션)' if res['video_used'] else ' (정적)'}")
    if res["errors"]:
        print(f"[slides] 오류 {len(res['errors'])}건:")
        for e in res["errors"]:
            print("  - " + e)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
