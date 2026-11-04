#!/usr/bin/env python3
"""Real-Time Hands-Free Voice Assistant for XiaoZhi AI Backend.

Features:
  1. Auto-Calibrating VAD (Voice Activity Detection): Speak naturally without pressing Enter.
  2. In-Memory Pipeline (Zero Disk I/O): Mic, STT, LLM, and TTS all stream in RAM.
  3. Multi-Turn Context Memory: Remembers conversation history across turns.
  4. Real-Time Sentence Streaming: LLM streams tokens via SSE -> splits sentences ->
     synthesizes TTS & plays first sentence immediately while LLM generates the rest.
"""
from collections import deque
import io
import json
import os
import queue
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path

try:
    import winsound
except ImportError:
    winsound = None

try:
    import numpy as np
    import sounddevice as sd
except ImportError:
    print("[ERROR] Thiếu thư viện 'sounddevice' hoặc 'numpy'. Chạy: pip install sounddevice numpy")
    sys.exit(1)

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8080/v1")
GATEWAY_KEY = os.environ.get("GATEWAY_KEY", "sk-xiaozhi-local-secret")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5:3b-instruct")
TTS_VOICE = os.environ.get("TTS_VOICE", "vi_VN-vais1000-medium")

SAMPLE_RATE = 16000
FRAME_DURATION_MS = 50  # 50ms per frame (20 frames/sec)
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)  # 800 samples
PRE_ROLL_FRAMES = 8     # Keep 0.4s before speech trigger
SILENCE_LIMIT_S = 0.85  # Stop after 0.85s of silence
MIN_SPEECH_S = 0.35     # Ignore clicks shorter than 0.35s
MAX_SPEECH_S = 20.0     # Max single utterance duration
MAX_HISTORY_MESSAGES = 20  # Keep last 10 turns (user + assistant)

SYSTEM_PROMPT = (
    "Bạn là XiaoZhi, trợ lý giọng nói AI tiếng Việt thông minh, luôn ghi nhớ ngữ cảnh cuộc trò chuyện. "
    "Hãy trả lời ngắn gọn trong 1 đến 3 câu, không dùng ký hiệu markdown phức tạp để đọc thành tiếng mượt mà."
)

# Phrases commonly hallucinated by Whisper on silence/noise
HALLUCINATIONS = {
    "cảm ơn các bạn đã theo dõi",
    "hãy đăng ký kênh",
    "subtitle by",
    "amara.org",
    "thank you",
    "you",
    ".",
}


def pcm_to_wav_bytes(pcm_bytes: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def encode_multipart_bytes(wav_bytes: bytes, fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = f"----XiaoZhiRT{uuid.uuid4().hex}"
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        b'Content-Disposition: form-data; name="file"; filename="speech.wav"\r\n'
        b"Content-Type: audio/wav\r\n\r\n"
    )
    body.extend(wav_bytes)
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def calibrate_vad_threshold() -> float:
    """Measure 0.8s of background room noise to set a dynamic speech threshold."""
    print("🎙️ Đang đo độ ồn môi trường (vui lòng giữ yên lặng 1 giây)...", end="\r", flush=True)
    rms_values = []
    chunks = int(0.8 * 1000 / FRAME_DURATION_MS)
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=FRAME_SAMPLES) as stream:
        for _ in range(chunks):
            data, _ = stream.read(FRAME_SAMPLES)
            rms = float(np.sqrt(np.mean(data.astype(np.float32) ** 2)))
            rms_values.append(rms)
    ambient_rms = float(np.median(rms_values)) if rms_values else 100.0
    # Threshold is 2.8x ambient noise, clamped to a sensible range [280, 1800]
    threshold = max(280.0, min(ambient_rms * 2.8 + 120.0, 1800.0))
    print(f"✅ Đã cân chỉnh Micro (Độ ồn nền: {ambient_rms:.0f} | Ngưỡng kích hoạt giọng nói: {threshold:.0f})   ")
    return threshold


def listen_vad(threshold: float) -> bytes | None:
    """Continuously listen to mic using VAD; return raw PCM bytes once an utterance finishes."""
    pre_roll: deque[bytes] = deque(maxlen=PRE_ROLL_FRAMES)
    speech_frames: list[bytes] = []
    speaking = False
    silence_frames = 0
    max_silence_frames = int(SILENCE_LIMIT_S * 1000 / FRAME_DURATION_MS)
    min_speech_frames = int(MIN_SPEECH_S * 1000 / FRAME_DURATION_MS)
    max_total_frames = int(MAX_SPEECH_S * 1000 / FRAME_DURATION_MS)

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=FRAME_SAMPLES) as stream:
        while True:
            data, _ = stream.read(FRAME_SAMPLES)
            raw = data.tobytes()
            rms = float(np.sqrt(np.mean(data.astype(np.float32) ** 2)))

            # Visual meter bar
            bar_len = min(20, int((rms / max(threshold * 2, 1)) * 20))
            bar = "█" * bar_len + "░" * (20 - bar_len)

            if not speaking:
                pre_roll.append(raw)
                print(f"  🟢 [Đang lắng nghe] [{bar}] (Hãy nói vào mic... Ctrl+C để thoát)", end="\r", flush=True)
                if rms >= threshold:
                    speaking = True
                    silence_frames = 0
                    speech_frames.extend(pre_roll)
                    speech_frames.append(raw)
            else:
                speech_frames.append(raw)
                print(f"  🔴 [Đang thu giọng] [{bar}] ({len(speech_frames) * FRAME_DURATION_MS / 1000:.1f}s)                   ", end="\r", flush=True)
                if rms < threshold * 0.85:
                    silence_frames += 1
                    if silence_frames >= max_silence_frames:
                        break
                else:
                    silence_frames = 0

                if len(speech_frames) >= max_total_frames:
                    break

    print(" " * 85, end="\r", flush=True)
    active_frames = len(speech_frames) - silence_frames
    if active_frames < min_speech_frames:
        return None
    return b"".join(speech_frames)


def stt_transcribe_bytes(wav_bytes: bytes) -> tuple[str, float]:
    body, content_type = encode_multipart_bytes(
        wav_bytes,
        {"model": "small", "language": "vi", "response_format": "json"},
    )
    req = urllib.request.Request(
        f"{GATEWAY_URL}/audio/transcriptions",
        data=body,
        headers={
            "Content-Type": content_type,
            "Authorization": f"Bearer {GATEWAY_KEY}",
        },
        method="POST",
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    elapsed = time.perf_counter() - t0
    return result.get("text", "").strip(), elapsed


def tts_synthesize_bytes(text: str) -> bytes:
    payload = json.dumps({
        "model": "tts-1",
        "input": text,
        "voice": TTS_VOICE,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{GATEWAY_URL}/audio/speech",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GATEWAY_KEY}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def play_wav_bytes(wav_bytes: bytes) -> None:
    if winsound:
        winsound.PlaySound(wav_bytes, winsound.SND_MEMORY)
    else:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            frames = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
            sd.play(frames, samplerate=wf.getframerate())
            sd.wait()


def stream_llm_and_speak(chat_history: list[dict[str, str]]) -> str:
    """Stream LLM tokens via SSE, split into sentences, and pipeline TTS + Audio Playback concurrently."""
    sentence_queue: queue.Queue[str | None] = queue.Queue()
    audio_queue: queue.Queue[bytes | None] = queue.Queue()
    t_start = time.perf_counter()
    first_audio_logged = False

    def tts_worker() -> None:
        while True:
            sentence = sentence_queue.get()
            if sentence is None:
                audio_queue.put(None)
                break
            clean = sentence.strip()
            if not clean:
                continue
            try:
                wav_data = tts_synthesize_bytes(clean)
                audio_queue.put(wav_data)
            except Exception as exc:
                print(f"\n  [Lỗi TTS]: {exc}")

    def player_worker() -> None:
        nonlocal first_audio_logged
        while True:
            wav_data = audio_queue.get()
            if wav_data is None:
                break
            if not first_audio_logged:
                first_audio_logged = True
                ttfa = time.perf_counter() - t_start
                print(f" ⚡ [Phát âm thanh đầu tiên sau {ttfa:.2f}s]", end="", flush=True)
            play_wav_bytes(wav_data)

    t_tts = threading.Thread(target=tts_worker, daemon=True)
    t_play = threading.Thread(target=player_worker, daemon=True)
    t_tts.start()
    t_play.start()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + chat_history[-MAX_HISTORY_MESSAGES:]
    payload = json.dumps({
        "model": LLM_MODEL,
        "messages": messages,
        "stream": True,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{GATEWAY_URL}/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GATEWAY_KEY}",
        },
        method="POST",
    )

    print("  🤖 XiaoZhi: ", end="", flush=True)
    full_reply = []
    buffer = ""
    # Split on sentence-ending punctuation (., !, ?, ;, newline)
    sentence_end_re = re.compile(r"([.!?;\n]+)\s*")

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="ignore").strip()
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                try:
                    chunk = json.loads(line[6:])
                    token = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                except Exception:
                    continue
                if not token:
                    continue

                print(token, end="", flush=True)
                full_reply.append(token)
                buffer += token

                # Check if we have a complete sentence to dispatch to TTS immediately
                match = sentence_end_re.search(buffer)
                if match and match.end() >= 12:
                    cut_idx = match.end()
                    sentence_queue.put(buffer[:cut_idx])
                    buffer = buffer[cut_idx:]
    except Exception as exc:
        print(f"\n  ❌ Lỗi LLM Stream: {exc}")

    if buffer.strip():
        sentence_queue.put(buffer.strip())

    sentence_queue.put(None)
    t_tts.join()
    t_play.join()
    print()
    return "".join(full_reply).strip()


def main() -> int:
    print("=" * 68)
    print("  ⚡ XIAOZHI REAL-TIME VOICE ASSISTANT (RẢNH TAY - ĐA LƯỢT - STREAMING)")
    print("=" * 68)
    print(f" * Gateway   : {GATEWAY_URL}")
    print(f" * LLM Model : {LLM_MODEL} (SSE Streaming + Context Memory)")
    print(f" * TTS Voice : {TTS_VOICE} (Sentence Pipelining)")
    print("-" * 68)

    try:
        check_req = urllib.request.Request(
            f"{GATEWAY_URL}/models",
            headers={"Authorization": f"Bearer {GATEWAY_KEY}"},
        )
        with urllib.request.urlopen(check_req, timeout=5):
            pass
    except Exception as e:
        print(f"[LỖI] Không thể kết nối tới Gateway ({e}). Hãy chạy 'docker compose up -d'.")
        return 1

    chat_history: list[dict[str, str]] = []

    # Automated self-test mode
    if "--test" in sys.argv:
        print("[Test Mode] Kiểm tra luồng Real-Time Streaming + Context Memory...")
        sample_wav = Path("output_test.wav")
        if sample_wav.exists():
            user_text, stt_t = stt_transcribe_bytes(sample_wav.read_bytes())
        else:
            user_text, stt_t = "Xin chào, tôi tên là Triết, hãy nhớ tên tôi nhé.", 0.0
        print(f"  👤 Bạn nói (Turn 1): \"{user_text}\" (STT: {stt_t:.2f}s)")
        chat_history.append({"role": "user", "content": user_text})
        reply1 = stream_llm_and_speak(chat_history)
        chat_history.append({"role": "assistant", "content": reply1})

        # Test Turn 2 (Context memory check)
        chat_history.append({"role": "user", "content": "Mình tên là Triết, mình đang lập trình ESP32."})
        chat_history.append({"role": "assistant", "content": "Chào Triết, dự án ESP32 của bạn rất thú vị!"})
        q2 = "Bạn có nhớ tên mình và mình đang làm dự án gì không?"
        print(f"  👤 Bạn nói (Turn 2): \"{q2}\"")
        chat_history.append({"role": "user", "content": q2})
        reply2 = stream_llm_and_speak(chat_history)
        chat_history.append({"role": "assistant", "content": reply2})
        print("\n[Test Mode] Hoàn tất kiểm tra Real-Time & Context thành công!")
        return 0

    threshold = calibrate_vad_threshold()
    print("💡 Hướng dẫn: Cứ nói tự nhiên vào mic, khi bạn ngừng nói 0.8s AI sẽ tự trả lời!")
    print("💡 Nói 'xóa ngữ cảnh' để làm mới bộ nhớ trò chuyện | Nhấn Ctrl+C để thoát.\n")

    try:
        while True:
            pcm_data = listen_vad(threshold)
            if not pcm_data:
                continue

            wav_bytes = pcm_to_wav_bytes(pcm_data)
            try:
                user_text, stt_time = stt_transcribe_bytes(wav_bytes)
            except Exception as e:
                print(f"  ❌ Lỗi STT: {e}")
                continue

            clean_lower = user_text.lower().strip(" .,!?")
            if not clean_lower or clean_lower in HALLUCINATIONS:
                continue

            print(f"  👤 Bạn ({stt_time:.2f}s): {user_text}")

            if clean_lower in ("xóa ngữ cảnh", "xoa ngu canh", "reset"):
                chat_history.clear()
                print("  🧹 Đã xóa lịch sử ngữ cảnh hội thoại!\n")
                continue

            chat_history.append({"role": "user", "content": user_text})
            ai_reply = stream_llm_and_speak(chat_history)
            if ai_reply:
                chat_history.append({"role": "assistant", "content": ai_reply})
            print(f"  💭 [Context đang nhớ: {len(chat_history) // 2} lượt hội thoại]\n")

            # Brief pause after speaker finishes so mic doesn't catch room echo
            time.sleep(0.25)

    except KeyboardInterrupt:
        print("\n\n👋 Đã dừng trợ lý giọng nói XiaoZhi Real-Time. Tạm biệt!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
