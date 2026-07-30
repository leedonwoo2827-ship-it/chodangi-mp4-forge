@echo off
chcp 65001 >nul
REM ==========================================================================
REM  render.bat  --  05 bundle (deck.html) -> bright general video
REM                  (slides + voice/subtitles + mp4)
REM
REM  Input: 05\<bundle>\ made by pipeline #2 (source\deck.html + script\<bundle>_script.json)
REM  Steps: capture deck.html (headless Chromium) + countdown(54321)
REM         + Supertonic3 voice/subtitles + ffmpeg mux.
REM  Output: <book>\05\<bundle>\draft\<bundle>.static.mp4  (updates review.json)
REM
REM  Usage:
REM    render.bat                     -> render ALL bundles under 05\  (double-click)
REM    render.bat m01-1               -> one bundle only  (from cmd)
REM    render.bat m01-1 --no-audio    -> slides capture only (skip voice/mux)
REM    [drag] drop a bundle folder or script\*.json ONTO this render.bat (multiple OK)
REM    [copy-and-run] put your 05\<bundle> folders into  work\05\  next to this file,
REM                  then double-click render.bat -> renders everything in work\05\.
REM
REM  First time once: .venv\Scripts\python -m playwright install chromium
REM  (to preview design fast, just open 05\<bundle>\source\deck.html in a browser)
REM ==========================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [error] .venv not found. Run: python -m venv .venv
  echo         then: .venv\Scripts\python -m pip install -r requirements-render.txt
  echo         then: .venv\Scripts\python -m playwright install chromium
  pause & exit /b 1
)

REM Book root (folder that holds the 04/05 stages).
REM  우선순위: 로컬 work\05\ 에 번들을 복사해 넣었으면 그걸 쓰고, 없으면 아래 기본 경로.
REM  → 다른 책/과목도 render.bat 옆 work\05\ 에 05\<번들> 폴더만 복사하면 여기서 전체 렌더.
set "BOOK=D:\00work\ocr-output-260723"
if exist "%~dp0work\05" set "BOOK=%~dp0work"
set "PY=.venv\Scripts\python.exe"

if "%~1"=="" goto :all
REM Flags like --force / --no-audio apply to the full 05\ scan.
set "A1=%~1"
if "!A1:~0,1!"=="-" goto :allflags
REM Decide: dropped PATH (drag) vs ROUND code (typed). Path -> %~1 != %~nx1
if "%~1"=="%~nx1" goto :roundmode

REM ---- drag-and-drop: pass the dropped bundle/json path(s) straight through ----
"%PY%" make_bundle_video.py %*
goto :end

:allflags
"%PY%" make_bundle_video.py --book "%BOOK%" %*
goto :end

:roundmode
set "RND=%~1"
shift
set "REST="
:collect
if not "%~1"=="" ( set "REST=!REST! %1" & shift & goto :collect )
"%PY%" make_bundle_video.py --book "%BOOK%" --round "!RND!" !REST!
goto :end

:all
"%PY%" make_bundle_video.py --book "%BOOK%"
goto :end

:end
echo.
echo [done] output: %BOOK%\05\^<bundle^>\draft\^<bundle^>.static.mp4
pause
endlocal
