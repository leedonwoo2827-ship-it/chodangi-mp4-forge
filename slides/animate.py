"""요소 순차 등장 모션 클립 합성 — Pillow 프레임 + ffmpeg overlay/alpha 페이드.

base(항상 보임) 위에 각 element 레이어를 지정 시각(appear_time)에 알파 페이드인으로
올려 하나의 무음 mp4 클립을 만든다. render_scene 이 이 클립을 -stream_loop -1 로
받아 나레이션 길이에 맞춰 트림하므로, 클립 길이는 나레이션보다 넉넉히 잡는다.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

from mp4maker.ffmpeg_runner import run_ffmpeg

FADE = 0.35


def render_clip(base: Image.Image, elements, out_path: Path, duration: float,
                fps: int = 30, log_path: Path | None = None) -> Path:
    """base + elements → out_path(mp4). elements=[(RGBA layer, appear_time), ...]."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.parent / f".slidetmp_{out_path.stem}"
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        base_png = tmp / "base.png"
        base.convert("RGB").save(base_png)

        inputs = ["-loop", "1", "-framerate", str(fps), "-t", f"{duration:.2f}", "-i", str(base_png)]
        filters = [f"[0:v]fps={fps},format=rgba[bg]"]
        prev = "bg"
        for i, (layer, t) in enumerate(elements):
            p = tmp / f"e{i}.png"
            layer.save(p)
            inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{duration:.2f}", "-i", str(p)]
            st = max(0.0, min(float(t), max(0.0, duration - FADE - 0.05)))
            filters.append(f"[{i + 1}:v]format=rgba,fade=t=in:st={st:.2f}:d={FADE}:alpha=1[e{i}]")
            filters.append(f"[{prev}][e{i}]overlay=eof_action=pass[o{i}]")
            prev = f"o{i}"
        filters.append(f"[{prev}]fade=t=in:st=0:d=0.4,format=yuv420p[v]")

        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", ";".join(filters),
            "-map", "[v]",
            "-t", f"{duration:.2f}",
            "-r", str(fps),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "veryfast",
            "-crf", "20",
            "-movflags", "+faststart",
            str(out_path),
        ]
        run_ffmpeg(cmd, log_path=log_path)
        return out_path
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def render_countdown_clip(frames_rgb, out_path: Path, fps: int = 30,
                          log_path: Path | None = None) -> Path:
    """RGB 프레임 리스트(각 1초씩)를 카운트다운 클립으로. 5,4,3,2,1 → 5초."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.parent / f".cdtmp_{out_path.stem}"
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        for i, im in enumerate(frames_rgb):
            im.save(tmp / f"f{i:03d}.png")
        cmd = [
            "ffmpeg", "-y",
            "-framerate", "1", "-i", str(tmp / "f%03d.png"),
            "-vf", f"fps={fps},format=yuv420p",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-preset", "veryfast", "-crf", "20",
            "-movflags", "+faststart", str(out_path),
        ]
        run_ffmpeg(cmd, log_path=log_path)
        return out_path
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
