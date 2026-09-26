@echo off
cd /d "%~dp0"

set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
if not exist "%PY%" set "PY=%LocalAppData%\Programs\Python\Launcher\py.exe"
if not exist "%PY%" (
  echo Python is not installed.
  echo Install it from https://www.python.org/downloads/ then open this file again.
  pause
  exit /b 1
)

set "URL=http://127.0.0.1:8765/customs-calculator.html"
set "BROWSER=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%BROWSER%" set "BROWSER=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not exist "%BROWSER%" set "BROWSER=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"

if exist "%BROWSER%" (
  start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 1; Start-Process -FilePath '%BROWSER%' -ArgumentList '%URL%'"
) else (
  start "" "%URL%"
)

"%PY%" "%~dp0server.py"
if errorlevel 1 (
  echo.
  echo The calculator did not stay running. Close any previous calculator window, then open this file again.
  pause
)
