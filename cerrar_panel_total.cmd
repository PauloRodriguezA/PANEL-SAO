@echo off
title Cerrar Panel Entel Connect
echo Cerrando procesos Streamlit/Python asociados al panel...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $c=$_.CommandLine; $n=$_.Name; $c -and ($n -match '^(streamlit|python|pythonw|python3\.13)\.exe$') -and ($c -match 'streamlit') -and ($c -match 'panel\.py' -or $c -match '--server\.port 8501') } | ForEach-Object { Write-Host ('Cerrando PID ' + $_.ProcessId + ' ' + $_.Name); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo Listo.
pause
