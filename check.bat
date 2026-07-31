@echo off
chcp 65001 >nul
REM ==========================================================================
REM  check.bat  --  build the 06 answer-check web (SQLD workbook)
REM
REM  Reads 05\*\source\lesson_*.json + 03 theory, and writes <book>\06\ :
REM    check.html, problems.js, videos.js, theory.js, theory_content.js(baked),
REM    assets\, figs\, videos\, theory\assets\
REM  Theory is BAKED into theory_content.js (no fetch, no iframe) -> works on
REM  local double-click (file://) AND on the web server. Upload the 06 folder.
REM
REM  Usage:
REM    check.bat                         -> default book, videos of round 1
REM    check.bat --video-rounds 1,2      -> also copy round 2 videos
REM    check.bat --book D:\path\to\book  -> different book root
REM ==========================================================================
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [error] .venv not found. First run: python -m venv .venv
  echo         then: .venv\Scripts\python -m pip install -r requirements-render.txt
  pause & exit /b 1
)

".venv\Scripts\python.exe" scripts\build_check.py %*

echo.
echo [done] 06 check web built. Upload the whole 06 folder to your server.
pause
endlocal
