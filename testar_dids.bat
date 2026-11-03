@echo off
chcp 65001 > nul
title Scanner UDS Ford Service 22 - Fiesta Zetec Rocam
color 0B

echo ========================================================
echo   Scanner UDS Ford Service 22 - DIDs Propriatarios
echo   Ford Fiesta 2010 Sedan 1.0 Flex Zetec Rocam
echo ========================================================
echo.
echo Requisito: Chave do carro ligada na posicao II (KOEO)
echo            ou motor funcionando.
echo.

python "%~dp0testar_dids_fiesta.py"

pause
