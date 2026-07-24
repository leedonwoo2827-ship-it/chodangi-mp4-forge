# 실행 가이드 (RUN)

## 설치 (한 번)
```powershell
setup.bat                       # .venv 생성 + 의존성 설치
# TTS 모델을 assets\onnx, assets\voice_styles 에 둔다 (README 참고)
```
ffmpeg 필요: `winget install Gyan.FFmpeg` (설치 후 새 터미널).

## 웹앱 실행
```powershell
run.bat                         # → http://localhost:8830
```
- 크롬 확장이 아니라 **로컬 웹앱**. 브라우저로 접속해 쓴다.
- 종료: 터미널에서 Ctrl+C.

## TTS 모델 위치 바꾸기
다른 곳의 모델을 쓰려면 환경변수로 가리킨다:
```powershell
set VOICEWRIGHT_ASSETS_DIR=D:\path\to\assets
run.bat
```

## 단계별 CLI (디버깅용)
```powershell
.venv\Scripts\activate
python ingest\import_images.py _assets\ch90_bundle      # 이미지 가져오기 (최신 변형만)
python -m mp4maker --probe                              # ffmpeg/폰트 점검
python -m mp4maker _assets\ch90_bundle --dry-run        # 검증만
python -m mp4maker _assets\ch90_bundle --only 1 --keep-work   # 1씬만
python -m mp4maker _assets\ch90_bundle                  # 풀 렌더
```

## 포트 바꾸기
```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```
