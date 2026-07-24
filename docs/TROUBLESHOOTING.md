# 문제 해결 (TROUBLESHOOTING)

| 증상 | 확인 / 해결 |
|---|---|
| **이미지가 안 가져와짐** | 파일명이 `chNN_XX_*` 규칙인지(Flow가 저장한 이름). 위치가 `Downloads/FlowGenie/` 또는 `Downloads/` 인지. 번들 이름이 `chNN_bundle` 인지. |
| **옛날 이미지가 렌더됨** | 여러 번 뽑아 `_1,_2,…`가 쌓인 경우. 가져오기는 **최신(번호 큰)** 것을, 렌더도 최신을 쓴다. 그래도 옛 게 나오면 `images/`에 남은 옛 파일을 지우고 다시 가져오기. |
| **"씬N 이미지 없음"으로 멈춤** | 그 씬 이미지를 Flow에서 받아 Downloads에 두고 다시 ⚡. 무결성상 씬마다 이미지+오디오 필수. |
| **렌더 에러 / 오디오 없음** | 오디오는 필수(자막은 자동 폴백). `audio/chNN_XX_narration.wav` 존재 확인. [3 음성/자막]에서 먼저 생성. |
| **한국어 발음이 틀림** | `📖 발음 사전`에 `표기 → 읽는법` 추가 → 그 씬만 다시 생성. (자막엔 원문 유지, 합성에만 적용) |
| **파일이 너무 큼 (YouTube)** | 기본이 이미 CRF 20 + 12M 상한. 더 줄이려면 `python -m mp4maker <bundle> --crf 23 --maxrate 8M`. |
| **자막이 둘째 줄로 넘어감** | `--wrap-chars` 를 키우거나 `--font-size` 를 줄인다 (기본 50 / 14). 예: `--wrap-chars 56 --font-size 13`. |
| **ffmpeg 못 찾음** | `winget install Gyan.FFmpeg` 후 새 터미널. `python -m mp4maker --probe` 로 확인. |
| **TTS 모델 못 찾음** | `assets/onnx`, `assets/voice_styles` 에 모델이 있는지, 또는 `VOICEWRIGHT_ASSETS_DIR` 환경변수 확인. |
| **포트 충돌(8830)** | `uvicorn app.main:app --port 8000` 로 다른 포트. |
