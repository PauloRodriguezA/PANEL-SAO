@echo off
title Cerrar EPA-SAO Entel Total
echo Cerrando EPA-SAO Entel, python EPA.PY y tuneles publicos SSH del puerto 8081...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $c=$_.CommandLine; $c -and ( ($_.Name -ieq 'ssh.exe' -and (($c -match 'serveo\.net') -or ($c -match 'localhost\.run')) -and ($c -match '127\.0\.0\.1:8081' -or $c -match 'localhost:8081')) -or ($_.Name -ieq 'cloudflared.exe' -and ($c -match '127\.0\.0\.1:8081' -or $c -match 'localhost:8081')) -or ($_.Name -match '^(python|pythonw|python3(\.\d+)?)\.exe$' -and $c -match 'EPA\.PY') ) } | ForEach-Object { Write-Host ('Cerrando PID ' + $_.ProcessId + ' ' + $_.Name); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo.
echo Limpieza finalizada.
pause
