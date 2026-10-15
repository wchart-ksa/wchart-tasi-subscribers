@echo off
chcp 65001 >nul
title Stop Wchart Tasi subscribers app
echo Stopping Wchart Tasi server (port 5002)...
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and $_.CommandLine -like '*almchtrkyn*' }; if ($p) { foreach ($x in $p) { Stop-Process -Id $x.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host ('Stopped PID ' + $x.ProcessId) } } else { Write-Host 'No running server found.' }"
echo.
ping -n 2 127.0.0.1 >nul
