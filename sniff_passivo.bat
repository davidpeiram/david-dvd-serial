@echo off
chcp 65001 > nul
title Sniffer Passivo CAN - Fiesta Zetec Rocam
color 0E

echo ========================================================
echo   Sniffer Passivo de Barramento CAN Ford Fiesta 1.0
echo   Escuta Passiva (Zero Risco / Zero Emissao de Mensagens)
echo ========================================================
echo.

python "%~dp0sniff_passivo_fiesta.py"

pause
