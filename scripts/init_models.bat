@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0.."

set "PIPER_DIR=piper-models"
set "WHISPER_DIR=whisper-models"
set "HF_BASE=https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"

if not exist "%PIPER_DIR%" mkdir "%PIPER_DIR%"
if not exist "%WHISPER_DIR%" mkdir "%WHISPER_DIR%"

echo === [1/3] Downloading Vietnamese Piper TTS Models ===
call :download "%HF_BASE%/vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium.onnx" "%PIPER_DIR%\vi_VN-vais1000-medium.onnx"
call :download "%HF_BASE%/vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium.onnx.json" "%PIPER_DIR%\vi_VN-vais1000-medium.onnx.json"
call :download "%HF_BASE%/vi/vi_VN/25hours_single/low/vi_VN-25hours_single-low.onnx" "%PIPER_DIR%\vi_VN-25hours_single-low.onnx"
call :download "%HF_BASE%/vi/vi_VN/25hours_single/low/vi_VN-25hours_single-low.onnx.json" "%PIPER_DIR%\vi_VN-25hours_single-low.onnx.json"

echo.
echo === [2/3] Pulling Ollama LLM (qwen2.5:3b-instruct) ===
docker exec ollama ollama pull qwen2.5:3b-instruct
if errorlevel 1 (
    echo [ERROR] Failed to pull qwen2.5:3b-instruct. Make sure container 'ollama' is running ^(docker compose up -d^).
    exit /b 1
)

echo.
echo === [3/3] Ensuring Faster-Whisper (small, int8) is cached in ./whisper-models ===
docker exec faster-whisper python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8', download_root='/models')"
if errorlevel 1 (
    echo [ERROR] Failed to initialize Faster-Whisper model. Make sure container 'faster-whisper' is running.
    exit /b 1
)

echo.
echo === All models initialized successfully! ===
exit /b 0

:download
set "URL=%~1"
set "DEST=%~2"
if exist "%DEST%" (
    for %%A in ("%DEST%") do if %%~zA GTR 0 (
        echo [SKIP] Already exists: %DEST%
        exit /b 0
    )
)
echo [DOWN] Downloading %DEST% ...
curl.exe -fL "%URL%" -o "%DEST%"
if errorlevel 1 (
    echo [ERROR] Failed to download %URL%
    exit /b 1
)
exit /b 0
