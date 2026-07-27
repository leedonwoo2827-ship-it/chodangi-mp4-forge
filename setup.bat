@echo off
chcp 65001 >nul
REM ==========================================================================
REM  compy-ui setup (Windows) - self-contained.
REM  Creates a virtual env, installs deps, downloads the local TTS models,
REM  and checks ffmpeg. Run this once before run.bat / render.bat.
REM  (ComfyUI is not used in this build - slides are rendered locally.)
REM ==========================================================================
setlocal
cd /d "%~dp0"

where python >nul 2>nul || (echo [error] Install Python 3.11-3.13 first. & pause & exit /b 1)

echo [setup] Creating virtual environment (.venv)
if not exist ".venv\Scripts\python.exe" python -m venv .venv || (pause & exit /b 1)

echo [setup] Installing dependencies
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt || (pause & exit /b 1)

echo [setup] Checking ffmpeg
where ffmpeg >nul 2>nul || echo [warn] ffmpeg not on PATH. Install: winget install Gyan.FFmpeg

echo [setup] Installing Playwright Chromium (deck.html 슬라이드 캡처, 파이프라인 05)
".venv\Scripts\python.exe" -m playwright install chromium || echo [warn] playwright chromium 설치 실패 - deck 캡처 경로(make_bundle_video.py)만 영향. Pillow 경로(make_video.py)는 정상.

echo [setup] Checking TTS models (assets\onnx)
if exist "assets\onnx\vocoder.onnx" (
  echo   models already present - skip.
) else (
  echo   models not found. Downloading from HuggingFace ^(~380MB-1GB, needs git-lfs^).
  echo   ^(or copy an existing assets folder from another PC and press Ctrl+C^)
  powershell -ExecutionPolicy Bypass -File "scripts\setup_assets.ps1"
)

echo [setup] Preparing .env
if not exist ".env" (
  if exist ".env.example" ( copy /y ".env.example" ".env" >nul & echo   created .env from .env.example )
) else (
  echo   .env already present - keep.
)

echo.
echo [setup] Done. Double-click run.bat (web UI) or render.bat (batch MP4).
pause
endlocal
