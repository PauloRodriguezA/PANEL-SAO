@echo off
title Limpiar carpeta EPA Entel
echo Cerrando procesos antes de limpiar...
call "%~dp0CERRAR_EPA_TOTAL.cmd"
cd /d "%~dp0"
echo.
echo Eliminando archivos duplicados/basura de Windows...
del /q "EPA(*).PY" 2>nul
del /q "Abrir_EPA_Entel_PUBLICO_V4(*).cmd" 2>nul
del /q "Abrir_EPA_Entel_PUBLICO_V4(*).ps1" 2>nul
del /q "epa_entel(*).sqlite3" 2>nul
del /q "logo_entel_transparente(*).png" 2>nul
del /q "torre_entel_lateral_opaca(*).png" 2>nul
del /q "README*.md" 2>nul
del /q "requirements*.txt" 2>nul
del /q ".gitignore*" 2>nul
del /q "EPA_ENTEL*.zip" 2>nul
echo.
echo Quedaron solo archivos operativos del paquete V7.
pause
