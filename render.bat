@echo off
chcp 65001 >nul
REM ==========================================================================
REM  render.bat — 05 번들(deck.html) → 밝은 일반영상 (슬라이드+음성/자막+mp4) 한 번에
REM
REM  #2(exambook-forge)가 만든 05\<번들>\ (source\deck.html + script\<번들>_script.json)을
REM  입력으로: deck.html 캡처(headless Chromium) + 카운트다운(54321) +
REM            Supertonic3 음성/자막 + ffmpeg 합성.
REM  결과: <book>\05\<번들>\draft\<번들>.static.mp4  (+ review.json 갱신)
REM
REM  사용법:
REM    render.bat                    -> 05\ 아래 모든 번들 한 번에 (흩어진 json 전부 렌더)
REM    render.bat m01-1              -> 그 번들 하나만
REM    render.bat m01-1 --no-audio   -> 슬라이드 캡처만(음성/합성 생략; 디자인 확인용)
REM
REM  최초 1회: .venv\Scripts\python -m playwright install chromium
REM  (디자인만 빨리 보려면 05\<번들>\source\deck.html 을 브라우저로 직접 열면 됨)
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
  REM 인자 없음 = 05\ 아래 흩어진 모든 번들을 한 번에 렌더
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
echo [done] 결과: %BOOK%\05\<번들>\draft\<번들>.static.mp4
pause
endlocal
