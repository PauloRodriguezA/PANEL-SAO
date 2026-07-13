@echo off
title EPA-SAO Entel Publico
cd /d "%~dp0"
set "EPA_DIR=%CD%"
echo ==============================================
echo  EPA-SAO Entel - modo publico
echo ==============================================
echo.
if not exist "%~dp0..\publicar_epa_resiliente.ps1" (
    echo ERROR: No encuentro publicar_epa_resiliente.ps1
    echo Debe estar en la carpeta raiz del panel.
    echo.
    pause
    exit /b 1
)
if not exist "EPA.PY" (
    echo ERROR: No encuentro EPA.PY en esta carpeta.
    echo Copia este CMD y el PS1 en la carpeta donde esta EPA.PY.
    echo.
    pause
    exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -NoExit -File "%~dp0..\publicar_epa_resiliente.ps1" -Provider "SAO" -Port 8081 -EpaDir "%EPA_DIR%" -DbName "epa_entel_sao.sqlite3" -CatalogName "SAO_2026.xlsx"
pause
