@echo off
chcp 65001 >nul
title Thu am va Test XiaoZhi AI Pipeline

echo ==========================================================
echo    KHOI DONG THU AM LAPTOP DE TEST HE THONG XIAOZHI AI
echo ==========================================================
echo.

where py >nul 2>&1
if %ERRORLEVEL% equ 0 (
    py -3 mic_test.py
) else (
    python mic_test.py
)

pause
