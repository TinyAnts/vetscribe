@echo off
setlocal
cd /d "%~dp0"

REM ===== VetScribe one-click launcher (Windows) =====

REM 1) make sure the key was pasted (only if a .env exists)
if exist .env (
  findstr /C:"PASTE_YOUR_KEY_HERE" .env >nul 2>&1
  if %errorlevel%==0 (
    echo.
    echo  !! You have not pasted your key yet.
    echo  !! Open the file ".env", replace PASTE_YOUR_KEY_HERE with your OpenAI key, SAVE, run again.
    echo  !! ^(Or leave .env out and paste your key in the app's key field once it opens.^)
    echo.
    pause
  )
)

REM 2) build an ISOLATED environment outside OneDrive and outside the broken
REM    system Scripts folder. This avoids the websockets.exe install error.
set "VENV=%LOCALAPPDATA%\vetscribe-venv"
if not exist "%VENV%\Scripts\python.exe" (
  echo Creating isolated environment ^(first run only, ~30s^)...
  python -m venv "%VENV%"
)
set "PY=%VENV%\Scripts\python.exe"

if not exist "%PY%" (
  echo.
  echo  !! Could not create the environment. Is Python installed and on PATH?
  echo  !! Install Python 3.11+ from python.org, tick "Add to PATH", then run again.
  echo.
  pause
  exit /b
)

REM 3) install dependencies into the clean environment
echo Installing dependencies into the isolated environment...
"%PY%" -m pip install --upgrade pip
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo  !! Dependency install failed. Scroll up, copy the red ERROR line, send it to me.
  echo.
  pause
  exit /b
)

REM 4) launch the app
echo.
echo Launching VetScribe. When you see:  Running on local URL:  http://127.0.0.1:7860
echo open that address in your browser. Close this window to stop.
echo.
"%PY%" app.py
pause
