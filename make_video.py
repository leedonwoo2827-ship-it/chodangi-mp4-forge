"""헤드리스 렌더 드라이버 — lesson JSON 한 개 → MP4 (웹 UI 없이).

app/routes_pipeline.py 의 ⚡ '한 번에 만들기'(레슨 경로)를 CLI 로 그대로 재현한다:
  1) lesson JSON 파싱 + 도식(SVG) 번들 복사 + 이미지 마크다운 정리
  2) lesson → 대본(scenes) 컴파일 → munje/chNN/script/chNN_script.json
  3) 슬라이드 PNG(+모션 클립: 문제→해설 사이 54321 카운트다운 포함) 렌더
  4) Supertonic3 로컬 TTS 로 음성/자막 (LLM/클라우드 없음 — 발음사전 기반)
  5) mp4maker(ffmpeg) 합성 → munje/chNN/draft/chNN_final.mp4

ComfyUI·LLM·FastAPI 를 import 하지 않으므로 requirements-render.txt 최소 의존성으로 동작한다.

사용:
  python make_video.py --lesson "D:\\00work\\ocr-output-260723\\04\\lesson_m01.json" --chapter 1
  python make_video.py --lesson ... --chapter 1 --only 1,2,3,4   # 특정 씬만(빠른 테스트)
  python make_video.py --lesson ... --chapter 1 --no-audio       # 음성 생략(슬라이드/합성만)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# voicewright 가 읽을 경로를 고정 (voicewright import 전에 — app/main.py 와 동일).
os.environ.setdefault("VOICEWRIGHT_VOICE_MAP", str(ROOT / "config" / "voice_map.yaml"))
os.environ.setdefault("VOICEWRIGHT_PRONUNCIATION_MAP", str(ROOT / "config" / "pronunciation_map.yaml"))
os.environ.setdefault("VOICEWRIGHT_ASSETS_DIR", str(ROOT / "assets"))
os.environ.setdefault("VOICEWRIGHT_WORKSPACE", os.environ.get("MF_OUTPUT_DIR") or str(ROOT / "munje"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import bundles                       # noqa: E402
from services import figures, workbook        # noqa: E402
from slides.render import generate_bundle_slides  # noqa: E402


def _parse_only(s: str) -> list[int] | None:
    if not s or not s.strip():
        return None
    return [int(x) for x in s.split(",") if x.strip()]


def _default_assets_srcs(lesson_path: Path) -> list[Path]:
    """도식 SVG 소스 폴더 후보. 04/lesson_*.json → 형제 02/assets 를 우선."""
    stage_dir = lesson_path.parent           # ...\04
    book_dir = stage_dir.parent              # ...\ocr-output-260723
    return [
        stage_dir / "assets",                # 04/assets (있으면 최우선)
        book_dir / "02" / "assets",          # 02/assets (실제 SVG 위치)
        book_dir / "03" / "assets",
        stage_dir,                           # 04/ 자체
    ]


def _write_script(root: Path, chapter: int, script: dict) -> Path:
    (root / "script").mkdir(parents=True, exist_ok=True)
    out = root / "script" / f"ch{chapter:02d}_script.json"
    out.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _truncate_problems(doc: dict, max_problems: int) -> None:
    """앞 max_problems 개 문제까지만 남긴다(빠른 테스트용). section 등은 그대로 유지."""
    kept, n = [], 0
    for b in (doc.get("blocks") or []):
        if b.get("kind") == "problem":
            if n >= max_problems:
                continue
            n += 1
        kept.append(b)
    doc["blocks"] = kept


def _out5_dir(lesson_path: Path) -> Path:
    """04\\lesson_mXX.json → 형제 05 폴더(완성 영상 스테이지)."""
    return lesson_path.parent.parent / "05"


def _out_name(lesson_path: Path) -> str:
    """lesson_m01.json → 'm01' (05\\m01.mp4)."""
    stem = lesson_path.stem
    return stem[len("lesson_"):] if stem.startswith("lesson_") else stem


def build(lesson_path: Path, chapter: int, only: list[int] | None,
          assets_srcs: list[Path], do_audio: bool, max_problems: int = 0,
          out_dir: Path | None = None) -> Path:
    print(f"[make] lesson = {lesson_path}")
    text = lesson_path.read_text(encoding="utf-8")
    doc = workbook.parse_lesson_doc(text)
    if doc is None:
        raise SystemExit(f"[error] 유효한 레슨 JSON 이 아닙니다: {lesson_path}")
    if max_problems > 0:
        _truncate_problems(doc, max_problems)
        print(f"[make] --max-problems {max_problems}: 앞 {max_problems}문제만 렌더")

    name = f"ch{chapter:02d}"
    root = bundles.create_bundle(name)
    print(f"[make] bundle = {root}")

    # 1) 도식(SVG) 번들 복사 (원본 doc 참조 그대로 — 정리 전에 스캔)
    manifest = figures.copy_lesson_figures(doc, root / "images", assets_srcs)
    print(f"[make] figures: 복사 {len(manifest['copied'])} · 누락 {len(manifest['missing'])}"
          f" · PNG변환 {len(manifest['rasterized'])}")
    if manifest["missing"]:
        print(f"[warn] SVG 소스에서 못 찾음(무시하고 진행): {', '.join(manifest['missing'])}")

    # 2) 컴파일 (내부에서 이미지 마크다운 정리됨) → 대본 저장
    script = workbook.lesson_to_script(doc, chapter=chapter)
    sp = _write_script(root, chapter, script)
    scenes = script.get("scenes") or []
    print(f"[make] script = {sp.name}  scenes={len(scenes)}")

    # 3) 슬라이드 (모션 on → 카운트다운 클립 포함)
    print("[make] 슬라이드 렌더 …")
    res = generate_bundle_slides(root, only=only, motion=True,
                                 on_progress=lambda ev: _slide_log(ev))
    print(f"[make] slides: 이미지 {len(res['images'])} · 클립 {len(res['clips'])}"
          f"{' (모션)' if res['video_used'] else ' (정적)'}")
    if res["errors"]:
        for e in res["errors"]:
            print(f"[warn] {e}")

    # 4) 음성/자막 (Supertonic3, 발음사전 기반 — LLM 없음)
    if do_audio:
        print("[make] 음성/자막 생성 (Supertonic3) …")
        from app.synth import synthesize   # 늦은 import (env 설정 후)
        voice = script.get("voice")
        speed = script.get("speed")
        asyncio.run(synthesize(root, only=only, voice_override=voice, speed=speed,
                               on_progress=_synth_log))
        print("[make] 음성/자막 완료")
    else:
        print("[make] --no-audio: 음성 생략")

    # --only 는 특정 씬의 슬라이드/음성만 재생성하는 용도. mp4maker 는 번들의 모든
    # 씬 자산이 있어야 하므로 여기서 합성은 건너뛴다(전체 렌더 시 자동 합성).
    if only:
        print("[make] --only: 슬라이드/음성만 재생성함. 전체 합성은 --only 없이 다시 실행하세요.")
        print(f"[done] (부분 재생성) {root}")
        return root / "draft" / f"ch{chapter:02d}_final.mp4"

    # 5) MP4 합성 (레슨: Ken Burns off, 자막 하드번인 없음)
    print("[make] MP4 합성 (mp4maker) …")
    args = [sys.executable, "-m", "mp4maker", str(root),
            "--kenburns", "off", "--no-subs", "--no-soft-sub"]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    rc = subprocess.run(args, cwd=str(ROOT), env=env).returncode
    if rc != 0:
        raise SystemExit(f"[error] mp4maker 실패 (종료코드 {rc})")

    final_mp4 = root / "draft" / f"ch{chapter:02d}_final.mp4"
    print(f"[done] {final_mp4}")

    # 완성 영상(+자막)을 파이프라인 05 스테이지 폴더로 복사(깔끔한 이름). 중간파일은 munje 에 유지.
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        name = _out_name(lesson_path)
        dest = out_dir / f"{name}.mp4"
        shutil.copy2(final_mp4, dest)
        srt = root / "draft" / f"ch{chapter:02d}.srt"
        if srt.exists():
            shutil.copy2(srt, out_dir / f"{name}.srt")
        print(f"[out] {dest}")
        return dest
    return final_mp4


def _slide_log(ev: dict) -> None:
    if ev.get("type") == "log":
        print("  " + ev.get("line", ""))


def _synth_log(completed: int, total: int, scene: int | None) -> None:
    if scene:
        print(f"  음성 씬 {scene}  ({completed}/{total})")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    p = argparse.ArgumentParser(prog="make_video.py",
                                description="lesson JSON → MP4 (헤드리스, 웹 UI 없이)")
    p.add_argument("--lesson", required=True, help="lesson JSON 경로 (예: 04\\lesson_m01.json)")
    p.add_argument("--chapter", type=int, required=True, help="챕터 번호(번들 chNN)")
    p.add_argument("--only", default="", help="특정 씬의 슬라이드/음성만 재생성 (mp4 합성은 건너뜀)")
    p.add_argument("--max-problems", type=int, default=0,
                   help="앞 N문제까지만 완전 렌더(빠른 테스트용, mp4 생성). 0=전체")
    p.add_argument("--assets-src", default="", help="도식 SVG 소스 폴더(기본: 형제 02/assets 자동 탐색)")
    p.add_argument("--out-dir", default="", help="완성 영상 복사 위치(기본: 형제 05 폴더). 'none'=복사 안 함")
    p.add_argument("--no-audio", action="store_true", help="음성 생략(슬라이드/합성만)")
    args = p.parse_args(argv)

    lesson_path = Path(args.lesson).resolve()
    if not lesson_path.is_file():
        raise SystemExit(f"[error] lesson 파일 없음: {lesson_path}")

    if args.assets_src.strip():
        assets_srcs = [Path(args.assets_src)]
    else:
        assets_srcs = _default_assets_srcs(lesson_path)

    od = args.out_dir.strip()
    if od.lower() == "none":
        out_dir = None
    elif od:
        out_dir = Path(od)
    else:
        out_dir = _out5_dir(lesson_path)   # 기본: 04 의 형제 05 폴더

    build(lesson_path, args.chapter, _parse_only(args.only), assets_srcs,
          not args.no_audio, max_problems=args.max_problems, out_dir=out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
