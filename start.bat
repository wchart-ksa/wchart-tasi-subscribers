@echo off
title Wchart Tasi - Subscribers (port 5002)
cd /d "%~dp0"

REM If server already running on 5002, just open the browser
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 5002 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if %errorlevel%==0 (
    start "" http://127.0.0.1:5002
    echo Server is already running. Browser opened: http://127.0.0.1:5002
    timeout /t 2 >nul
    exit /b
)

echo ============================================================
echo   Wchart Tasi - Subscribers
echo   URL after start: http://127.0.0.1:5002
echo   Do NOT close this window while using the site.
echo ============================================================
echo.

REM Open the browser after 3 seconds (server boot time)
start "" /min cmd /c "timeout /t 3 >nul & explorer http://127.0.0.1:5002"

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0app.py"
) else (
    python "%~dp0app.py"
)

echo.
echo Server stopped. Press any key to close this window.
pause >nul
