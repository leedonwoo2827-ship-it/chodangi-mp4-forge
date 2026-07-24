"""slides — 문제집/강의 슬라이드 렌더러 (Pillow + ffmpeg 모션 클립).

comfy/generate.py 의 이미지 단계를 대체한다. 대본의 씬별 slide 스펙을 그려
images/ 포스터 PNG(+ clips/ 모션 mp4)를 남긴다.
"""
from __future__ import annotations

from .render import generate_bundle_slides

__all__ = ["generate_bundle_slides"]
