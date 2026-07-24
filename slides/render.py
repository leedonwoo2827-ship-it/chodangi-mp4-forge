"""번들 단위 슬라이드 생성 — comfy/generate.py 의 이미지 단계를 대체.

대본(script/chNN_script.json)의 씬별 slide 스펙을 Pillow 로 그려
    images/chNN_XX_*.png   (포스터/정적 폴백 — 항상)
    clips/chNN_XX.mp4      (요소 순차 등장 모션 — motion=True 이고 ffmpeg 있으면)
둘 다 남긴다. mp4maker 는 클립이 있으면 클립을 우선 쓰고(움직임), 없으면 이미지를
Ken Burns 없이(--kenburns off) 정적 표시한다.

generate_bundle_images 와 동일 시그니처/반환형으로 라우트 배선을 드롭인 교체한다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

from mp4maker.ffmpeg_runner import probe_binary

from . import animate, layout
from .theme import get_palette

ProgressCb = Optional[Callable[[dict], None]]


def _emit(cb: ProgressCb, ev: dict) -> None:
    if cb:
        try:
            cb(ev)
        except Exception:
            pass


def _load(bundle: Path):
    files = sorted((bundle / "script").glob("*_script.json"))
    if not files:
        raise FileNotFoundError(f"대본 JSON 없음: {bundle}/script/*_script.json")
    data = json.loads(files[0].read_text(encoding="utf-8"))
    chap = int(data.get("chapter") or 1)
    return data, chap, f"ch{chap:02d}", data.get("scenes") or []


def generate_bundle_slides(
    bundle_dir: str | Path,
    *,
    only: list[int] | None = None,
    motion: bool = True,
    on_progress: ProgressCb = None,
) -> dict:
    """번들의 모든(또는 only) 씬 슬라이드를 렌더한다.

    Returns: {"images":[...], "clips":[...], "video_used": bool, "errors":[...]}
    """
    bundle = Path(bundle_dir).resolve()
    data, chapter, cid, scenes = _load(bundle)
    pal = get_palette(data.get("theme") or "", data.get("subject") or "", chapter)

    images_dir = bundle / "images"
    clips_dir = bundle / "clips"
    images_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg_ok = probe_binary("ffmpeg") is not None
    use_motion = bool(motion and ffmpeg_ok)
    if use_motion:
        clips_dir.mkdir(parents=True, exist_ok=True)
    if motion and not ffmpeg_ok:
        _emit(on_progress, {"type": "log", "line": "[slides] ffmpeg 없음 → 모션 생략, 정적 이미지만 생성"})

    only_set = set(only) if only else None
    result = {"images": [], "clips": [], "video_used": use_motion, "errors": []}
    total = len(scenes)

    for pos, scene in enumerate(scenes):
        idx = int(scene.get("scene") or scene.get("scene_number") or (pos + 1))
        if only_set is not None and idx not in only_set:
            continue
        _emit(on_progress, {"type": "progress", "completed": pos, "total": total, "scene": idx})
        slide = scene.get("slide")
        if not slide:
            msg = f"씬{idx}: slide 스펙 없음 — 건너뜀"
            result["errors"].append(msg)
            _emit(on_progress, {"type": "log", "line": f"[slides] {msg}"})
            continue
        try:
            img_name = scene.get("image_filename") or f"{cid}_{idx:02d}_slide.png"
            clip_name = scene.get("video_filename") or f"{cid}_{idx:02d}.mp4"
            if slide.get("kind") == "gap":
                # 간격 씬: 정적 포스터만(무음). mp4maker 가 seconds 만큼 이미지 hold.
                layout.build_gap(slide, pal).save(images_dir / img_name)
                result["images"].append(img_name)
                continue
            if slide.get("kind") == "countdown":
                seconds = int(slide.get("seconds") or 5)
                cbase = layout.build_countdown_base(slide, pal)
                layout.draw_countdown_number(cbase, seconds, pal).save(images_dir / img_name)
                result["images"].append(img_name)
                _emit(on_progress, {"type": "log", "line": f"[slides] 씬{idx} 카운트다운 -> {img_name}"})
                if use_motion:
                    frames = [layout.draw_countdown_number(cbase, n, pal)
                              for n in range(seconds, 0, -1)]
                    animate.render_countdown_clip(frames, clips_dir / clip_name)
                    result["clips"].append(clip_name)
                continue
            base, elements = layout.build(slide, pal)
            layout.compose_static(base, elements).save(images_dir / img_name)
            result["images"].append(img_name)
            _emit(on_progress, {"type": "log", "line": f"[slides] 씬{idx} 이미지 -> {img_name}"})
            if use_motion:
                hint = float(scene.get("narration_seconds") or 6)
                dur = round(hint * 1.25) + 5
                animate.render_clip(base, elements, clips_dir / clip_name, dur)
                result["clips"].append(clip_name)
                _emit(on_progress, {"type": "log", "line": f"[slides] 씬{idx} 클립 -> {clip_name}"})
        except Exception as exc:  # noqa: BLE001
            msg = f"씬{idx} 슬라이드 생성 실패: {exc}"
            result["errors"].append(msg)
            _emit(on_progress, {"type": "log", "line": f"[slides] {msg}"})
            continue

    _emit(on_progress, {"type": "progress", "completed": total, "total": total, "scene": None})
    return result
