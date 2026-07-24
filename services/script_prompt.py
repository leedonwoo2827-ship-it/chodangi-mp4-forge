"""대본(JSON) 생성 프롬프트 — 기존 영상 공방과 동일한 구조/스키마.

원본: 260612-od-flow-supoer3-mp4 의 services/vodstudio/prompts.py
(FlowGenie/nano_banana 관련 문구만 ComfyUI 중립으로 조정. 안전 규칙은 그대로 유지.)

이 프롬프트로 만든 JSON 은 mp4maker 번들 스키마와 동일하며, 씬별 영어 "prompt" 가
그대로 ComfyUI txt2img 입력이 된다. 대본 생성은:
  - 이 프롬프트를 아무 LLM(Claude/ChatGPT/Gemini)에 붙여넣어 순수 JSON 을 받거나,
  - 이미 만든 script JSON 을 번들 script/ 에 드롭인
어느 쪽이든 된다. 아래 CLI 로 프롬프트 텍스트를 뽑아 쓸 수 있다:

    python -m services.script_prompt --chapter 90 --minutes 15 > prompt.txt
"""
from __future__ import annotations

CPS = 6.5  # SuperTonic3 TTS 실측(한국어 ~6.5자/초, 기본 보이스 M5).


def master_script_json_prompt(chapter: int, title: str, minutes: int,
                              target_audience: str = "", objective: str = "",
                              context: str = "", series_name: str = "",
                              series_block: str = "", target_chars: int = 0,
                              images: int = 0) -> str:
    """씬별 영어 이미지 prompt + scene_meta 를 포함한 마스터 스크립트 JSON 생성 프롬프트.

    반환된 프롬프트를 LLM 에 주면 mp4maker/ComfyUI 호환 순수 JSON 을 출력한다.
    """
    lo_sec, hi_sec = minutes * 60 - 60, minutes * 60 + 60
    target_chars = int(target_chars) if target_chars else int(minutes * 60 * CPS)
    if images and images > 0:
        n_lo, n_hi = images, images + 2
    else:
        n_lo, n_hi = minutes * 2, minutes * 2 + 6
    per_chars = max(150, round(target_chars / n_lo))
    per_lo, per_hi = round(per_chars * 0.85), round(per_chars * 1.2)
    ch = f"ch{int(chapter):02d}"
    ctx = (f"\n\n## 근거 자료 (이 내용만 사실 근거로 사용 — 없는 사실은 지어내지 말 것)\n{context}\n"
           if context.strip() else "")
    aud = (target_audience or "").strip()
    obj = (objective or "").strip()
    aud_obj = (
        "## 대상/목적\n- 대상 청중과 목적은 **주제에 맞게 스스로 판단**하라.\n"
        if not aud and not obj else
        f"## 대상/목적\n- Target Audience: {aud or '(주제에 맞게 자동)'}\n- Objective: {obj or '(주제에 맞게 자동)'}\n"
    )
    title_rule = (f'"{title}"' if (title or "").strip()
                  else "(책/장 내용에 어울리는 한국어 제목을 직접 지어 채울 것)")
    series_sec = ""
    if (series_name or "").strip() or (series_block or "").strip():
        series_sec = (
            "## 시리즈 공통 (★ 같은 책의 모든 장에서 동일하게 유지)\n"
            + (f"- 시리즈(책): {series_name}\n" if (series_name or '').strip() else "")
            + (series_block.strip() + "\n" if (series_block or '').strip() else "")
            + "위 톤·비주얼·표기를 이 장의 모든 narration 과 image prompt 에 일관되게 적용하라.\n\n"
        )
    return f"""\
당신은 고품격 다큐멘터리의 수석 작가입니다. 아래 주제로 영상 제작용 '마스터 스크립트 JSON'을
**순수 JSON 객체 하나로만** 출력하세요. 코드펜스(```), 설명, 머리말 없이 JSON만 출력합니다.

## ★ 분량 = 글자수 (목표에 맞추기 — 가장 중요)
- 목표 분량 약 {minutes}분. TTS(SuperTonic3·M5)는 한국어를 약 {CPS}자/초로 읽으므로,
  **전체 narration_text 글자수 합계를 ≈ {target_chars}자에 맞춰라**(너무 모자라지도, 크게 넘치지도 않게).
- scene(=이미지) {n_lo}~{n_hi}개. **각 씬 narration_text는 약 {per_chars}자({per_lo}~{per_hi}자, 4~6문장)** 로 서술하라.
  ⚠️ 씬당 100~140자처럼 너무 짧게 쓰지 말 것. 반대로 한 씬을 과도하게 길게 늘이지도 말 것.
- 책 본문에 충실하게(사실·인물·연도·수치·일화 그대로), 재해석·각색·창작·과장 금지.
  표현·어조도 저자 의도·문체를 살리되 구어 내레이션을 위해 최소한만 다듬어라.
- 영어 image prompt 만 시각화를 위해 새로 쓰되, 그 장면도 본문이 묘사한 사실에 근거한다.
- 최상위 "title": {title_rule}.
- 언어: narration_text/title/subtitle/visual_description 은 한국어, image **prompt 는 영어**.
- 내레이션: 차분하고 권위있는 3인칭 다큐 톤. narration_seconds = 대략 글자수/{CPS}.
- 첫 scene 은 scene_type "opening_title", 마지막은 "next_preview"(또는 "closing"),
  분기/절정은 "climax", 나머지는 "body".

## 이미지 prompt 규칙 (ComfyUI txt2img 입력)
- 각 scene 의 "prompt" 는 40~80단어 영어, 다큐멘터리 시네마틱 묘사.
- 반드시 "documentary style, cinematic quality." 로 끝낼 것.
- "image_filename" 은 "{ch}_<2자리씬번호>_<영문슬러그>.png".
- **★ 실존 인물의 실명을 prompt 에 쓰지 마라.** 이름 대신 나이·국적·직업·행동·복장으로 묘사하라.
  (image_filename 슬러그엔 이름 써도 됨, prompt 본문만 금지)
- 특정 **브랜드/상표/캐릭터명**도 prompt 에선 일반 명사로 바꿔라.
- **★ 어린이 교육용 영상이므로 흡연 묘사(pipe, cigarette, cigar, smoking, smoke, tobacco)를 절대 넣지 마라.**
  손에 책·펜·안경을 들거나 빈손/생각하는 자세 등 무해한 행동으로 바꿔 묘사하라.

## 출력 JSON 스키마 (정확히 이 구조)
{{
  "version": "1.0",
  "chapter": {int(chapter)},
  "title": "{title or '(제목)'}",
  "subtitle": "",
  "genre": "classic-documentary-full",
  "aspect_ratio": "16:9",
  "total_duration_seconds": <모든 narration_seconds 합>,
  "default_transition": "crossfade",
  "narration_style": {{"tone": "차분하고 권위있는", "person": "3인칭", "tempo": "measured", "chars_per_second": {CPS}}},
  "scenes": [
    {{
      "scene": 1,
      "scene_type": "opening_title",
      "title": "...",
      "narration_text": "(여기에 반드시 {per_chars}자 이상, 4~6문장으로 충실히)",
      "narration_seconds": {max(8, round(per_chars / CPS))},
      "prompt": "... documentary style, cinematic quality.",
      "image_filename": "{ch}_01_opening_title.png",
      "visual_description": "...",
      "scene_meta": {{"era": "", "mood": "", "transition_hint": "crossfade", "text_overlay": "", "subtitle": "", "bgm_hint": ""}}
    }}
  ],
  "video_meta": {{"aspect_ratio": "16:9", "opening_title": "{title or '(제목)'}", "closing_text": "다음 장에서 계속...", "default_transition": "crossfade", "bgm_track": null}}
}}

{series_sec}{aud_obj}{ctx}
이것은 '책/단행본을 소개하는 다큐멘터리' 영상의 대본이다. 위 스키마대로 순수 JSON 하나만 출력하되,
**위 '분량=글자수' 요건(전체 ≈{target_chars}자, 씬당 약 {per_chars}자)에 맞춰라.**"""


def condense_narration_prompt(script_json: str, target_chars: int, current_chars: int) -> str:
    """narration_text 만 더 간결하게 축약(분량 초과 시). scene/prompt/image_filename 유지."""
    return f"""\
아래는 이미 만든 다큐멘터리 대본 JSON 이다. 현재 전체 narration_text 글자수는 약 {current_chars}자로,
목표 {target_chars}자보다 **많다**. 영상이 목표보다 길어지므로 줄여야 한다.

## 지시 (반드시)
- **각 scene 의 narration_text 를 더 간결하게 줄여**, 전체 합계가 **약 {target_chars}자**가 되게 하라.
- scene 개수·순서·title·prompt·image_filename·scene_meta 는 **절대 바꾸지 마라(그대로 유지)**. narration_text 만 축약.
- 핵심 사실·인물·연도·일화는 유지하되, 군더더기·중복·곁가지를 덜어내 압축한다. 새 내용 창작 금지.
- narration_seconds 는 각 narration_text 글자수 / {CPS} 로 갱신. total_duration_seconds 도 갱신.
- 코드펜스·설명 없이 **완성된 JSON 객체 하나만** 출력.

## 현재 JSON
{script_json}
"""


def expand_narration_prompt(script_json: str, context: str, target_chars: int,
                            current_chars: int) -> str:
    """narration_text 만 더 길게 보강(분량 미달 시). scene/prompt/image_filename 유지."""
    return f"""\
아래는 이미 만든 다큐멘터리 대본 JSON 이다. 현재 전체 narration_text 글자수는 약 {current_chars}자로,
목표 {target_chars}자에 **부족하다**. 영상이 목표 분량보다 짧아지므로 보강이 필요하다.

## 지시 (반드시)
- **각 scene 의 narration_text 를 책 본문 근거로 더 자세히 늘려**, 전체 합계가 **{target_chars}자 이상**이 되게 하라.
- scene 개수·순서·title·prompt·image_filename·scene_meta 는 **절대 바꾸지 마라(그대로 유지)**. narration_text 만 길게.
- 늘릴 때 사실·맥락·일화를 **더 풀어서** 쓰되, 창작·동어반복·군더더기는 금지.
- narration_seconds 는 각 narration_text 글자수 / {CPS} 로 갱신. total_duration_seconds 도 갱신.
- 코드펜스·설명 없이 **완성된 JSON 객체 하나만** 출력.

## 현재 JSON
{script_json}

## 근거 자료
{context}
"""


def youtube_meta_prompt(title: str, body: str, minutes: int = 0) -> str:
    """완성 영상용 유튜브 업로드 글(제목 후보·설명·해시태그·태그) 생성 프롬프트."""
    mins = f"약 {minutes}분" if minutes else ""
    return f"""\
당신은 유튜브 채널 운영·SEO 전문가입니다. 아래 다큐멘터리 영상 내용으로 유튜브 업로드용 글을
작성하세요. **아래 형식 그대로**, 코드펜스·머리말·설명 없이 한국어로만 출력합니다.

## 영상 정보
- 제목(가제): {title or '(제목 미정)'}
- 분량: {mins}
- 내용(대본 요약):
{body}

## 출력 형식 (정확히 이 순서/머리표)
[제목 후보]
- (클릭을 부르되 과장·낚시는 피한 40자 내외 제목 5개, 각 줄 '- ' 로 시작)

[설명]
(2~4문단. 첫 2줄에 핵심 훅(영상을 왜 봐야 하는지). 이어서 영상이 다루는 내용·의미를 요약.
 본문 사실에만 근거하고 없는 내용·과장은 금지. 마지막에 구독/좋아요 유도 1줄.)

[해시태그]
(#으로 시작하는 관련 태그 8~15개, 한 줄, 공백으로 구분)

[태그]
(유튜브 검색 최적화용 키워드 10~20개, 쉼표로 구분, 한 줄)
"""


def summary_note_prompt(title: str, body: str) -> str:
    """문제·정답·해설을 모아 학습 요약노트(Markdown) 를 만드는 프롬프트."""
    return f"""\
당신은 자격증/시험 대비 학습서의 저자입니다. 아래 '문제·정답·해설' 목록만을 근거로
학습자가 복습할 수 있는 **요약노트**를 작성하세요. **Markdown 으로만** 출력하고,
코드펜스(```), 머리말, 사족은 넣지 마세요. 본문 사실에만 근거하며 없는 내용은 지어내지 마세요.

## 자료
- 제목: {title or '(제목 없음)'}
- 문제·정답·해설:
{body}

## 출력 형식 (정확히 이 순서, Markdown 머리표 사용)
## 핵심 개념 정리
- (문제들이 다루는 개념을 항목별로 간결히 정리)

## 문제 유형별 접근법
- (자주 나오는 유형과 푸는 요령)

## 자주 틀리는 포인트
- (헷갈리기 쉬운 함정·오답 포인트)

## 한 줄 요약
(이 단원을 한 문장으로)
"""


def pronounce_prompt(text: str) -> str:
    """숫자·영어를 소리 나는 대로 한글로 바꾼 '읽기용' 한 줄 텍스트 생성(TTS 입력용)."""
    return (
        "다음 텍스트에서 숫자와 영어를 소리 나는 대로 한글로 바꾸고, 부연 설명이나 특수 기호 없이 "
        "딱 한 줄의 문장만 출력해 줘. 예: DDL→디디엘, SQL→에스큐엘, CREATE→크리에이트, "
        "ALTER→얼터, TRUNCATE→트렁케이트, INSERT→인서트, SELECT→셀렉트.\n"
        f"{text}"
    )


def classify_merge_prompt(topics: list[str], batch_text: str) -> str:
    """여러 챕터 요약을 읽고 각 개념을 세부항목으로 분류·통합하는 프롬프트."""
    topic_lines = "\n".join(f"- {t}" for t in topics) or "- (분류 목록 없음: 내용순으로 정리)"
    return f"""\
당신은 자격증 학습서 편집자입니다. 아래 여러 챕터의 요약을 읽고, 각 개념을 **세부항목 목록 중
가장 알맞은 하나**로 분류한 뒤, 세부항목별로 중복을 제거해 핵심만 간결히 정리하세요.

## 세부항목 목록 (이 이름을 그대로 머리표에 사용)
{topic_lines}

## 출력 형식 (Markdown 만, 코드펜스 금지)
내용이 있는 세부항목마다:
### <세부항목 이름 정확히>
- 핵심 요점 (간결한 불릿, 중복 제거)
내용이 없는 세부항목은 생략. 어느 세부항목에도 안 맞으면 `### 기타` 아래에 둡니다.
본문 사실에만 근거하고 없는 내용은 지어내지 마세요.

## 챕터 요약 모음
{batch_text}
"""


def topic_polish_prompt(topic: str, merged_text: str) -> str:
    """한 세부항목에 대해 여러 배치에서 모인 정리를 최종 통합하는 프롬프트."""
    return f"""\
아래는 '{topic}' 세부항목에 대해 여러 곳에서 모은 정리입니다. 중복을 제거하고 핵심 개념과
자주 틀리는 포인트를 간결한 Markdown 불릿으로 **최종 정리**하세요. 머리표(###)·코드펜스·사족 없이
불릿(-)만 출력합니다. 본문 사실에만 근거하세요.

{merged_text}
"""


def _main(argv: list[str] | None = None) -> int:
    import argparse
    import sys
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="대본 JSON 생성 프롬프트를 출력(LLM 에 붙여넣기용)")
    ap.add_argument("--chapter", type=int, default=1)
    ap.add_argument("--title", default="")
    ap.add_argument("--minutes", type=int, default=15)
    ap.add_argument("--target-chars", type=int, default=0)
    ap.add_argument("--images", type=int, default=0)
    args = ap.parse_args(argv)
    print(master_script_json_prompt(
        args.chapter, args.title, args.minutes,
        target_chars=args.target_chars, images=args.images))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
