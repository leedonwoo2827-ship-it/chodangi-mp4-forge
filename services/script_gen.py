"""대본(JSON) 자동 생성 — 기존 od-flow 의 generate-script-json 과 동일 구조.

활성 LLM 공급자(codex/agy, OAuth·API키 없음)로 책 본문/주제를 근거로 다큐 대본 JSON 을
생성하고, narration 글자수를 목표 범위에 맞추는 보강(expand)/축약(condense) 패스를 돈다.
반환 JSON 은 mp4maker 번들 스키마와 동일하며 씬별 영어 prompt 가 ComfyUI txt2img 입력이 된다.

원본: 260612-od-flow-supoer3-mp4/routes/vodstudio_routes.py::generate_script_json
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional

from .llm import backend
from . import script_prompt

CPS = 6.5


def generate_youtube_meta(
    bundle_dir, *, model: Optional[str] = None,
    on_progress: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """완성(예정) 영상의 대본으로 유튜브 업로드용 글을 LLM 으로 생성. 동기."""
    from pathlib import Path
    bundle = Path(bundle_dir)
    files = sorted((bundle / "script").glob("*_script.json"))
    if not files:
        raise FileNotFoundError("대본 JSON 이 없습니다. 먼저 대본을 만드세요.")
    data = json.loads(files[0].read_text(encoding="utf-8"))
    title = data.get("title") or ""
    scenes = data.get("scenes") or []
    if not scenes:
        raise ValueError("대본에 scenes 가 없습니다.")
    secs = sum(float(s.get("narration_seconds") or 0) for s in scenes)
    parts = []
    for s in scenes:
        t = (s.get("title") or "").strip()
        n = (s.get("narration_text") or "").strip()
        parts.append((f"[{t}] " if t else "") + n)
    body = "\n".join(parts)[:5000]     # 프롬프트 과대 방지

    if on_progress:
        try:
            on_progress(f"유튜브 업로드용 글 생성 중… LLM({backend.get_provider()}) 호출")
        except Exception:
            pass
    text = _llm(script_prompt.youtube_meta_prompt(title, body, round(secs / 60)), model)
    return {"ok": True, "title": title, "text": (text or "").strip()}


def parse_script_doc(text: str) -> Optional[Dict[str, Any]]:
    """코드펜스/앞뒤 잡텍스트를 허용하고 첫 '{' ~ 마지막 '}' 를 파싱. scenes[] 있으면 반환."""
    s = (text or "").strip()
    if not s:
        return None
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        doc = json.loads(s[i:j + 1])
    except Exception:
        return None
    if isinstance(doc, dict) and isinstance(doc.get("scenes"), list) and doc["scenes"]:
        return doc
    return None


def _nchars(doc: Dict[str, Any]) -> int:
    return sum(len((s.get("narration_text") or "")) for s in (doc.get("scenes") or []))


def _llm(prompt: str, model: Optional[str]) -> str:
    """동기 LLM 호출(활성 공급자). LLMError 계열을 그대로 올린다(라우트에서 매핑)."""
    client = backend.active_client()
    mdl = (model or "").strip() or (backend.get_model() or None)
    return client.chat(mdl, [{"role": "user", "content": prompt}], max_tokens=8000).text


def generate_script(
    *,
    chapter: int = 1,
    title: str = "",
    minutes: int = 15,
    topic: str = "",
    context: str = "",
    target_audience: str = "",
    objective: str = "",
    series: str = "",
    target_chars: int = 0,
    images: int = 0,
    model: Optional[str] = None,
    on_progress: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """대본 JSON 을 생성해 dict 로 반환(동기). 라우트에서 asyncio.to_thread 로 감싼다.

    on_progress(msg): 단계별 진행 메시지 콜백(있으면 호출). UI 실시간 표시용.
    Returns: {ok, script_json, doc?, scene_count?, narration_chars?, topups?, est_minutes?, warning?}
    """
    def _p(msg: str) -> None:
        if on_progress:
            try:
                on_progress(msg)
            except Exception:
                pass

    tchars = max(0, int(target_chars or 0))
    # target_chars 가 오면 분량을 역산(6.5자/초·60), 아니면 minutes 사용.
    minutes = max(3, min(45, round(tchars / (CPS * 60)) if tchars else int(minutes or 10)))
    ctx = (context or topic or "").strip()

    prompt = script_prompt.master_script_json_prompt(
        chapter, title, minutes, target_audience, objective,
        context=ctx, series_name=(series or "").strip(),
        target_chars=tchars, images=max(0, int(images or 0)))
    prov = backend.get_provider()
    _p(f"LLM({prov})로 대본 생성 중… 응답 대기 (수십 초~2분 걸릴 수 있음)")
    text = _llm(prompt, model)
    doc = parse_script_doc(text)
    if doc is None:
        return {"ok": False, "script_json": text,
                "warning": "JSON 파싱 실패 — 모델 출력을 확인/수정 후 저장하세요."}
    _p(f"초안 생성됨: {len(doc.get('scenes') or [])}씬 · {_nchars(doc)}자 — 목표 대비 확인")

    # 분량 강제: 목표 범위 [floor, ceiling] 밖이면 expand/condense (최대 3회).
    target_total = tchars if tchars else int(minutes * 60 * CPS)
    floor = round(target_total * 0.95)
    ceiling = round(target_total * 1.15)
    topups = 0
    while target_total and topups < 3:
        n = _nchars(doc)
        if n < floor:
            _p(f"분량 보정 {topups + 1}/3 — 목표 {target_total}자에 미달({n}자), 보강 중…")
            pr = script_prompt.expand_narration_prompt(
                json.dumps(doc, ensure_ascii=False), ctx, target_total, n)
        elif n > ceiling:
            _p(f"분량 보정 {topups + 1}/3 — 목표 {target_total}자 초과({n}자), 축약 중…")
            pr = script_prompt.condense_narration_prompt(
                json.dumps(doc, ensure_ascii=False), target_total, n)
        else:
            break
        topups += 1
        d2 = parse_script_doc(_llm(pr, model))
        if not (d2 and d2.get("scenes")):
            break
        doc = d2

    scenes = doc.get("scenes") or []
    nchars = _nchars(doc)
    return {
        "ok": True,
        "doc": doc,
        "script_json": json.dumps(doc, ensure_ascii=False, indent=2),
        "scene_count": len(scenes),
        "narration_chars": nchars,
        "topups": topups,
        "est_minutes": round(nchars / CPS / 60.0, 1),
    }
