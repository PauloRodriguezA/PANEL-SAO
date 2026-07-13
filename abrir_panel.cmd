@echo off
setlocal
cd /d "%~dp0"
title Panel de Adherencia Entel - SAO
set PANEL_SERVICIO_FIJO=SAO
for %%I in ("%~dp0..\..") do set "PROJECT_ROOT=%%~fI"
for %%I in ("%PROJECT_ROOT%\..") do set "PROJECT_PARENT=%%~fI"
set "VENV_DIR=%USERPROFILE%\Documents\Codex\PythonEnvs\PanelAdherencia"
set "PST_CORREO_DIR=C:\Users\artof\OneDrive\Paulo Rodriguez\PYTHON\PST"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
set "STREAMLIT_EXE=%VENV_DIR%\Scripts\streamlit.exe"
if not exist "%PYTHON_EXE%" (
    echo Creando entorno Python local en "%VENV_DIR%"...
    py -3 -m venv "%VENV_DIR%" 2>nul
    if errorlevel 1 (
        python -m venv "%VENV_DIR%"
    )
    if errorlevel 1 (
        echo ERROR: No se pudo crear .venv. Instala Python 3 y vuelve a intentar.
        pause
        exit /b 1
    )
)
if not exist "%STREAMLIT_EXE%" (
    echo Instalando dependencias del panel...
    "%PYTHON_EXE%" -m pip install --upgrade pip
    "%PYTHON_EXE%" -m pip install -r "%PROJECT_ROOT%\requirements.txt"
    if errorlevel 1 (
        echo ERROR: No se pudieron instalar dependencias.
        pause
        exit /b 1
    )
)
echo Iniciando panel SAO en http://127.0.0.1:8503
echo Este panel abre solo local; la publicacion oficial queda en Git.
"%STREAMLIT_EXE%" run "%~dp0panel.py" --server.address 127.0.0.1 --server.port 8503
