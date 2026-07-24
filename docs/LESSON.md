# 문제집 / 강의(lesson) → 영상

compy-ui 의 대본→이미지→음성→MP4 파이프라인을 **문제집(quiz) 영상**으로 확장한 기능.
ComfyUI 대신 로컬에서 **텍스트 슬라이드**(문제/보기/정답/해설 + 앞부분 개념 강의)를
Pillow 로 렌더하고, "요소 순차 등장 + 정답 강조" 모션 클립으로 만든 뒤 기존 TTS·자막·
ffmpeg 합성을 그대로 태운다. 과목 무관(SQLD·수학·영어…), `theme` 로 과목/회차별 색 지정.

## 워크플로우

1. **번들 생성** — 헤더의 [+ 새 번들] (예: `ch01`).
2. **[1 대본] 탭 → 문제집/강의 카드** — `lesson JSON` 을 붙여넣거나 파일로 불러와
   **[🧩 레슨 저장 → 씬 변환]**. 블록이 씬으로 컴파일되어 `script/chNN_script.json` 저장.
   샘플: `samples/lesson_1.json · lesson_5.json · lesson_10.json`.
3. **[2 이미지] 탭 → [🖼 슬라이드 생성]** — `images/`(포스터 PNG) + `clips/`(모션 mp4) 생성.
   "요소 순차 등장 모션" 체크 해제 시 정적 PNG만.
4. **[⚡ 한 번에 만들기]** — 레슨 번들은 자동 감지되어 슬라이드→음성/자막→MP4(자막 안전영역,
   Ken Burns off)로 한 번에. (2·3단계를 개별로 눌러도 됨)
5. **[4 결과] 탭 → [📔 요약노트 생성]** — 문제·정답·해설을 모아 학습 요약노트(Markdown,
   `draft/chNN_summary.md`). 다음 회차 앞부분 개념 강의 소스로 재사용 가능.

CLI 로 슬라이드만 미리 볼 수도 있다:

    python -m slides munje/ch01           # images/ + clips/
    python -m slides munje/ch01 --motion off   # 정적 PNG만

## lesson JSON 스키마

최상위는 순서 있는 `blocks` 배열. 각 블록은 `kind` 로 구분하고 화면 데이터 + 낭독/자막
텍스트(`narration`)를 함께 가진다(= 음성·자막 원천).

```jsonc
{
  "kind": "lesson", "chapter": 1, "title": "1과 · ...", "subject": "SQLD",
  "theme": "sqld",              // 팔레트 키(sqld/math/eng/science/amber/teal/slate) 또는 "#1b3a5b"
  "scenes_per_problem": 2,       // 기본 2 (문제 제시 / 정답·해설)
  "blocks": [
    { "kind": "section", "title": "개념 강의", "subtitle": "...", "narration": "..." },
    { "kind": "concept", "heading": "엔터티란?", "bullets": ["...", "..."], "narration": "..." },
    { "kind": "ox", "heading": "헷갈리는 OX",
      "items": [ { "q": "...", "a": "O", "note": "..." } ], "narration": "..." },
    { "kind": "table", "heading": "SQL 분류",
      "columns": ["분류","명령어"], "rows": [["DDL","CREATE, ALTER, DROP"]], "narration": "..." },
    { "kind": "problem", "number": 1, "type": "multiple_choice",
      "question": "...", "choices": ["...","..."],
      "answer": "②", "answer_index": 1, "explanation": "...",
      "difficulty": "중", "tags": ["엔터티"],
      "narration_question": "", "narration_answer": "" }   // 비우면 자동 생성
  ]
}
```

- `blocks` 대신 `problems: [...]` 만 줘도 동작(전부 problem 으로 취급).
- **`include_lecture: false`** (최상위) — section/concept/ox/table 강의 블록을 **영상에서 제외**하고
  문제(problem)만 렌더한다. 강의 내용은 JSON 에 그대로 남아 요약노트·다음 회차 재사용에 쓸 수 있다.
  (기본 true = 강의 블록도 영상에 포함)
- **자막**: 문제집(lesson) 영상은 화면 자막(하드번인)을 **굽지 않는다**(mp4maker `--no-subs` 자동).
  음성 나레이션은 그대로 나온다. (일반 다큐 대본 경로는 기존대로 자막 번인)
- `problem.type`: `multiple_choice` | `short_answer` | `ox`. MC 는 `answer_index`(0-based)로
  정답 강조, 없으면 `answer`("②"/"3"...)에서 유추. `choices` 없으면 단답형.
- 긴 해설은 자동으로 여러 정답 씬으로 **페이지 분할**된다(슬라이드 넘침 방지).
- **`explanation_speech`** (문제): 정답 슬라이드는 간결한 `explanation`을 보여주고, **음성은 이 설명투 대본**을
  읽는다(슬라이드≠음성). 없으면 `narration_answer` → 자동 문구 순으로 폴백. 음성이 길수록 슬라이드도 그만큼 머문다.
- **`countdown_seconds`** (최상위, 기본 5): 문제와 해설 사이에 **'생각할 시간'** 씬(무음). 앞 문제(질문+보기)를
  그대로 보여주며 우하단에 5→1 타이머 배지가 돈다. `0`이면 끔.
- **`gap_seconds`** (최상위, 기본 1.5): 해설이 끝나고 **다음 문제로 넘어가기 전 짧은 간격**(무음). `0`이면 끔.
- **`ai_reading`** (최상위, 기본 true): **⚡ 한 번에 만들기가 AI 발음까지 자동 적용**(숫자·영어→한글 읽기)해
  버튼 한 번으로 끝난다. `false`면 원문 그대로 읽음(별도 [🔤 AI 발음] 버튼으로 수동 처리).
- **`round`**(최상위 기본 회차) + **`source_no`**(문제별 원 번호): 정답 슬라이드 우상단에 **"출처 · 제50회 12번"** 표기,
  통합 요약노트의 기출 색인에 모임. (문제별 `round`로 개별 지정도 가능, `source` 문자열로 통째 지정도 가능)
- **`voice`**(기본 F2 강의체) · **`speed`**(기본 1.05): 문제집 음성/속도. 3탭에서 씬별 조정도 가능.
- **AI 발음**: 3탭 [🔤 AI 발음으로 전체 음성 생성] → 숫자·영어를 소리 나는 대로 한글(CREATE→크리에이트)로 읽음.

## 규모 가이드

- 권장 번들 크기: **문제 5~10개**(씬 10~20), 상한 ~15문제(~30씬).
- 1000문제는 **10문제씩 ~100번들**(`ch01`…`ch100`)로 나눠 렌더 → 불량 번들이 나머지를
  오염시키지 않고, `--only` 로 씬 단위 재렌더가 가능하다.

## 폰트

`assets/fonts/` 에 Pretendard TTF 를 넣으면 사용, 없으면 시스템 한글 폰트(맑은 고딕)로 폴백.
자세한 내용은 `assets/fonts/README.md`.

## 구현 위치

- `services/workbook.py` — lesson JSON 파싱/컴파일(`lesson_to_script`).
- `slides/` — 렌더러: `theme`(팔레트)·`layout`(그리기)·`animate`(모션 클립)·`render`(번들 처리).
- `services/summary.py` + `script_prompt.summary_note_prompt` — 요약노트.
- `app/routes_pipeline.py` — `save_lesson` / `generate_slides` / `summary_note` 엔드포인트,
  `_job_oneclick`/`_job_render` 의 레슨 감지(슬라이드 + `--kenburns off`).
