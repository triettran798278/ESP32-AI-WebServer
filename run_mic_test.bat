@echo off
chcp 65001 >nul
title XiaoZhi Real-Time Voice Assistant (Ranh Tay + Streaming)

echo ====================================================================
echo    KHOI DONG TRO LY GIONG NOI REAL-TIME XIAOZHI (RANH TAY 100%%)
echo ====================================================================
echo.

where py >nul 2>&1
if %ERRORLEVEL% equ 0 (
    py -3 mic_test.py
) else (
    python mic_test.py
)

pause
