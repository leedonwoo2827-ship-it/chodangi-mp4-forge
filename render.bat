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
REM  TWO MODES, auto-detected -- ONE file works in both places:
REM   [repo] this file sits NEXT TO make_bundle_video.py
REM          BOOK = D:\00work\ocr-output-260723 , or work\ when work\05\ exists.
REM   [book] this file was COPIED into a book root (the folder that holds 05\)
REM          BOOK = that folder. The repo is auto-detected, in this order:
REM            %CHODANGI_HOME%  ->  ..\*chodangi*  ->  D:\00work\260724-chodangi-mp4
REM          A candidate counts only if it has BOTH
REM            .venv\Scripts\python.exe  AND  make_bundle_video.py
REM
REM  Usage:
REM    render.bat                     -> render ALL bundles under 05\  (double-click)
REM    render.bat m01-1               -> one bundle only  (from cmd)
REM    render.bat m01-1 --no-audio    -> slides only (skip voice/mux)
REM    render.bat --reuse-images      -> reuse 05\<b>\images\slide_NN.png, no Chromium
REM    render.bat --force             -> re-render bundles that are already done
REM    render.bat --help              -> full flag list
REM    [drag] drop a bundle folder or script\*.json ONTO this render.bat (multiple OK)
REM    [copy-and-run A] copy THIS FILE into a book root (next to its 05\), double-click.
REM    [copy-and-run B] or copy 05\<bundle> folders into  work\05\  next to this file.
REM
REM  KEEP THIS FILE ASCII-ONLY (commit 7885fff) AND CRLF (.gitattributes).
REM  Non-ASCII bytes break cmd's set/goto parsing; LF breaks byte-offset tracking.
REM  Avoid "!" in folder names: delayed expansion would eat it.
REM
REM  First time once: .venv\Scripts\python -m playwright install chromium
REM  (to preview design fast, just open 05\<bundle>\source\deck.html in a browser)
REM ==========================================================================
setlocal enabledelayedexpansion

REM ---- folder of THIS file, normalized, WITHOUT the trailing backslash ------
REM  "%~dp0" ends with "\" ; passing "D:\x\" as a quoted argument escapes the
REM  closing quote and swallows the next one, so  --book "D:\x\" --round m01
REM  reaches python as a SINGLE argument.  %%~fI normalizes and drops the "\".
for %%I in ("%~dp0.") do set "SELF=%%~fI"

REM ---- mode + repo location ------------------------------------------------
set "REPO="
set "MODE=book"
if exist "%SELF%\make_bundle_video.py" set "MODE=repo"
if "%MODE%"=="repo" set "REPO=%SELF%"
if defined REPO goto :haverepo

if defined CHODANGI_HOME call :trycand "%CHODANGI_HOME%"
for /d %%D in ("%SELF%\..\*chodangi*") do if not defined REPO call :trycand "%%~fD"
if not defined REPO call :trycand "D:\00work\260724-chodangi-mp4"
if defined REPO goto :haverepo

echo [error] chodangi render repo not found.
echo         Tried: %%CHODANGI_HOME%%  ,  %SELF%\..\*chodangi*  ,  D:\00work\260724-chodangi-mp4
echo         A valid repo has BOTH  .venv\Scripts\python.exe  and  make_bundle_video.py
echo         Set it once:   setx CHODANGI_HOME "D:\00work\260724-chodangi-mp4"
echo         then open a NEW cmd window (setx does not affect this one) and retry.
pause & exit /b 1

:haverepo
set "PY=%REPO%\.venv\Scripts\python.exe"
set "DRIVER=%REPO%\make_bundle_video.py"
if not exist "%PY%" (
  echo [error] .venv not found: %PY%
  echo         In %REPO% run: python -m venv .venv
  echo         then: .venv\Scripts\python -m pip install -r requirements-render.txt
  echo         then: .venv\Scripts\python -m playwright install chromium
  pause & exit /b 1
)
cd /d "%REPO%"
echo [mode] %MODE%  repo=%REPO%

REM ---- ffmpeg is fatal for the mux step: fail NOW, not after minutes of TTS -
set "SKIPFF="
for %%A in (%*) do (
  if /i "%%~A"=="--no-audio" set "SKIPFF=1"
  if /i "%%~A"=="--help" set "SKIPFF=1"
  if /i "%%~A"=="-h" set "SKIPFF=1"
)
where /q ffmpeg
if not errorlevel 1 goto :ffok
if defined SKIPFF goto :ffok
echo [error] ffmpeg is not in PATH.
echo         Slides + TTS would run for minutes and then mp4maker WOULD FAIL.
echo         Install:  winget install Gyan.FFmpeg    then open a NEW cmd window.
echo         Slides only (no ffmpeg needed):  render.bat --no-audio
pause & exit /b 1
:ffok

REM ---- book root (the folder that holds the 04/05 stages) -------------------
REM  [book] mode : the book root IS this file's folder.
REM  [repo] mode : keep the old behaviour -- hardcoded default, overridden when
REM                bundles were copied into  work\05\  next to this file.
if "%MODE%"=="repo" goto :bookrepo
set "BOOK=%SELF%"
goto :bookdone
:bookrepo
set "BOOK=D:\00work\ocr-output-260723"
if exist "%SELF%\work\05\" set "BOOK=%SELF%\work"
:bookdone
echo [book] %BOOK%

REM ---- drag-and-drop FIRST: dropped paths carry their own book root ---------
REM  make_bundle_video._resolve_book_round() derives <book>/05/<round> from the
REM  path, so --book is irrelevant here and the "no 05\ here" check must NOT
REM  apply -- you may drop a bundle from any tree onto a copy of this file.
if "%~1"=="" goto :bookcheck
set "A1=%~1"
if "!A1:~0,1!"=="-" goto :bookcheck
REM Decide: dropped PATH (drag) vs ROUND code (typed). Path -> %~1 != %~nx1
if "%~1"=="%~nx1" goto :bookcheck
"%PY%" "%DRIVER%" %*
goto :end

:bookcheck
if "%MODE%"=="repo" goto :dispatch
if exist "%BOOK%\05\" goto :dispatch
echo [error] no 05\ folder next to this file: %BOOK%
echo         This render.bat was copied somewhere that is NOT a book root.
echo         Put it in the folder that CONTAINS 05\ , e.g.
echo             D:\00work\ocr-output-260730\render.bat
echo         and double-click it there.
pause & exit /b 1

:dispatch
if "%~1"=="" goto :all
if "!A1:~0,1!"=="-" goto :allflags
goto :roundmode

:allflags
"%PY%" "%DRIVER%" --book "%BOOK%" %*
goto :end

:roundmode
set "RND=%~1"
shift
set "REST="
:collect
if not "%~1"=="" ( set "REST=!REST! %1" & shift & goto :collect )
"%PY%" "%DRIVER%" --book "%BOOK%" --round "!RND!" !REST!
goto :end

:all
"%PY%" "%DRIVER%" --book "%BOOK%"
goto :end

:end
echo.
echo [done] output: %BOOK%\05\^<bundle^>\draft\^<bundle^>.static.mp4
pause
endlocal
exit /b 0

REM ==========================================================================
REM  :trycand <path>  -- accept a candidate as REPO only if it really is one.
REM  Called from a for /d loop, so it must never fall through into :end.
REM ==========================================================================
:trycand
if "%~1"=="" goto :eof
for %%I in ("%~1\.") do set "C=%%~fI"
if not exist "!C!\make_bundle_video.py" goto :eof
if not exist "!C!\.venv\Scripts\python.exe" goto :eof
set "REPO=!C!"
goto :eof