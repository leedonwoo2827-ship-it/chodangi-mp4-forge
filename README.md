# 초당기(chodangi) MP4 — 이 PC 커스텀 빌드

> 이 폴더는 `ocr-output-260723\04\lesson_mXX.json` 을 입력으로 받아 **웹 UI 없이 배치 한 방**으로
> 해설영상(mp4)을 뽑도록 커스터마이징한 설치본입니다. (원본 README 는 아래에 그대로 둡니다.)

## 배치로 한 번에 (권장 경로)
```bat
render.bat                      REM m01, m02, m03 전체 → munje\chNN\draft\chNN_final.mp4 3개
render.bat m01                  REM m01 한 개만
render.bat m02 --max-problems 2 REM 앞 2문제만 빠른 테스트(mp4 생성)
render.bat m01 --no-audio       REM 음성 없이 슬라이드만
```
- 파이프라인: `lesson JSON → 대본 컴파일 → 슬라이드(+54321 카운트다운) → Supertonic3 음성/자막 → mp4maker(ffmpeg)`.
- 단계별 세부 점검: `.venv\Scripts\python -m slides munje\ch01` / `... -m mp4maker munje\ch01` / `python make_video.py --help`.

## 이 빌드의 커스터마이징 요약
- **의존성 0 지향**: `requirements-render.txt`(onnxruntime·numpy·soundfile·pyyaml·pydantic·pysrt·lxml·Pillow)만으로 렌더 경로 동작. ComfyUI/LLM/PDF 계열 불필요. **Supertonic3** 는 `assets\`(HF `Supertone/supertonic-3`, onnx+voice_styles)로 완전 로컬 — PyTorch·클라우드·API키 없음.
- **요약(5.요약노트) 프로세스 제거** — 라우트·서비스·웹 5번 탭 삭제.
- **문제→해설 전환 54321 카운트다운** — `countdown_seconds:5`/`scenes_per_problem:2`로 "생각할 시간" 5→4→3→2→1(기존 스타일 유지).
- **SVG "지금 돌아가게" 조치**(`services/figures.py`): 문제/해설의 `![](assets/x.svg)` 마크다운을 화면/음성 텍스트에서 제거하고, 참조 SVG 를 `02\assets` 에서 번들 `images\` 로 자동 복사(누락 시 경고만). `cairosvg` 설치 시 PNG 로 자동 변환(도식 표시는 향후 렌더러 확장 지점).

## 남은 데이터 품질 메모(상위 플러그인 피드백 대상)
- 보기 문자열에 이미 `①②③④` 가 들어있어 렌더러 기호와 **중복**(`③ ③`)으로 보임 → 보기에서 접두 기호 제거 또는 렌더러 기호 비표시 중 택1.
- 해설 텍스트의 `**볼드**` 마크다운이 리터럴로 노출 → 상위 생성 단계에서 순수 텍스트로 내리거나 렌더러에 볼드 파싱 추가.
- 위 두 가지는 이번 설치 범위 밖(데이터/렌더 스타일)이라 손대지 않았습니다.

---

# compy-ui-mujejip — 문제집 → 강의/복습 영상 도구

**문제집(JSON) → 텍스트 슬라이드(요소 순차 등장 모션) → 음성/자막 → MP4**, 그리고
여러 회차의 해설을 모아 **공식 출제기준 순서의 통합 요약노트**까지 — 웹 화면 하나에서
버튼 몇 개로. 클라우드 없이, API 키 없이, 이 폴더 하나로 로컬 실행됩니다. (SQLD 예시로
만들었지만 `subject`/`theme`만 바꾸면 어떤 과목·자격증에도 적용됩니다.)

- **슬라이드**: 문제·보기·정답·해설을 로컬에서 렌더(Pillow+ffmpeg) — **ComfyUI 불필요**
- **음성/자막**: **Supertonic3** 로컬 TTS(문제집 기본 강의체 F2) · 합성 **ffmpeg**
- **54321 카운트다운**: 문제→해설 전환에 "생각할 시간" 5→4→3→2→1

> 이 빌드는 **ComfyUI(다큐 이미지 생성)와 요약노트 기능을 제거**한 문제집 전용 버전입니다.

## 문제집 빠른 시작
1. `setup.bat` (최초 1회) → `run.bat` → 브라우저 `http://localhost:8830`
2. **[+ 새 번들]** `ch01` → **[1 대본]** 탭에서 `samples/lesson_1.json` 불러와 **[🧩 레슨 저장]**
3. **[2 이미지]** → **[🖼 슬라이드 생성]** → 헤더 **[⚡ 한 번에 만들기]**
4. **[4 결과]** 미리보기/다운로드  (요약노트 탭은 이 빌드에서 제거됨)

문제집 JSON은 `ocr-output-260723\04\lesson_mXX.json` 형식(스키마는 `_context\HANDOFF-to-pipeline2.md` 참고).
`include_lecture:false`면 영상은 문제만, `round`/`source_no`로 기출 출처 표기.

## 두 가지 실행 경로
- **A. 배치 한 방(헤드리스, 권장)** → `render.bat` (맨 위 "이 PC 커스텀 빌드" 참고). 웹 없이 mp4 생성.
- **B. 웹 UI** → `setup.bat`(최초 1회) → `run.bat` → `http://localhost:8830`. 번들 만들고 단계별 버튼.
  - 준비물: **Python 3.11~3.13**(Add to PATH) · **ffmpeg**(`winget install Gyan.FFmpeg`) · **git + git-lfs**
  - `setup.bat` = 가상환경 + 라이브러리 + Supertonic3 모델 설치. **ComfyUI 불필요.**

## 폴더(번들) 규약
```
munje/chNN/
  script/      chNN_script.json          ← lesson 컴파일 결과
  images/      chNN_XX_*.png             ← 슬라이드(자동) + 복사된 도식 SVG
  clips/       chNN_XX.mp4               ← 요소 등장/카운트다운 모션(자동)
  audio/       chNN_XX_narration.wav     ← Supertonic3(자동)
  subtitles/   chNN_XX_narration.srt     ← 자동
  draft/       chNN_final.mp4            ← ffmpeg(자동)
```

## 구성
voicewright(로컬 TTS, Supertone Supertonic3) + slides(Pillow 슬라이드) + mp4maker(ffmpeg 합성).
이미지는 전부 로컬 Pillow 렌더 — 외부 서비스/ComfyUI 연동 없음.
