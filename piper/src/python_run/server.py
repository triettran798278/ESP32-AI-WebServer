import io
import json
import logging
import os
import time
import wave
from pathlib import Path
from typing import Dict, Optional

import onnxruntime
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel

from piper import PiperVoice
from piper.config import PiperConfig
from piper.download import ensure_voice_exists, find_voice, get_voices

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("piper-tts-api")

MODEL_DIR = Path(os.getenv("PIPER_MODEL_DIR", "/models"))
DEFAULT_VOICE = os.getenv("PIPER_DEFAULT_VOICE", "vi_VN-vais1000-medium")
INTRA_THREADS = int(os.getenv("PIPER_INTRA_THREADS", "4"))

VOICE_ALIASES = {
    "vi_VN-25hours-single-low": "vi_VN-25hours_single-low",
    "vi-25hours-single-low": "vi_VN-25hours_single-low",
    "vais1000": "vi_VN-vais1000-medium",
    "25hours": "vi_VN-25hours_single-low",
}
OPENAI_GENERIC_VOICES = {"alloy", "echo", "fable", "onyx", "nova", "shimmer", "default", ""}

app = FastAPI(title="Piper Vietnamese TTS Server (OpenAI & XiaoZhi Compatible)")
_VOICES: Dict[str, PiperVoice] = {}


class OpenAISpeechRequest(BaseModel):
    model: Optional[str] = "tts-1"
    input: str
    voice: Optional[str] = DEFAULT_VOICE
    response_format: Optional[str] = "wav"
    speed: Optional[float] = 1.0


def _resolve_voice_name(requested: Optional[str]) -> str:
    if not requested:
        return DEFAULT_VOICE
    name = requested.strip().removesuffix(".onnx")
    if name.lower() in OPENAI_GENERIC_VOICES:
        return DEFAULT_VOICE
    return VOICE_ALIASES.get(name, name)


def _get_or_load_voice(voice_name: Optional[str] = None) -> PiperVoice:
    resolved = _resolve_voice_name(voice_name)
    if resolved in _VOICES:
        return _VOICES[resolved]

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    onnx_path = MODEL_DIR / f"{resolved}.onnx"
    config_path = MODEL_DIR / f"{resolved}.onnx.json"

    if not (onnx_path.exists() and config_path.exists()):
        logger.info("Voice %s not found in %s, downloading from Hugging Face...", resolved, MODEL_DIR)
        voices_info = get_voices(MODEL_DIR, update_voices=False)
        for v_info in list(voices_info.values()):
            for alias in v_info.get("aliases", []):
                voices_info[alias] = {"_is_alias": True, **v_info}
        if resolved not in voices_info:
            raise HTTPException(status_code=404, detail=f"Unknown Piper voice: {resolved}")
        ensure_voice_exists(resolved, [MODEL_DIR], MODEL_DIR, voices_info)
        onnx_path, config_path = find_voice(resolved, [MODEL_DIR])

    t0 = time.perf_counter()
    with open(config_path, "r", encoding="utf-8") as f:
        config_dict = json.load(f)

    sess_options = onnxruntime.SessionOptions()
    sess_options.intra_op_num_threads = INTRA_THREADS
    sess_options.inter_op_num_threads = 1
    sess_options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL

    voice = PiperVoice(
        config=PiperConfig.from_dict(config_dict),
        session=onnxruntime.InferenceSession(
            str(onnx_path),
            sess_options=sess_options,
            providers=["CPUExecutionProvider"],
        ),
    )
    _VOICES[resolved] = voice
    logger.info("Loaded Piper voice '%s' in %.2fs (threads=%d)", resolved, time.perf_counter() - t0, INTRA_THREADS)
    return voice


def _synthesize_wav(text: str, voice_name: Optional[str] = None, speed: float = 1.0) -> bytes:
    cleaned = text.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Text must not be empty")

    voice = _get_or_load_voice(voice_name)
    length_scale = (voice.config.length_scale / speed) if (speed and speed > 0) else voice.config.length_scale

    t0 = time.perf_counter()
    with io.BytesIO() as wav_io:
        with wave.open(wav_io, "wb") as wav_file:
            voice.synthesize(cleaned, wav_file, length_scale=length_scale)
        wav_bytes = wav_io.getvalue()

    logger.info(
        "Synthesized %d chars (%d bytes WAV) in %.3fs using voice '%s'",
        len(cleaned),
        len(wav_bytes),
        time.perf_counter() - t0,
        _resolve_voice_name(voice_name),
    )
    return wav_bytes


@app.on_event("startup")
def startup_load() -> None:
    try:
        _get_or_load_voice(DEFAULT_VOICE)
    except Exception as exc:
        logger.warning("Deferred preload of default voice %s: %s", DEFAULT_VOICE, exc)


@app.get("/health")
def health():
    available = sorted(p.stem for p in MODEL_DIR.glob("*.onnx")) if MODEL_DIR.exists() else []
    return {
        "status": "ok",
        "default_voice": DEFAULT_VOICE,
        "loaded_voices": list(_VOICES.keys()),
        "available_models_on_disk": available,
        "intra_threads": INTRA_THREADS,
    }


@app.get("/voices")
def list_voices():
    available = sorted(p.stem for p in MODEL_DIR.glob("*.onnx")) if MODEL_DIR.exists() else []
    return {"default": DEFAULT_VOICE, "voices": available}


@app.post("/v1/audio/speech")
def openai_speech(req: OpenAISpeechRequest):
    selected_voice = req.voice if (req.voice and req.voice not in OPENAI_GENERIC_VOICES) else req.model
    wav_bytes = _synthesize_wav(req.input, voice_name=selected_voice, speed=req.speed or 1.0)
    return Response(content=wav_bytes, media_type="audio/wav")


@app.api_route("/tts", methods=["GET", "POST"])
@app.api_route("/", methods=["GET", "POST"])
async def synthesize_endpoint(
    request: Request,
    text: Optional[str] = Query(None),
    voice: Optional[str] = Query(None),
    speed: float = Query(1.0),
):
    if request.method == "POST" and not text:
        body = await request.body()
        raw = body.decode("utf-8").strip()
        if raw.startswith("{"):
            try:
                payload = json.loads(raw)
                text = payload.get("text") or payload.get("input") or ""
                voice = voice or payload.get("voice") or payload.get("model")
                speed = float(payload.get("speed", speed))
            except json.JSONDecodeError:
                text = raw
        else:
            text = raw

    if not text:
        raise HTTPException(status_code=400, detail="Missing 'text' parameter or request body")

    wav_bytes = _synthesize_wav(text, voice_name=voice, speed=speed)
    return Response(content=wav_bytes, media_type="audio/wav")
