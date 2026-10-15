@echo off
chcp 65001 >nul
title مشتركين منصة دبليوشارت تاسي - المنفذ 5002
cd /d "%~dp0"

REM إذا كان الخادم يعمل بالفعل على المنفذ 5002: افتح المتصفح فقط
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 5002 -State Listen -ErrorAction SilentlyContinue) { Start-Process 'http://127.0.0.1:5002'; exit 0 } else { exit 1 }"
if %errorlevel%==0 (
    echo الخادم يعمل بالفعل. تم فتح المتصفح.
    timeout /t 2 >nul
    exit /b
)

echo ============================================================
echo   تشغيل مشروع: مشتركين منصة دبليوشارت تاسي
echo   الرابط: http://127.0.0.1:5002
echo   لا تغلق هذه النافذة أثناء العمل.
echo ============================================================
echo.

REM فتح المتصفح بعد 3 ثوانٍ (مهلة إقلاع الخادم)
start "" /min cmd /c "timeout /t 3 >nul & start "" http://127.0.0.1:5002"

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0app.py"
) else (
    python "%~dp0app.py"
)

echo.
echo توقف الخادم. اضغط أي زر لإغلاق النافذة.
pause >nul
