@echo off
title Teste de Bancada - CANable V2.1 STM32G431
cd /d "%~dp0"
echo ========================================================
echo   Iniciando Diagnostico de Bancada - CANable V2.1
echo ========================================================
python test_bancada_canable.py
pause
