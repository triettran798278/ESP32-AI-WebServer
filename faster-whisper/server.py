import io
import logging
import os
import time
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from faster_whisper import WhisperModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("faster-whisper-api")

MODEL_NAME = os.getenv("WHISPER_MODEL", "small")
COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
CPU_THREADS = int(os.getenv("WHISPER_CPU_THREADS", "4"))
DEFAULT_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "vi").strip()
VAD_FILTER = os.getenv("WHISPER_VAD_FILTER", "true").lower() in ("1", "true", "yes")
DOWNLOAD_ROOT = os.getenv("WHISPER_MODEL_DIR", "/models")

app = FastAPI(title="Faster-Whisper OpenAI-Compatible STT Server")
model: Optional[WhisperModel] = None


@app.on_event("startup")
def load_model() -> None:
    global model
    os.makedirs(DOWNLOAD_ROOT, exist_ok=True)
    logger.info(
        "Loading WhisperModel(model=%s, device=%s, compute_type=%s, cpu_threads=%d, root=%s)",
        MODEL_NAME,
        DEVICE,
        COMPUTE_TYPE,
        CPU_THREADS,
        DOWNLOAD_ROOT,
    )
    t0 = time.perf_counter()
    model = WhisperModel(
        MODEL_NAME,
        device=DEVICE,
        compute_type=COMPUTE_TYPE,
        cpu_threads=CPU_THREADS,
        download_root=DOWNLOAD_ROOT,
    )
    logger.info("WhisperModel loaded in %.2fs", time.perf_counter() - t0)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "device": DEVICE,
        "compute_type": COMPUTE_TYPE,
        "cpu_threads": CPU_THREADS,
        "default_language": DEFAULT_LANGUAGE or "auto",
        "vad_filter": VAD_FILTER,
    }


@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": MODEL_NAME,
                "object": "model",
                "owned_by": "faster-whisper-local",
            }
        ],
    }


@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    model_name: Optional[str] = Form(None, alias="model"),
    language: Optional[str] = Form(None),
    prompt: Optional[str] = Form(None),
    response_format: str = Form("json"),
    temperature: float = Form(0.0),
):
    if model is None:
        raise HTTPException(status_code=503, detail="Whisper model is not loaded yet")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    lang = (language if language is not None else DEFAULT_LANGUAGE).strip()
    if not lang or lang.lower() == "auto":
        lang = None

    t0 = time.perf_counter()
    segments, info = model.transcribe(
        io.BytesIO(audio_bytes),
        language=lang,
        initial_prompt=prompt,
        vad_filter=VAD_FILTER,
        beam_size=5,
        temperature=temperature,
    )
    segment_list = list(segments)
    text = " ".join(seg.text.strip() for seg in segment_list if seg.text.strip())
    elapsed = time.perf_counter() - t0

    logger.info(
        "Transcribed %.2fs audio in %.2fs (lang=%s): %s",
        info.duration,
        elapsed,
        info.language,
        text,
    )

    if response_format == "text":
        return PlainTextResponse(text)
    if response_format == "verbose_json":
        return {
            "task": "transcribe",
            "language": info.language,
            "duration": info.duration,
            "text": text,
            "segments": [
                {"id": s.id, "start": s.start, "end": s.end, "text": s.text.strip()}
                for s in segment_list
            ],
        }
    return {"text": text}
