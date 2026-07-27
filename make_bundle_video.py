"""번들 렌더 드라이버 (파이프라인 05) — deck.html 슬라이드 기반 '일반 영상'.

exambook-forge(#2)가 만든 `05/<회차>/` 번들을 입력으로:
  1) source/deck.html 을 headless Chromium 으로 캡처 → images/slide_%02d.png (밝은 슬라이드)
  2) 카운트다운(생각할 시간 54321)·간격 씬은 밝은 Pillow 프레임/클립으로 생성
  3) Supertonic3 로컬 TTS 로 음성/자막 (자막·음성 최종 OK 지점)
  4) mp4maker(ffmpeg) 합성 → draft/<회차>.static.mp4 + <회차>.ko.vtt
  5) review.json / slides.json / <회차>.timing.json 갱신

기존 make_video.py(Pillow, lesson JSON 직접 렌더)는 그대로 두고, 이 드라이버는
deck.html 기반 경로를 추가한다. 렌더 엔진(#3의 slides 캡처·synth·mp4maker)은 재사용.

사용:
  python make_bundle_video.py --book D:/00work/ocr-output-260723 --round m01
  python make_bundle_video.py --book ... --round m01 --no-audio   # 슬라이드만(합성/음성 생략)
  python make_bundle_video.py --book ...                          # 05/ 아래 모든 회차

전제: #2에서 `python scripts/bundle.py --book <book> --round m01` 로 05 번들이 만들어져 있어야 함.
의존성: playwright(+chromium)  ·  기존 requirements-render.txt(onnxruntime/Pillow/pysrt/lxml/…).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("VOICEWRIGHT_VOICE_MAP", str(ROOT / "config" / "voice_map.yaml"))
os.environ.setdefault("VOICEWRIGHT_PRONUNCIATION_MAP", str(ROOT / "config" / "pronunciation_map.yaml"))
os.environ.setdefault("VOICEWRIGHT_ASSETS_DIR", str(ROOT / "assets"))
os.environ.setdefault("VOICEWRIGHT_WORKSPACE", os.environ.get("MF_OUTPUT_DIR") or str(ROOT / "munje"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import bundles                       # noqa: E402
from slides import animate, deck_capture       # noqa: E402

CPS = 6.5
MIN_SECONDS = 4


def _secs(text: str) -> int:
    return max(MIN_SECONDS, round(len((text or "").strip()) / CPS))


def _chapter_of(round_code: str) -> int:
    digits = re.sub(r"\D", "", round_code) or "1"
    return int(digits)


def _build_records(series: dict, cid: str) -> list[dict]:
    """_series 씬 → #3 스크립트 씬 레코드(1-based idx, 파일명, 낭독/무음)."""
    recs: list[dict] = []
    for s in series.get("scenes", []):
        si = int(s.get("scene", len(recs)))
        idx = si + 1
        kind = s.get("kind", "content")
        capture = bool(s.get("capture"))
        narration = (s.get("narration_text") or s.get("narration") or "").strip()
        rec = {
            "si": si, "idx": idx, "kind": kind, "capture": capture,
            "number": s.get("number"), "heading": s.get("heading") or "",
            "image_filename": f"{cid}_{idx:02d}_{kind}.png",
            "video_filename": f"{cid}_{idx:02d}.mp4",
        }
        if kind in ("countdown", "gap"):
            rec["silent"] = True
            rec["seconds"] = int(s.get("countdown_seconds") or s.get("gap_seconds") or
                                 (5 if kind == "countdown" else 2))
            rec["narration_text"] = ""
        else:
            rec["narration_text"] = narration or rec["heading"] or "…"
            rec["narration_seconds"] = _secs(rec["narration_text"])
        recs.append(rec)
    return recs


def _scratch_script(series: dict, recs: list[dict], chap: int) -> dict:
    scenes = []
    for r in recs:
        sc = {
            "scene": r["idx"],
            "title": r["heading"] or f"씬 {r['idx']}",
            "image_filename": r["image_filename"],
            "video_filename": r["video_filename"],
            "narration_text": r["narration_text"],
        }
        if r.get("silent"):
            sc["silent"] = True
            sc["narration_seconds"] = int(r["seconds"])
        else:
            sc["narration_seconds"] = int(r["narration_seconds"])
        scenes.append(sc)
    return {
        "version": "1.0", "kind": "lesson", "chapter": chap,
        "title": series.get("round") or "", "subject": series.get("subject") or "",
        "theme": series.get("theme") or "", "round": series.get("round") or "",
        "voice": series.get("voice") or "F2", "speed": series.get("speed", 1.05),
        "ai_reading": False, "aspect_ratio": "16:9", "scenes": scenes,
    }


def _srt_to_vtt(srt_text: str) -> str:
    body = re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", srt_text)
    return "WEBVTT\n\n" + body.strip() + "\n"


def _parse_srt_cues(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for m in re.finditer(
            r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})",
            path.read_text(encoding="utf-8")):
        g = [int(x) for x in m.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        out.append({"start": round(start, 3), "end": round(end, 3)})
    return out


def _wav_dur(path: Path) -> float:
    try:
        import soundfile as sf
        info = sf.info(str(path))
        return round(info.frames / float(info.samplerate), 3)
    except Exception:
        return 0.0


def build(book: Path, round_code: str, do_audio: bool, keep_scratch: bool) -> Path | None:
    b05 = book / "05" / round_code
    series_path = b05 / "script" / f"{round_code}_script.json"
    deck = b05 / "source" / "deck.html"
    review_path = b05 / "review.json"
    if not series_path.exists() or not deck.exists():
        raise SystemExit(
            f"[error] 05 번들이 없습니다: {b05}\n"
            f"        먼저 #2에서: python scripts/bundle.py --book \"{book}\" --round {round_code}")

    series = json.loads(series_path.read_text(encoding="utf-8"))
    chap = _chapter_of(round_code)
    cid = f"ch{chap:02d}"
    scratch = bundles.create_bundle(cid)
    (scratch / "clips").mkdir(parents=True, exist_ok=True)
    print(f"[make] round={round_code} scratch={scratch}")

    recs = _build_records(series, cid)
    n_cap = sum(1 for r in recs if r["capture"])

    # 1) deck.html 캡처 → 캡처 씬 이미지
    cap_files = [r["image_filename"] for r in recs if r["capture"]]
    saved, deck_slides = deck_capture.capture_deck(deck, scratch / "images", cap_files)
    print(f"[make] deck 캡처: {len(saved)}/{n_cap}  (deck .slide={deck_slides})")
    if deck_slides != n_cap:
        print(f"[warn] deck 슬라이드({deck_slides}) ≠ 캡처 씬({n_cap}) — 슬라이드/씬 1:1 확인 필요")

    # 2) 카운트다운/간격 프레임·클립 (밝게)
    ffmpeg_ok = shutil.which("ffmpeg") is not None
    last_problem_img: dict = {}
    for r in recs:
        if r["capture"] and r["kind"] == "problem":
            last_problem_img[r.get("number")] = scratch / "images" / r["image_filename"]
    for r in recs:
        img_path = scratch / "images" / r["image_filename"]
        if r["kind"] == "countdown":
            base = last_problem_img.get(r.get("number"))
            base = base if (base and base.exists()) else None
            if base is None:
                deck_capture.solid_frame().save(img_path)
                frames = deck_capture.countdown_frames(img_path, r["seconds"])
            else:
                frames = deck_capture.countdown_frames(base, r["seconds"])
            frames[0].save(img_path)
            if ffmpeg_ok:
                try:
                    animate.render_countdown_clip(frames, scratch / "clips" / r["video_filename"])
                except Exception as exc:
                    print(f"[warn] 카운트다운 클립 실패 씬{r['idx']}: {exc}")
        elif r["kind"] == "gap":
            deck_capture.solid_frame().save(img_path)

    # 3) 스크래치 대본 저장
    (scratch / "script").mkdir(parents=True, exist_ok=True)
    (scratch / "script" / f"{cid}_script.json").write_text(
        json.dumps(_scratch_script(series, recs, chap), ensure_ascii=False, indent=2),
        encoding="utf-8")

    if not do_audio:
        print("[make] --no-audio: 음성/합성 생략 (슬라이드만). 05 이미지 복사 후 종료.")
        _copy_images_only(scratch, b05, recs, cid)
        return None

    # 4) 음성/자막 (Supertonic3)
    print("[make] 음성/자막 (Supertonic3) …")
    from app.synth import synthesize   # 늦은 import(env 설정 후, 모델 로드 무거움)
    asyncio.run(synthesize(scratch, voice_override=series.get("voice"),
                           speed=series.get("speed")))

    # 5) mp4maker 합성 (레슨: Ken Burns off, 자막 하드번인 없음)
    print("[make] MP4 합성 (mp4maker) …")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONIOENCODING"] = "utf-8"
    rc = subprocess.run([sys.executable, "-m", "mp4maker", str(scratch),
                         "--kenburns", "off", "--no-subs", "--no-soft-sub"],
                        cwd=str(ROOT), env=env).returncode
    if rc != 0:
        raise SystemExit(f"[error] mp4maker 실패 (종료코드 {rc})")

    # 6) 05 번들로 산출물 이관 + review.json/slides.json/timing.json 갱신
    dest = _finalize_bundle(scratch, b05, recs, cid, round_code, review_path)
    if not keep_scratch:
        shutil.rmtree(scratch, ignore_errors=True)
    print(f"[done] {dest}")
    return dest


def _copy_images_only(scratch: Path, b05: Path, recs: list[dict], cid: str) -> None:
    (b05 / "images").mkdir(parents=True, exist_ok=True)
    for r in recs:
        srcimg = scratch / "images" / r["image_filename"]
        if srcimg.exists():
            shutil.copy2(srcimg, b05 / "images" / f"slide_{r['si']:02d}.png")


def _finalize_bundle(scratch: Path, b05: Path, recs: list[dict], cid: str,
                     round_code: str, review_path: Path) -> Path:
    for sub in ("images", "audio", "subtitles", "draft"):
        (b05 / sub).mkdir(parents=True, exist_ok=True)

    # 이미지·오디오 → pressplay 파일명(0-base)
    durations: dict[int, float] = {}
    cues_map: dict[int, list] = {}
    for r in recs:
        si, idx = r["si"], r["idx"]
        srcimg = scratch / "images" / r["image_filename"]
        if srcimg.exists():
            shutil.copy2(srcimg, b05 / "images" / f"slide_{si:02d}.png")
        srcaud = scratch / "audio" / f"{cid}_{idx:02d}_narration.wav"
        if srcaud.exists():
            shutil.copy2(srcaud, b05 / "audio" / f"scene_{si:02d}.wav")
            durations[si] = _wav_dur(srcaud)
        cues_map[si] = _parse_srt_cues(scratch / "subtitles" / f"{cid}_{idx:02d}_narration.srt")

    # 통합 자막 → subtitles/subtitles.srt + draft/<round>.ko.vtt
    combined = scratch / "subtitles" / f"{cid}.srt"
    if combined.exists():
        srt_text = combined.read_text(encoding="utf-8")
        (b05 / "subtitles" / "subtitles.srt").write_text(srt_text, encoding="utf-8")
        (b05 / "draft" / f"{round_code}.ko.vtt").write_text(_srt_to_vtt(srt_text), encoding="utf-8")

    # 최종 영상 → draft/<round>.static.mp4
    final_src = scratch / "draft" / f"{cid}_final.mp4"
    dest = b05 / "draft" / f"{round_code}.static.mp4"
    if final_src.exists():
        shutil.copy2(final_src, dest)

    # 타이밍 누적
    start = 0.0
    timing = []
    for r in recs:
        si = r["si"]
        d = durations.get(si, 0.0)
        timing.append({"scene": si, "kind": r["kind"], "durSec": d, "startSec": round(start, 3)})
        start += d
    total = round(start, 3)

    # review.json 갱신(있으면 로드, 없으면 최소 생성)
    review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else {"slides": []}
    review["totalSeconds"] = total
    by_index = {sl.get("index"): sl for sl in review.get("slides", [])}
    for t in timing:
        sl = by_index.get(t["scene"])
        if sl is not None:
            sl["durSec"] = t["durSec"]
            sl["startSec"] = t["startSec"]
            sl["cues"] = cues_map.get(t["scene"], [])
    review["staticVideo"] = f"{round_code}.static.mp4" if dest.exists() else None
    review["staticSubtitles"] = f"{round_code}.ko.vtt" if (b05 / "draft" / f"{round_code}.ko.vtt").exists() else None
    review.setdefault("motionVideo", None)
    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")

    # slides.json (캡처 매니페스트) + timing.json
    slides_manifest = {
        "version": "1.0", "round": round_code,
        "slides": [{"index": r["si"], "image": f"slide_{r['si']:02d}.png",
                    "heading": r["heading"], "capture": r["capture"], "kind": r["kind"]}
                   for r in recs],
    }
    (b05 / "source" / "slides.json").write_text(
        json.dumps(slides_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (b05 / "source" / f"{round_code}.timing.json").write_text(
        json.dumps({"round": round_code, "totalSeconds": total, "scenes": timing},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    return dest


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    p = argparse.ArgumentParser(prog="make_bundle_video.py",
                                description="05 번들(deck.html) → 일반영상 static.mp4 + review.json")
    p.add_argument("--book", default="D:/00work/ocr-output-260723", help="책 루트")
    p.add_argument("--round", default="", help="회차코드 (예: m01). 생략 시 05/ 아래 모든 회차")
    p.add_argument("--no-audio", action="store_true", help="음성/합성 생략(슬라이드 캡처만)")
    p.add_argument("--keep-scratch", action="store_true", help="munje/ 스크래치 번들 유지(디버그)")
    args = p.parse_args(argv)

    book = Path(args.book).resolve()
    if args.round:
        rounds = [args.round]
    else:
        d05 = book / "05"
        rounds = sorted(p.name for p in d05.iterdir() if p.is_dir()) if d05.is_dir() else []
    if not rounds:
        raise SystemExit(f"[error] 처리할 회차가 없습니다: {book}/05 (--round 로 지정)")

    for rc in rounds:
        build(book, rc, not args.no_audio, args.keep_scratch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
