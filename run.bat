@echo off
chcp 65001 >nul
REM ==========================================================================
REM  compy-ui web app launcher. Run setup.bat first. Browser opens automatically.
REM  ComfyUI is not used in this build (slides render locally). --reload restarts
REM  the server when code changes.
REM ==========================================================================
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [setup] Virtual environment not found. Run setup.bat first.
  pause
  exit /b 1
)

REM Web app port. Change this one value if the port is in use.
set "PORT=8830"

set "PYTHONPATH=%~dp0;%PYTHONPATH%"
echo [run] Open http://localhost:%PORT% in your browser  (close this window to stop)

start "" http://localhost:%PORT%

".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT% --reload --reload-dir app --reload-dir services --reload-dir voicewright --reload-dir mp4maker --reload-dir slides
endlocal
