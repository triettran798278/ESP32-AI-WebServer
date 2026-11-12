#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

PIPER_DIR="./piper-models"
WHISPER_DIR="./whisper-models"
HF_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"

mkdir -p "$PIPER_DIR" "$WHISPER_DIR"

download_if_missing() {
    local url="$1"
    local dest="$2"
    if [ -s "$dest" ]; then
        echo "[SKIP] Already exists: $dest"
    else
        echo "[DOWN] Downloading $dest ..."
        curl -fL "$url" -o "$dest"
    fi
}

echo "=== [1/3] Downloading Vietnamese Piper TTS Models ==="
download_if_missing "$HF_BASE/vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium.onnx" "$PIPER_DIR/vi_VN-vais1000-medium.onnx"
download_if_missing "$HF_BASE/vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium.onnx.json" "$PIPER_DIR/vi_VN-vais1000-medium.onnx.json"
download_if_missing "$HF_BASE/vi/vi_VN/25hours_single/low/vi_VN-25hours_single-low.onnx" "$PIPER_DIR/vi_VN-25hours_single-low.onnx"
download_if_missing "$HF_BASE/vi/vi_VN/25hours_single/low/vi_VN-25hours_single-low.onnx.json" "$PIPER_DIR/vi_VN-25hours_single-low.onnx.json"

echo "=== [2/3] Pulling Ollama LLM (qwen2.5:3b-instruct) ==="
docker exec ollama ollama pull qwen2.5:3b-instruct

echo "=== [3/3] Ensuring Faster-Whisper (small, int8) is cached in ./whisper-models ==="
docker exec faster-whisper python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8', download_root='/models')"

echo "=== All models initialized successfully! ==="
