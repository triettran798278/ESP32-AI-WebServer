@echo off
title XiaoZhi AI Backend - All-In-One Launcher

echo ================================================================
echo    XIAOZHI FULL-LOCAL AI BACKEND - 1-CLICK ALL-IN-ONE
echo ================================================================
echo.

echo [1/3] Kiem tra Docker Desktop...
docker.exe info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker Engine chua khoi dong!
    echo Vui long mo ung dung Docker Desktop va cho bieu tuong mau xanh - Engine running.
    echo Sau do chay lai file bat nay.
    pause
    exit /b 1
)
echo [OK] Docker Engine dang hoat dong tot.
echo.

echo [2/3] Khoi dong cac Container AI...
docker.exe compose up -d
if errorlevel 1 (
    echo [ERROR] Khong the khoi chay docker compose!
    pause
    exit /b 1
)
echo [OK] 5 Container da online: Ollama, Faster-Whisper, Piper-TTS, MCP-Gateway 8008, Gateway 8080.
echo.

echo [3/3] Kiem tra Model va chay Kiem thu toan trinh...
call init_models.bat
python test_pipeline.py

echo.
pause
