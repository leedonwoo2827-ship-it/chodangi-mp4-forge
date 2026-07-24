@echo off
chcp 65001 >nul
REM ==========================================================================
REM  render.bat — 문제집 lesson JSON -> MP4 (헤드리스, 웹 UI 없이)
REM
REM  사용법:
REM    render.bat                      -> m01, m02, m03 전체 렌더 (mp4 3개)
REM    render.bat m01                  -> m01 한 개만
REM    render.bat m02 --max-problems 2 -> m02 의 앞 2문제만 빠른 테스트(mp4 생성)
REM    render.bat m01 --no-audio       -> 음성 없이 슬라이드만
REM
REM  결과: munje\chNN\draft\chNN_final.mp4
REM  세부 조정(단계별): python -m slides munje\ch01  /  python -m mp4maker munje\ch01
REM ==========================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [error] .venv 없음. 먼저: python -m venv .venv  그리고  .venv\Scripts\python -m pip install -r requirements-render.txt
  pause & exit /b 1
)

REM lesson JSON 이 있는 폴더(초당기 파이프라인 04 스테이지). 필요하면 이 한 줄만 수정.
set "OCR_OUT=D:\00work\ocr-output-260723\04"
set "PY=.venv\Scripts\python.exe"

if "%~1"=="" goto :all

REM ---- 단일 레슨 모드: 첫 인자 = mNN, 나머지 인자는 make_video.py 로 패스스루 ----
set "LESSON=%~1"
shift
set "REST="
:collect
if "%~1"=="" goto :run_one
set "REST=!REST! %1"
shift
goto :collect

:run_one
call :chapter_of "!LESSON!"
echo === !LESSON!  chapter !CH! ===
"%PY%" make_video.py --lesson "%OCR_OUT%\lesson_!LESSON!.json" --chapter !CH!!REST!
goto :eof

REM ---- 전체 모드: m01, m02, m03 ----
:all
for %%L in (m01 m02 m03) do (
  call :chapter_of "%%L"
  echo === %%L  chapter !CH! ===
  "%PY%" make_video.py --lesson "%OCR_OUT%\lesson_%%L.json" --chapter !CH!
  if errorlevel 1 (
    echo [error] %%L 렌더 실패 - 중단.
    pause & exit /b 1
  )
)
echo.
echo [done] 전체 완료. 결과: munje\ch01\draft, munje\ch02\draft, munje\ch03\draft
pause
goto :eof

REM ---- mNN -> 챕터 번호(선행 0 제거). m01->1, m02->2, m10->10 ----
:chapter_of
set "_m=%~1"
set "_n=!_m:m=!"
set /a CH=1!_n! - 100
goto :eof
