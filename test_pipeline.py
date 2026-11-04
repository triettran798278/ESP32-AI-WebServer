#!/usr/bin/env python3
"""Integration test for the Full-Local XiaoZhi AI Backend (Ollama + Piper TTS + Faster-Whisper STT)."""
import json
import socket
import sys
import time
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:3b-instruct"
PIPER_URL = "http://localhost:10200/v1/audio/speech"
PIPER_VOICE = "vi_VN-vais1000-medium"
WHISPER_URL = "http://localhost:8000/v1/audio/transcriptions"
GATEWAY_URL = "http://localhost:8080/v1/models"
GATEWAY_KEY = "sk-xiaozhi-local-secret"
OUTPUT_WAV = Path("output_test.wav")

TEST_PROMPT = "Trả lời ngắn gọn trong 1 câu bằng tiếng Việt: Thủ đô của Việt Nam là gì?"
TEST_TTS_TEXT = "Xin chào, hệ thống trợ lý giọng nói trí tuệ nhân tạo đã sẵn sàng hoạt động."


def get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def test_ollama() -> None:
    print(f"\n[1/4] Testing Ollama LLM ({OLLAMA_MODEL}) at {OLLAMA_URL} ...")
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": TEST_PROMPT,
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    wall_time = time.perf_counter() - t0

    reply = data.get("response", "").strip()
    eval_count = data.get("eval_count", 0)
    eval_duration_ns = data.get("eval_duration", 0)
    tok_per_sec = (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns > 0 else (eval_count / wall_time if wall_time > 0 else 0.0)

    assert reply, "Ollama returned an empty response"
    print(f"  -> Prompt   : {TEST_PROMPT}")
    print(f"  -> Response : {reply}")
    print(f"  -> Speed    : {tok_per_sec:.2f} tokens/s ({eval_count} tokens, wall time {wall_time:.2f}s)")


def test_piper_tts() -> Path:
    print(f"\n[2/4] Testing Piper TTS ({PIPER_VOICE}) at {PIPER_URL} ...")
    payload = json.dumps({
        "model": "tts-1",
        "input": TEST_TTS_TEXT,
        "voice": PIPER_VOICE,
    }).encode("utf-8")

    req = urllib.request.Request(
        PIPER_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=60) as resp:
        wav_bytes = resp.read()
    elapsed = time.perf_counter() - t0

    OUTPUT_WAV.write_bytes(wav_bytes)
    assert OUTPUT_WAV.stat().st_size > 1000, "Generated WAV file is unexpectedly small"

    with wave.open(str(OUTPUT_WAV), "rb") as wf:
        duration = wf.getnframes() / float(wf.getframerate())
        sample_rate = wf.getframerate()

    print(f"  -> Input    : {TEST_TTS_TEXT}")
    print(f"  -> Saved    : {OUTPUT_WAV.resolve()} ({len(wav_bytes)} bytes, {sample_rate}Hz, {duration:.2f}s audio)")
    print(f"  -> Latency  : {elapsed:.3f}s (RTF: {elapsed / duration:.3f}x)")
    return OUTPUT_WAV


def _encode_multipart(file_path: Path, fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = f"----XiaoZhiBoundary{uuid.uuid4().hex}"
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
        f"Content-Type: audio/wav\r\n\r\n".encode()
    )
    body.extend(file_path.read_bytes())
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def test_faster_whisper(audio_path: Path) -> None:
    print(f"\n[3/4] Testing Faster-Whisper STT at {WHISPER_URL} with {audio_path.name} ...")
    body, content_type = _encode_multipart(
        audio_path,
        {"model": "small", "language": "vi", "response_format": "json"},
    )
    req = urllib.request.Request(
        WHISPER_URL,
        data=body,
        headers={"Content-Type": content_type},
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    elapsed = time.perf_counter() - t0

    text = result.get("text", "").strip()
    assert text, "Faster-Whisper returned empty transcription"
    print(f"  -> Recognized Text : {text}")
    print(f"  -> Latency         : {elapsed:.3f}s")


def test_gateway() -> None:
    print(f"\n[4/4] Testing Unified AI Gateway (Port 8080) with API Key ...")
    req = urllib.request.Request(
        GATEWAY_URL,
        headers={"Authorization": f"Bearer {GATEWAY_KEY}"},
        method="GET",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    elapsed = time.perf_counter() - t0
    models = [m.get("id") for m in data.get("data", [])]
    print(f"  -> Gateway Auth    : OK (Models: {', '.join(models)})")
    print(f"  -> Latency         : {elapsed:.3f}s")


def main() -> int:
    print("=== XiaoZhi Full-Local AI Backend Pipeline Test ===")
    try:
        test_ollama()
        wav_path = test_piper_tts()
        test_faster_whisper(wav_path)
        test_gateway()
    except urllib.error.URLError as exc:
        print(f"\n[FAIL] Connection error: {exc}", file=sys.stderr)
        print("Hint: Ensure containers are running ('docker compose up -d') and 'init_models' has finished.", file=sys.stderr)
        return 1
    except AssertionError as exc:
        print(f"\n[FAIL] Assertion failed: {exc}", file=sys.stderr)
        return 1

    lan_ip = get_lan_ip()
    print("\n" + "=" * 64)
    print("   HE THONG AI FULL-LOCAL DA SAN SANG PHUC VU 24/7!")
    print("=" * 64)
    print(f" * IP mang LAN cua May A nay : {lan_ip}")
    print(f" * Cua ngo Gateway tap trung : http://{lan_ip}:8080/v1")
    print(f" * API Key xac thuc          : {GATEWAY_KEY}")
    print("\n -- CAU HINH DAN VAO config.yaml TREN MAY B (LINUX) --")
    print(f" ASR base_url : http://{lan_ip}:8080/v1")
    print(f" LLM base_url : http://{lan_ip}:8080/v1")
    print(f" TTS api_url  : http://{lan_ip}:8080/v1/audio/speech")
    print(f" api_key      : {GATEWAY_KEY}")
    print("=" * 64 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
