# 벤더된 코드 수정 내역 (CUSTOMIZATIONS)

mediaforge는 `voicewright/` 와 `mp4maker/` 를 GitHub 원본에서 복사(vendor)해 들였다.
원본을 다시 받아 덮어쓰면 아래 수정이 사라지므로, **재동기화 시 이 문서를 보고 다시 적용**한다.

## voicewright/engine.py — 합성 시 발음 변환 항상 풀옵션
- `synth()` 의 `pmap.apply(text)` → `apply(text, spell_unknown_acronyms=True, convert_years=True)`.
- 모든 합성 경로(배치/씬/⚡한번에)가 **연도(1989년→천구백팔십구년)·영문약어·숫자단위**까지
  자동 변환. 자막(SRT)에는 적용 안 됨(원문 유지).

## voicewright/batch.py — flat 번들 출력
- `run_batch(..., flat_layout: bool = False)` 추가.
- `flat_layout=True` 면 `output_root/audio`·`output_root/subtitles` 에 직접 쓴다
  (원본은 `output_root/ch{NN}/audio`). mp4maker 번들 규약에 맞추기 위함.
- mediaforge의 `app/synth.py::synthesize()` 가 이 옵션을 켜서 호출.

## mp4maker/bundle.py — 이미지 "마지막 변형" 우선
- `_find_image` 가 `_1`(처음 것) 대신 **번호 큰/최신** 변형을 쓰도록 변경
  (`_variant_rank` 헬퍼 추가, `max(...)` 사용). Flow 재생성 시 최신 컷이 렌더됨.

## mp4maker — YouTube 친화 인코딩 + 자막 너비 기본값
- `render_scene.py SceneRenderConfig`: `crf 18→20`, `audio_bitrate 192k→128k`,
  `maxrate="12M"`, `bufsize="24M"` 필드 추가 + cmd에 `-maxrate/-bufsize` 반영.
- `concat.py concat_with_crossfade`: 하드코딩 `crf 18/192k` → 파라미터화(기본 CRF 20 + maxrate).
- `cli.py`: `--crf/--preset/--audio-bitrate/--maxrate/--bufsize` 플래그 추가,
  `--font-size 16→14`, `--wrap-chars 35→50` (자막이 둘째 줄로 잘 안 넘어가게).
  → cfg/concat 로 전달.

> 자막 **개수(cue)** 분할 로직(`voicewright/srt.py`)은 의도적으로 손대지 않았다.
> "한 줄 너비"만 넓히고 폰트를 약간 줄여 두 줄 넘침을 줄이는 방식.
