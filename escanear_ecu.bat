@echo off
chcp 65001 > nul
title Scanner e Inventario da ECU - Fiesta Zetec Rocam
color 0B

echo ========================================================
echo   Scanner e Auditoria de Diagnostico da ECU Ford
echo   Fiesta 2010 Sedan 1.0 Zetec Rocam
echo ========================================================
echo.

python "%~dp0scanner_inventario_ecu.py"

pause
