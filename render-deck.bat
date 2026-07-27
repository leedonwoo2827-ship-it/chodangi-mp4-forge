@echo off
chcp 65001 >nul
REM ==========================================================================
REM  render-deck.bat — 05 번들(deck.html) -> 일반영상 static.mp4 (밝은 슬라이드)
REM
REM  파이프라인 05: exambook-forge(#2)가 만든 05\<회차>\ 번들을 입력으로
REM    deck.html 캡처(headless Chromium) + Supertonic3 음성/자막 + ffmpeg 합성.
REM  결과: <book>\05\<회차>\draft\<회차>.static.mp4 + review.json 갱신.
REM  이후 리모션(키네틱) 영상은 클로드 데스크탑에서 script\<회차>_script.json 로 생성.
REM
REM  사용법:
REM    render-deck.bat                 -> 05\ 아래 모든 회차
REM    render-deck.bat m01             -> m01 한 개만
REM    render-deck.bat m01 --no-audio  -> 슬라이드 캡처만(음성/합성 생략)
REM
REM  전제(먼저 #2에서): python scripts\bundle.py --book <book> --round m01
REM  (기존 어두운 Pillow 경로는 render.bat)
REM ==========================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [error] .venv 없음. 먼저: python -m venv .venv  그리고  .venv\Scripts\python -m pip install -r requirements-render.txt
  echo         그리고: .venv\Scripts\python -m playwright install chromium
  pause & exit /b 1
)

REM 책 루트(04/05 스테이지가 있는 곳). 필요하면 이 한 줄만 수정.
set "BOOK=D:\00work\ocr-output-260723"
set "PY=.venv\Scripts\python.exe"

if "%~1"=="" (
  "%PY%" make_bundle_video.py --book "%BOOK%"
) else (
  set "RND=%~1"
  shift
  set "REST="
  :collect
  if not "%~1"=="" ( set "REST=!REST! %1" & shift & goto :collect )
  "%PY%" make_bundle_video.py --book "%BOOK%" --round "!RND!" !REST!
)

echo.
echo [done] 결과: %BOOK%\05\<회차>\draft\<회차>.static.mp4
pause
endlocal
