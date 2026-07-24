# 번들 규약 (BUNDLE)

모든 단계는 **번들 폴더 하나**를 통해 파일을 주고받는다. 서로 직접 호출하지 않는다.

```
_assets/ch90_bundle/                 ← 이름: chNN_bundle (NN=2자리)
├── script/      ch90_script.json    ← Claude/scriptforge (사람이 넣음)
├── images/      ch90_01_*.png        ← FlowGenie 결과 가져옴 (씬당 1장)
├── audio/       ch90_01_narration.wav    ← 자동(TTS)
├── subtitles/   ch90_01_narration.srt    ← 자동, + ch90.srt(통합)
└── draft/       ch90_final.mp4       ← 자동(합성)
```

## 파일명 규칙
| 종류 | 패턴 | 예 |
|---|---|---|
| 대본 | `chNN_script.json` (1개) | `ch90_script.json` |
| 이미지 | `chNN_XX*.{png,jpg,jpeg,webp}` | `ch90_01_opening.png` |
| 오디오 | `chNN_XX_narration.{wav,mp3,...}` | `ch90_01_narration.wav` |
| 씬 자막 | `chNN_XX_narration.srt` | `ch90_01_narration.srt` |
| 통합 자막 | `chNN.srt` | `ch90.srt` |

`NN`(챕터), `XX`(씬)는 모두 2자리 0-padded.

## 대본 JSON (mp4maker/TTS가 실제로 쓰는 필드)
```json
{
  "chapter": 90,
  "title": "...",
  "scenes": [
    { "scene": 1, "title": "오프닝",
      "narration_text": "자막/음성으로 들어갈 한국어",
      "narration_seconds": 6,
      "image_filename": "ch90_01_opening.png" }
  ]
}
```
- `narration_text` → TTS 입력 + 자막. `image_filename` → 이미지 매칭 시작점(폴백 있음).
- `narration_seconds` 는 hint (실제 길이는 오디오로 측정). `prompt`/`model` 등 그 외 필드는 무시.

## 무결성 규칙
- 씬마다 **이미지 + 오디오 필수** (없으면 렌더가 누락 씬 번호 출력하고 중단).
- 자막은 씬별/통합 중 하나만 있어도 OK (없으면 narration_text로 자동 생성).

## 이미지 매칭 폴백 (중요)
JSON `image_filename` 과 실제 파일이 조금 달라도 자동 매칭한다:
- 확장자 차이 (`.png` ↔ `.jpeg`)
- 변형 접미사 (`_1`, `_2`, `(2)`) — **가장 마지막(번호 큰/최신) 것을 사용**
- `ch` 접두 유무 (`ch90_01*` ↔ `90_01*`)
