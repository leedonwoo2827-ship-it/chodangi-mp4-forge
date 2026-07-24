"""mediaforge 파이프라인 API (/api/mf/*).

번들 단위로: 대본 확인 → 이미지 가져오기 → 음성/자막 → MP4 합성, 그리고
⚡ 한 번에. 무거운 작업(음성/렌더)은 백그라운드 작업으로 돌리고 폴링한다.
"""
from __future__ import annotations

import asyncio
import json
import mimetypes
import os
import shutil
import subprocess
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ingest.import_images import import_from_downloads

from services import pronounce
from services import script_gen
from services import workbook
from services.llm import backend as llm_backend
from services.llm import errors as llm_errors
from slides.render import generate_bundle_slides

from . import bundles
from .jobs import Job, get_registry
from .render import probe as mp4_probe
from .render import render as mp4_render
from .synth import save_scene_cues, synthesize, write_silence
from .synth import synth_scene_text as synthesize_scene_text

router = APIRouter()

_VALID_KINDS = ("images", "audio", "subtitles", "draft", "script")


# ----------------------------- 요청 모델 -----------------------------
class CreateBundleReq(BaseModel):
    name: str


class ImportReq(BaseModel):
    prefer: str = "latest"
    downloads: str | None = None
    move: bool = False


class ScriptGenReq(BaseModel):
    topic: str = ""
    context: str = ""
    minutes: int = 15
    title: str = ""
    target_audience: str = ""
    objective: str = ""
    series: str = ""
    target_chars: int = 0
    images: int = 0
    model: str | None = None


class SaveScriptReq(BaseModel):
    script_json: str          # 대본 JSON 텍스트(드롭인/편집본)


class SaveLessonReq(BaseModel):
    lesson_json: str          # 문제집/강의(lesson) JSON 텍스트


class SlideReq(BaseModel):
    only: list[int] | None = None
    motion: bool = True


class LLMProviderReq(BaseModel):
    provider: str


class LLMLoginReq(BaseModel):
    provider: str | None = None


class SynthReq(BaseModel):
    only: list[int] | None = None
    voice_override: str | None = None
    speed: float | None = None


class RenderReq(BaseModel):
    only: list[int] | None = None
    dry_run: bool = False
    keep_work: bool = False


# ----------------------------- 번들 -----------------------------
@router.get("/bundles")
async def get_bundles() -> dict:
    return {"bundles": bundles.list_bundles()}


@router.post("/bundles")
async def post_bundle(req: CreateBundleReq) -> dict:
    root = bundles.create_bundle(req.name.strip())
    return {"bundle": root.name, "path": str(root)}


@router.get("/bundles/{name}/status")
async def get_status(name: str) -> dict:
    return bundles.bundle_status(name)


@router.get("/bundles/{name}/script")
async def get_script(name: str) -> dict:
    root = bundles.bundle_path(name)
    sp = bundles.find_script(root)
    if not sp:
        raise HTTPException(404, f"{name}/script/*_script.json 없음")
    try:
        data = json.loads(sp.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(422, f"대본 JSON 파싱 실패: {exc}") from exc
    return {"file": sp.name, "data": data}


# ----------------------------- 대본(JSON) 생성/저장 -----------------------------
def _chapter_of(name: str) -> int:
    import re
    m = re.search(r"(\d{1,3})", name.replace("_bundle", ""))
    return int(m.group(1)) if m else 1


def _write_script(name: str, doc_or_text) -> Path:
    """대본 JSON 을 번들 script/chNN_script.json 으로 저장. dict/텍스트 모두 허용."""
    root = bundles.bundle_path(name)
    (root / "script").mkdir(parents=True, exist_ok=True)
    chap = _chapter_of(name)
    if isinstance(doc_or_text, (dict, list)):
        text = json.dumps(doc_or_text, ensure_ascii=False, indent=2)
    else:
        text = str(doc_or_text)
    out = root / "script" / f"ch{chap:02d}_script.json"
    out.write_text(text, encoding="utf-8")
    return out


def _is_lesson_bundle(name: str) -> bool:
    """대본이 문제집/강의(lesson)인지 판정 — kind=='lesson' 또는 씬에 slide 존재."""
    sp = bundles.find_script(bundles.bundle_path(name))
    if not sp:
        return False
    try:
        data = json.loads(sp.read_text(encoding="utf-8"))
    except Exception:
        return False
    if str(data.get("kind")) == "lesson":
        return True
    return any(sc.get("slide") for sc in (data.get("scenes") or []))


def _lesson_voice_speed(name: str) -> tuple[str | None, float | None]:
    """레슨 번들의 기본 음성/속도(script 최상위 voice/speed). 아니면 (None, None)."""
    sp = bundles.find_script(bundles.bundle_path(name))
    if not sp:
        return None, None
    try:
        data = json.loads(sp.read_text(encoding="utf-8"))
    except Exception:
        return None, None
    if str(data.get("kind")) != "lesson":
        return None, None
    return data.get("voice"), data.get("speed")


def _lesson_ai_reading(name: str) -> bool:
    """레슨의 ai_reading 플래그(기본 True). ⚡에서 자동 AI 발음 적용 여부."""
    sp = bundles.find_script(bundles.bundle_path(name))
    if not sp:
        return False
    try:
        data = json.loads(sp.read_text(encoding="utf-8"))
    except Exception:
        return False
    return str(data.get("kind")) == "lesson" and bool(data.get("ai_reading", True))


@router.get("/llm/status")
async def llm_status() -> dict:
    """codex/agy 설치·로그인·이메일 + 현재 활성 공급자."""
    return await asyncio.to_thread(llm_backend.status_all)


@router.post("/llm/provider")
async def llm_set_provider(req: LLMProviderReq) -> dict:
    if not llm_backend.set_provider(req.provider):
        raise HTTPException(400, f"알 수 없는 공급자: {req.provider} (codex|agy)")
    return await asyncio.to_thread(llm_backend.status_all)


@router.post("/llm/login")
async def llm_login(req: LLMLoginReq) -> dict:
    """공급자 로그인 명령(codex login / agy)을 새 콘솔에서 실행 → 브라우저 OAuth."""
    import subprocess
    import sys
    cmd = llm_backend.login_cmd(req.provider)
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(cmd, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        else:
            subprocess.Popen(cmd)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"로그인 명령 실행 실패: {exc}") from exc
    return {"launched": cmd}


async def _job_script(job: Job, name: str, req: ScriptGenReq) -> None:
    reg = get_registry()
    try:
        job.status = "running"
        job.stage = "대본(JSON) 생성 준비 중…"

        def cb(msg: str):
            job.stage = msg
            job.add_log(msg)

        res = await asyncio.to_thread(
            script_gen.generate_script,
            chapter=_chapter_of(name), title=req.title, minutes=req.minutes,
            topic=req.topic, context=req.context, target_audience=req.target_audience,
            objective=req.objective, series=req.series,
            target_chars=req.target_chars, images=req.images, model=req.model,
            on_progress=cb)
        if not res.get("ok"):
            reg.finish(job, status="error",
                       error=res.get("warning", "대본 생성 실패"), result=res)
            return
        _write_script(name, res["doc"])
        res["status"] = bundles.bundle_status(name)
        reg.finish(job, status="done", result=res)
    except llm_errors.LLMNotInstalled as exc:
        reg.finish(job, status="error", error=f"[미설치] {exc}")
    except llm_errors.LLMNotAuthenticated as exc:
        reg.finish(job, status="error", error=f"[미로그인] {exc}")
    except llm_errors.LLMError as exc:
        reg.finish(job, status="error", error=str(exc))
    except Exception as exc:  # noqa: BLE001
        reg.finish(job, status="error", error=str(exc))


@router.post("/extract_text")
async def extract_text_endpoint(files: list[UploadFile] = File(...)) -> dict:
    """근거자료(PDF/txt/md) 업로드 → 평문 텍스트 추출. 대본 생성 입력창에 채운다.

    여러 파일이면 이어붙인다(파일명 헤더 포함)."""
    from services import extract
    parts: list[str] = []
    total = 0
    for up in (files or []):
        data = await up.read()
        if not data:
            continue
        try:
            txt = await asyncio.to_thread(extract.extract_text, data, up.filename or "src")
        except ValueError as exc:
            raise HTTPException(415, str(exc)) from exc
        parts.append(f"## {up.filename}\n{txt}" if len(files) > 1 else txt)
        total += len(txt)
    if not parts:
        raise HTTPException(400, "추출할 내용이 없습니다.")
    return {"text": "\n\n".join(parts), "chars": total, "files": len(parts)}


@router.post("/bundles/{name}/generate_script")
async def post_generate_script(name: str, req: ScriptGenReq) -> dict:
    """LLM(codex/agy)으로 대본 JSON 생성 후 번들 script/ 에 저장 (백그라운드 작업)."""
    if not bundles.bundle_path(name).is_dir():
        raise HTTPException(404, f"번들 없음: {name}")
    job = get_registry().create(kind="script", bundle=name)
    _spawn(_job_script(job, name, req))
    return {"job_id": job.job_id}


class YoutubeReq(BaseModel):
    model: str | None = None


async def _job_youtube(job: Job, name: str, req: YoutubeReq) -> None:
    reg = get_registry()
    try:
        job.status = "running"
        job.stage = "유튜브 글 생성 준비 중…"

        def cb(msg: str):
            job.stage = msg
            job.add_log(msg)

        res = await asyncio.to_thread(
            script_gen.generate_youtube_meta,
            bundles.bundle_path(name), model=req.model, on_progress=cb)
        # draft/chNN_youtube.txt 로 저장
        root = bundles.bundle_path(name)
        (root / "draft").mkdir(parents=True, exist_ok=True)
        out = root / "draft" / f"ch{_chapter_of(name):02d}_youtube.txt"
        out.write_text(res.get("text", ""), encoding="utf-8")
        res["saved"] = out.name
        reg.finish(job, status="done", result=res)
    except llm_errors.LLMNotInstalled as exc:
        reg.finish(job, status="error", error=f"[미설치] {exc}")
    except llm_errors.LLMNotAuthenticated as exc:
        reg.finish(job, status="error", error=f"[미로그인] {exc}")
    except (llm_errors.LLMError, FileNotFoundError, ValueError) as exc:
        reg.finish(job, status="error", error=str(exc))
    except Exception as exc:  # noqa: BLE001
        reg.finish(job, status="error", error=str(exc))


@router.post("/bundles/{name}/youtube_meta")
async def post_youtube_meta(name: str, req: YoutubeReq) -> dict:
    """완성 영상용 유튜브 업로드 글(제목/설명/해시태그/태그) 생성 (백그라운드 작업)."""
    if not bundles.bundle_path(name).is_dir():
        raise HTTPException(404, f"번들 없음: {name}")
    job = get_registry().create(kind="youtube", bundle=name)
    _spawn(_job_youtube(job, name, req))
    return {"job_id": job.job_id}


@router.post("/bundles/{name}/save_script")
async def post_save_script(name: str, req: SaveScriptReq) -> dict:
    """편집/드롭인한 대본 JSON 텍스트를 번들 script/ 에 저장(파싱 검증 포함)."""
    if not bundles.bundle_path(name).is_dir():
        raise HTTPException(404, f"번들 없음: {name}")
    doc = script_gen.parse_script_doc(req.script_json)
    if doc is None:
        raise HTTPException(422, "유효한 대본 JSON 이 아닙니다(scenes[] 필요).")
    out = _write_script(name, doc)
    return {"saved": out.name, "scene_count": len(doc.get("scenes") or []),
            "status": bundles.bundle_status(name)}


@router.post("/bundles/{name}/save_lesson")
async def post_save_lesson(name: str, req: SaveLessonReq) -> dict:
    """문제집/강의(lesson) JSON 을 대본(scenes)으로 컴파일해 script/ 에 저장."""
    if not bundles.bundle_path(name).is_dir():
        raise HTTPException(404, f"번들 없음: {name}")
    doc = workbook.parse_lesson_doc(req.lesson_json)
    if doc is None:
        raise HTTPException(422, "유효한 레슨 JSON 이 아닙니다(blocks[] 또는 problems[] 필요).")
    script = workbook.lesson_to_script(doc, chapter=_chapter_of(name))
    _write_script(name, script)
    return {
        "saved": f"ch{_chapter_of(name):02d}_script.json",
        "scene_count": len(script.get("scenes") or []),
        "block_count": workbook.block_count(doc),
        "problem_count": workbook.problem_count(doc),
        "warnings": workbook.validate_lesson(doc),
        "status": bundles.bundle_status(name),
    }


# ----------------------------- 이미지 가져오기 -----------------------------
@router.post("/bundles/{name}/import_images")
async def import_images(name: str, req: ImportReq) -> dict:
    root = bundles.bundle_path(name)
    if not root.is_dir():
        raise HTTPException(404, f"번들 없음: {name}")
    try:
        rows = import_from_downloads(root, downloads=req.downloads,
                                     prefer=req.prefer, move=req.move)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"imported": rows, "status": bundles.bundle_status(name)}


# ----------------------------- 슬라이드 생성 -----------------------------
async def _job_slides(job: Job, name: str, req: SlideReq) -> None:
    reg = get_registry()
    try:
        job.status = "running"
        job.stage = "슬라이드 생성"
        root = bundles.bundle_path(name)

        def cb(ev: dict):
            t = ev.get("type")
            if t == "progress":
                job.completed, job.total = ev.get("completed", 0), ev.get("total", 0)
                sc = ev.get("scene")
                job.stage = f"슬라이드 생성 (씬 {sc})" if sc else "슬라이드 생성"
            elif t == "log":
                job.add_log(ev.get("line", ""))

        res = await asyncio.to_thread(
            generate_bundle_slides, root, only=req.only,
            motion=req.motion, on_progress=cb)
        res["status"] = bundles.bundle_status(name)
        reg.finish(job, status="done", result=res)
    except (FileNotFoundError, ValueError) as exc:
        reg.finish(job, status="error", error=str(exc))
    except Exception as exc:  # noqa: BLE001
        reg.finish(job, status="error", error=str(exc))


# ----------------------------- 작업(음성/렌더/한번에) -----------------------------
def _spawn(coro) -> None:
    asyncio.create_task(coro)


async def _job_synth(job: Job, name: str, req: SynthReq) -> None:
    reg = get_registry()
    try:
        job.status = "running"
        job.stage = "음성/자막 생성"
        root = bundles.bundle_path(name)

        def cb(completed: int, total: int, scene: int | None):
            job.completed, job.total = completed, total
            job.stage = f"음성/자막 생성 (씬 {scene})" if scene else "음성/자막 생성"
            job.add_log(f"씬 {scene}: {completed}/{total}")

        lv, lspeed = _lesson_voice_speed(name)
        result = await synthesize(
            root, only=req.only,
            voice_override=req.voice_override or lv,
            speed=req.speed if req.speed is not None else lspeed,
            on_progress=cb,
        )
        reg.finish(job, status="done", result=result)
    except Exception as exc:  # noqa: BLE001
        reg.finish(job, status="error", error=str(exc))


async def _job_render(job: Job, name: str, req: RenderReq) -> None:
    reg = get_registry()
    try:
        job.status = "running"
        job.stage = "MP4 합성"
        root = bundles.bundle_path(name)

        def on_event(ev: dict):
            t = ev.get("type")
            if t == "progress":
                job.completed, job.total = ev["completed"], ev["total"]
                job.stage = f"MP4 합성 (씬 {ev['scene']})"
            elif t == "log":
                job.add_log(ev["line"])

        extra = (["--kenburns", "off", "--no-subs", "--no-soft-sub"]
                 if _is_lesson_bundle(name) else None)
        res = await mp4_render(root, only=req.only, dry_run=req.dry_run,
                               keep_work=req.keep_work, extra_args=extra, on_event=on_event)
        if res["ok"]:
            reg.finish(job, status="done", result=res)
        else:
            reg.finish(job, status="error",
                       error=f"mp4maker 종료코드 {res['returncode']}", result=res)
    except Exception as exc:  # noqa: BLE001
        reg.finish(job, status="error", error=str(exc))


async def _job_oneclick(job: Job, name: str) -> None:
    """⚡ 슬라이드 → 음성/자막 → MP4. 누락/실패 시 그 단계에서 멈춤."""
    reg = get_registry()
    try:
        job.status = "running"
        root = bundles.bundle_path(name)

        st = bundles.bundle_status(name)
        if not st.get("has_script"):
            reg.finish(job, status="error", error="대본(script/*_script.json)이 없습니다.")
            return

        is_lesson = _is_lesson_bundle(name)

        # 1) 슬라이드 생성 — 이미지 없는 씬만 (이미 있으면 재사용)
        need = st.get("missing_images") or []
        if need:
            job.stage = "슬라이드 생성"

            def gcb(ev: dict):
                t = ev.get("type")
                if t == "progress":
                    job.completed, job.total = ev.get("completed", 0), ev.get("total", 0)
                    sc = ev.get("scene")
                    job.stage = f"슬라이드 생성 (씬 {sc})" if sc else "슬라이드 생성"
                elif t == "log":
                    job.add_log(ev.get("line", ""))

            gres = await asyncio.to_thread(generate_bundle_slides, root, only=need, on_progress=gcb)
            job.add_log(f"슬라이드 {len(gres['images'])}개 · 클립 {len(gres['clips'])}개"
                        f"{' (모션)' if gres['video_used'] else ' (정적)'}")
        else:
            job.add_log("슬라이드 이미 존재 — 생성 건너뜀")

        st = bundles.bundle_status(name)
        if st["missing_images"]:
            miss = ", ".join(f"씬{n}" for n in st["missing_images"])
            reg.finish(job, status="error",
                       error=f"{miss} 슬라이드 없음 — 슬라이드 렌더 로그를 확인하세요.")
            return

        # 2) 음성/자막 (오디오 누락 씬이 있을 때만)
        #    발음사전 기반 순수 Supertonic TTS — LLM(codex/agy) 불필요.
        if st["missing_audio"]:
            job.stage = "음성/자막 생성"

            def cb(completed, total, scene):
                job.completed, job.total = completed, total
                job.stage = f"음성/자막 생성 (씬 {scene})" if scene else "음성/자막 생성"

            lv, lspeed = _lesson_voice_speed(name)
            await synthesize(root, voice_override=lv, speed=lspeed, on_progress=cb)
            job.add_log("음성/자막 생성 완료")
        else:
            job.add_log("음성/자막 이미 존재 — 건너뜀")

        # 3) MP4 합성
        job.stage = "MP4 합성"

        def on_event(ev):
            if ev.get("type") == "progress":
                job.completed, job.total = ev["completed"], ev["total"]
                job.stage = f"MP4 합성 (씬 {ev['scene']})"
            elif ev.get("type") == "log":
                job.add_log(ev["line"])

        extra = (["--kenburns", "off", "--no-subs", "--no-soft-sub"]
                 if is_lesson else None)
        res = await mp4_render(root, extra_args=extra, on_event=on_event)
        if not res["ok"]:
            reg.finish(job, status="error",
                       error=f"MP4 합성 실패 (종료코드 {res['returncode']})", result=res)
            return
        reg.finish(job, status="done",
                   result={"final_mp4": res["final_mp4"], "outputs": res["outputs"],
                           "status": bundles.bundle_status(name)})
    except Exception as exc:  # noqa: BLE001
        reg.finish(job, status="error", error=str(exc))


@router.post("/bundles/{name}/generate_slides")
async def post_generate_slides(name: str, req: SlideReq) -> dict:
    """문제집/강의 슬라이드(포스터 PNG + 모션 클립) 생성 (백그라운드 작업)."""
    if not bundles.bundle_path(name).is_dir():
        raise HTTPException(404, f"번들 없음: {name}")
    job = get_registry().create(kind="slides", bundle=name)
    _spawn(_job_slides(job, name, req))
    return {"job_id": job.job_id}


@router.post("/bundles/{name}/synth")
async def post_synth(name: str, req: SynthReq) -> dict:
    job = get_registry().create(kind="synth", bundle=name)
    _spawn(_job_synth(job, name, req))
    return {"job_id": job.job_id}


@router.post("/bundles/{name}/render")
async def post_render(name: str, req: RenderReq) -> dict:
    job = get_registry().create(kind="render", bundle=name)
    _spawn(_job_render(job, name, req))
    return {"job_id": job.job_id}


@router.post("/bundles/{name}/oneclick")
async def post_oneclick(name: str) -> dict:
    job = get_registry().create(kind="oneclick", bundle=name)
    _spawn(_job_oneclick(job, name))
    return {"job_id": job.job_id}


class SceneSynthReq(BaseModel):
    scene: int
    text: str
    srt_text: str | None = None
    voice: str | None = None
    speed: float | None = None
    reset_subtitle: bool = False   # True면 자막을 srt_text로 새로, False면 편집본 유지+재타이밍


class SceneSrtReq(BaseModel):
    scene: int
    cues: list[dict]


@router.post("/bundles/{name}/scene_synth")
async def scene_synth(name: str, req: SceneSynthReq) -> dict:
    """한 씬만 (편집한 텍스트로) 음성+자막 재생성 — 번들에 직접 기록."""
    try:
        return await synthesize_scene_text(
            bundles.bundle_path(name), req.scene, req.text,
            srt_text=req.srt_text, voice=req.voice, speed=req.speed,
            reset_subtitle=req.reset_subtitle,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/bundles/{name}/scene_srt")
async def scene_srt(name: str, req: SceneSrtReq) -> dict:
    """편집한 자막 큐(시간/텍스트) 저장 + 통합 SRT 갱신."""
    try:
        return save_scene_cues(bundles.bundle_path(name), req.scene, req.cues)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


class PronounceReq(BaseModel):
    text: str
    model: str | None = None


@router.post("/pronounce_ai")
async def pronounce_ai_endpoint(req: PronounceReq) -> dict:
    """낭독 텍스트를 AI로 '소리 나는 대로 한글' 한 줄로 변환(발음란 자동 채우기)."""
    txt = await asyncio.to_thread(pronounce.to_reading, req.text, req.model)
    return {"text": txt}


class SynthAiReq(BaseModel):
    only: list[int] | None = None
    model: str | None = None


async def _run_ai_synth(root, name: str, model: str | None, job: Job,
                        only: list[int] | None = None) -> int:
    """씬마다 낭독을 AI 발음(한글 읽기)으로 바꿔 음성 생성. 무음 씬은 silence. 자막은 원문 유지."""
    sp = bundles.find_script(root)
    if not sp:
        raise ValueError("대본이 없습니다.")
    data = json.loads(sp.read_text(encoding="utf-8"))
    scenes = data.get("scenes") or []
    lv, lspeed = _lesson_voice_speed(name)
    want = set(only) if only else None
    targets = [s for s in scenes if want is None or int(s.get("scene") or 0) in want]
    total = len(targets)
    for i, sc in enumerate(targets):
        idx = int(sc.get("scene") or (i + 1))
        job.completed, job.total = i, total
        if sc.get("silent"):
            await write_silence(root, idx, float(sc.get("narration_seconds") or 5))
            continue
        orig = (sc.get("narration_text") or "").strip()
        if not orig:
            continue
        job.stage = f"AI 발음+음성 (씬 {idx})"
        reading = await asyncio.to_thread(pronounce.to_reading, orig, model)
        job.add_log(f"씬 {idx}: {reading[:40]}")
        await synthesize_scene_text(
            root, idx, reading, srt_text=orig, voice=lv, speed=lspeed, reset_subtitle=True)
    job.completed = total
    return total


async def _job_synth_ai(job: Job, name: str, req: SynthAiReq) -> None:
    reg = get_registry()
    try:
        job.status = "running"
        job.stage = "AI 발음 변환 + 음성 생성"
        root = bundles.bundle_path(name)
        n = await _run_ai_synth(root, name, req.model, job, only=req.only)
        reg.finish(job, status="done", result={"scenes": n, "status": bundles.bundle_status(name)})
    except llm_errors.LLMError as exc:
        reg.finish(job, status="error", error=str(exc))
    except (FileNotFoundError, ValueError) as exc:
        reg.finish(job, status="error", error=str(exc))
    except Exception as exc:  # noqa: BLE001
        reg.finish(job, status="error", error=str(exc))


@router.post("/bundles/{name}/synth_ai")
async def post_synth_ai(name: str, req: SynthAiReq) -> dict:
    """AI 발음 변환 후 전체(또는 일부) 씬 음성 생성 (백그라운드 작업)."""
    if not bundles.bundle_path(name).is_dir():
        raise HTTPException(404, f"번들 없음: {name}")
    job = get_registry().create(kind="synth_ai", bundle=name)
    _spawn(_job_synth_ai(job, name, req))
    return {"job_id": job.job_id}


@router.post("/bundles/{name}/to_pronunciation")
async def to_pron(payload: dict) -> dict:
    """발음 사전 + 약어/연도/단위 변환 미리보기 (한국어 발음 전환 버튼용)."""
    from voicewright import settings as settings_module
    from voicewright.pronunciation import load_pronunciation_map
    text = str(payload.get("text", ""))
    if not text.strip():
        return {"text": ""}
    pmap = load_pronunciation_map(settings_module.load().pronunciation_map_path)
    return {"text": pmap.apply(text, spell_unknown_acronyms=True, convert_years=True)}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = get_registry().get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job.to_dict()


# ----------------------------- 파일 서빙 (썸네일/미리듣기/다운로드) -----------------------------
@router.get("/file/{name}/{kind}/{filename}")
async def serve_file(name: str, kind: str, filename: str) -> FileResponse:
    if kind not in _VALID_KINDS:
        raise HTTPException(404, "unknown kind")
    if "/" in filename or "\\" in filename or filename.startswith(".."):
        raise HTTPException(400, "invalid filename")
    p = bundles.bundle_path(name) / kind / filename
    if not p.is_file():
        raise HTTPException(404, "file not found")
    media, _ = mimetypes.guess_type(str(p))
    return FileResponse(str(p), media_type=media or "application/octet-stream", filename=filename)


@router.post("/bundles/{name}/clear_draft")
async def clear_draft(name: str) -> dict:
    """기존 풀렌더 결과(draft/ 안의 mp4·srt·mlt·report·_work)를 비운다."""
    draft = bundles.bundle_path(name) / "draft"
    removed: list[str] = []
    if draft.is_dir():
        for p in sorted(draft.iterdir()):
            try:
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                    removed.append(p.name + "/")
                else:
                    p.unlink()
                    removed.append(p.name)
            except OSError:
                pass
    return {"removed": removed, "status": bundles.bundle_status(name)}


class OpenFolderReq(BaseModel):
    kind: str = "root"     # root | script | images | audio | subtitles | draft | clips


@router.post("/bundles/{name}/open_folder")
async def open_folder(name: str, req: OpenFolderReq) -> dict:
    """번들의 하위 폴더(images/script 등)를 파일 탐색기로 연다 (로컬 앱)."""
    import sys
    root = bundles.bundle_path(name)
    if not root.is_dir():
        raise HTTPException(404, f"번들 없음: {name}")
    allowed = {"root", "script", "images", "audio", "subtitles", "draft", "clips"}
    kind = (req.kind or "root").strip()
    if kind not in allowed:
        raise HTTPException(400, f"알 수 없는 폴더: {kind}")
    target = root if kind == "root" else root / kind
    target.mkdir(parents=True, exist_ok=True)
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(target))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"폴더 열기 실패: {exc}") from exc
    return {"opened": str(target)}


@router.post("/bundles/{name}/open_draft")
async def open_draft(name: str) -> dict:
    """결과(draft) 폴더를 파일 탐색기로 연다 (로컬 앱이라 서버=내 PC)."""
    draft = bundles.bundle_path(name) / "draft"
    draft.mkdir(parents=True, exist_ok=True)
    import sys
    try:
        if sys.platform.startswith("win"):
            import os
            os.startfile(str(draft))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(draft)])
        else:
            subprocess.Popen(["xdg-open", str(draft)])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"폴더 열기 실패: {exc}") from exc
    return {"opened": str(draft)}


@router.get("/probe")
async def probe() -> dict:
    return await mp4_probe()
