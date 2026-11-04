#!/usr/bin/env python3
"""Interactive Mic Test for XiaoZhi AI Pipeline.

Workflow:
  Microphone (Laptop) -> Faster-Whisper (STT) -> Ollama Qwen2.5 (LLM) -> Piper (TTS) -> Speaker (Laptop)
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path

# Native playback on Windows
try:
    import winsound
except ImportError:
    winsound = None

try:
    import sounddevice as sd
except ImportError:
    print("[ERROR] Thư viện 'sounddevice' chưa được cài đặt.")
    print("Vui lòng chạy lệnh: pip install sounddevice")
    sys.exit(1)

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://localhost:8080/v1")
GATEWAY_KEY = os.environ.get("GATEWAY_KEY", "sk-xiaozhi-local-secret")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5:3b-instruct")
TTS_VOICE = os.environ.get("TTS_VOICE", "vi_VN-vais1000-medium")

INPUT_WAV = Path("mic_input.wav")
OUTPUT_WAV = Path("mic_response.wav")
SAMPLE_RATE = 16000  # 16kHz standard for Whisper


def encode_multipart(file_path: Path, fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = f"----XiaoZhiMic{uuid.uuid4().hex}"
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


def record_audio(duration: int = 5) -> Path:
    print(f"\n[Micro] Đang ghi âm ({duration} giây)... Hãy nói vào mic!")
    # Record int16 mono at 16000 Hz
    audio_data = sd.rec(int(duration * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16")
    for sec_left in range(duration, 0, -1):
        print(f"  🎙️ Đang thu... còn {sec_left}s", end="\r", flush=True)
        time.sleep(1)
    sd.wait()
    print("  ✅ Thu âm hoàn tất!                  ")

    with wave.open(str(INPUT_WAV), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_data.tobytes())
    return INPUT_WAV


def stt_transcribe(audio_path: Path) -> tuple[str, float]:
    body, content_type = encode_multipart(
        audio_path,
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


def llm_chat(user_text: str) -> tuple[str, float]:
    payload = json.dumps({
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Bạn là XiaoZhi, trợ lý giọng nói AI tiếng Việt thông minh, thân thiện. "
                    "Hãy trả lời ngắn gọn, tự nhiên trong 1-2 câu để người dùng nghe thuận tiện."
                ),
            },
            {"role": "user", "content": user_text},
        ],
        "stream": False,
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
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    elapsed = time.perf_counter() - t0
    content = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    return content, elapsed


def tts_synthesize(text: str) -> tuple[Path, float]:
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
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=30) as resp:
        wav_bytes = resp.read()
    elapsed = time.perf_counter() - t0

    OUTPUT_WAV.write_bytes(wav_bytes)
    return OUTPUT_WAV, elapsed


def play_audio(wav_path: Path) -> None:
    print("  🔊 Đang phát phản hồi qua loa...")
    if winsound:
        winsound.PlaySound(str(wav_path), winsound.SND_FILENAME)
    else:
        with wave.open(str(wav_path), "rb") as wf:
            frames = wf.readframes(wf.getnframes())
            sd.play(frames, samplerate=wf.getframerate())
            sd.wait()


def main() -> int:
    print("=" * 60)
    print("  🎤 THỬ NGHIỆM TƯƠNG TÁC GIỌNG NÓI XIAOZHI (LAPTOP MIC -> AI)")
    print("=" * 60)
    print(f" * Gateway  : {GATEWAY_URL}")
    print(f" * LLM Model: {LLM_MODEL}")
    print(f" * TTS Voice: {TTS_VOICE}")
    print("-" * 60)

    # Check Gateway health
    try:
        check_req = urllib.request.Request(
            f"{GATEWAY_URL}/models",
            headers={"Authorization": f"Bearer {GATEWAY_KEY}"},
        )
        with urllib.request.urlopen(check_req, timeout=5) as resp:
            pass
        print("[Gateway] Kết nối thành công tới AI Gateway!")
    except Exception as e:
        print(f"[CẢNH BÁO] Không thể kết nối tới Gateway ({e}).")
        print("Hãy chắc chắn lệnh 'docker compose up -d' đã được chạy.")
        return 1

    duration = 5
    is_test_mode = "--test" in sys.argv
    if is_test_mode:
        duration = 2

    while True:
        if is_test_mode:
            print(f"\n[Test Mode] Ghi âm tự động {duration}s để kiểm tra...")
        else:
            prompt_msg = (
                f"\n[?] Nhấn [ENTER] để ghi âm {duration}s | "
                f"Gõ số giây (vd: 7) để đổi thời gian | "
                f"Gõ 'q' để thoát: "
            )
            try:
                user_choice = input(prompt_msg).strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\nĐã thoát.")
                break

            if user_choice == "q":
                print("Tạm biệt!")
                break
            elif user_choice.isdigit() and int(user_choice) > 0:
                duration = min(int(user_choice), 30)
                print(f"-> Đã đặt thời lượng ghi âm: {duration} giây.")

        # 1. Record
        t_total_start = time.perf_counter()
        audio_file = record_audio(duration)

        # 2. STT
        print("  🔄 [STT] Đang nhận diện giọng nói...")
        try:
            user_text, stt_time = stt_transcribe(audio_file)
        except Exception as e:
            print(f"  ❌ Lỗi STT: {e}")
            continue

        if not user_text:
            print("  ⚠️ Không phát hiện giọng nói (hoặc âm lượng quá nhỏ). Hãy thử nói to hơn!")
            if is_test_mode:
                break
            continue

        print(f"  👤 BẠN VỪA NÓI : \"{user_text}\" ({stt_time:.2f}s)")

        # 3. LLM
        print("  🧠 [LLM] Đang suy nghĩ câu trả lời...")
        try:
            ai_reply, llm_time = llm_chat(user_text)
        except Exception as e:
            print(f"  ❌ Lỗi LLM: {e}")
            continue

        print(f"  🤖 XIAOZHI NÓI : \"{ai_reply}\" ({llm_time:.2f}s)")

        # 4. TTS
        print("  🗣️ [TTS] Đang tổng hợp giọng nói...")
        try:
            reply_wav, tts_time = tts_synthesize(ai_reply)
        except Exception as e:
            print(f"  ❌ Lỗi TTS: {e}")
            continue

        total_latency = time.perf_counter() - t_total_start - duration
        print(f"  ⚡ Tổng thời gian xử lý AI (STT+LLM+TTS): {total_latency:.2f}s")

        # 5. Playback
        play_audio(reply_wav)

        if is_test_mode:
            print("\n[Test Mode] Hoàn tất vòng thử nghiệm 1 lần thành công!")
            break


if __name__ == "__main__":
    sys.exit(main())
