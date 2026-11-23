"""
Platform Integration Bridge for XiaoZhi ESP32 Server.
Provides the upstream manager-api endpoints, resolves Agent Profiles dynamically,
and coordinates ThingsBoard MCP integration.
"""

import asyncio
from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import logging
import secrets
import uuid
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, status
from starlette.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .store import PlatformStore, platform_store, normalize_mac
from .accounts import AccountStore, bootstrap_from_env
from . import agent_api_tools, tool_pipeline
from .dashboard_integration import router as dashboard_router
try:
    from .device_db import device_db
except ImportError:
    from device_db import device_db

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("platform_bridge")

SECRET_KEY = os.getenv("BRIDGE_SECRET", "").strip()

# Internal service URLs
WHISPER_URL = os.getenv("WHISPER_URL", "http://faster-whisper:8000/v1/audio/transcriptions")
PIPER_URL = os.getenv("PIPER_URL", "http://piper-tts:10200/v1/audio/speech")
LLM_GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "http://mcp-gateway:8008/v1")
WS_PUBLIC_PORT = int(os.getenv("WS_PUBLIC_PORT", "8005"))
HOST_IP = os.getenv("HOST_IP", "localhost")
PUBLIC_WS_URL = os.getenv('PUBLIC_WS_URL', f'ws://{HOST_IP}:{WS_PUBLIC_PORT}/xiaozhi/v1/')
PUBLIC_OTA_URL = os.getenv('PUBLIC_OTA_URL', f'http://{HOST_IP}:8005/xiaozhi/ota/')

accounts = AccountStore()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    bootstrap_from_env(accounts)
    yield


app = FastAPI(title="XiaoZhi Platform Management Bridge", version="1.0.0", lifespan=lifespan)
app.include_router(dashboard_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware('http')
async def protect_pending_management_routes(request: Request, call_next):
    path = request.url.path
    pending = (path in {'/api/devices/bind',
                        }
               or path.startswith('/api/native-dashboards'))
    if pending:
        try:
            console_user(request.headers.get('authorization'))
        except HTTPException:
            return JSONResponse({'detail': 'Invalid or expired session'}, status_code=401)
        return JSONResponse({'detail': 'This feature is temporarily unavailable'}, status_code=503)
    return await call_next(request)


# Mount Built AI Agent Management Console (Alpha 0.1)
CONSOLE_DIST_DIR = Path(__file__).resolve().parent / "console_dist"
if not CONSOLE_DIST_DIR.exists():
    CONSOLE_DIST_DIR = Path(__file__).resolve().parent.parent / "xiaozhi-console" / "dist"

if CONSOLE_DIST_DIR.exists():
    assets_dir = CONSOLE_DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="console_assets")
    app.mount("/console", StaticFiles(directory=str(CONSOLE_DIST_DIR), html=True), name="console")


@app.get("/logo.svg")
async def get_logo():
    if CONSOLE_DIST_DIR.exists():
        from fastapi.responses import FileResponse
        logo_path = CONSOLE_DIST_DIR / "logo.svg"
        if logo_path.exists():
            return FileResponse(str(logo_path), media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="logo.svg not found")


@app.get("/favicon.svg")
async def get_favicon():
    if CONSOLE_DIST_DIR.exists():
        from fastapi.responses import FileResponse
        fav_path = CONSOLE_DIST_DIR / "favicon.svg"
        if fav_path.exists():
            return FileResponse(str(fav_path), media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="favicon.svg not found")


@app.get("/")
async def root_index():
    if CONSOLE_DIST_DIR.exists():
        from fastapi.responses import FileResponse
        index_file = CONSOLE_DIST_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
    return RedirectResponse(url="/test/test_page.html")


def verify_secret(authorization: Optional[str] = Header(None)):
    token = authorization[7:].strip() if authorization and authorization.startswith('Bearer ') else ''
    if not SECRET_KEY or not secrets.compare_digest(token, SECRET_KEY):
        raise HTTPException(status_code=401, detail='Invalid service credential')


# ==============================================================================
# 1. XiaoZhi manager-api Contract Endpoints (read_config_from_api: true)
# ==============================================================================

@app.post("/xiaozhi/config/server-base", dependencies=[Depends(verify_secret)])
@app.post("/config/server-base", dependencies=[Depends(verify_secret)])
async def get_server_base_config():
    """Returns the baseline service configuration for ASR, TTS, VAD, and LLM."""
    logger.info("Serving /config/server-base to XiaoZhi runtime")
    return {
        "code": 0,
        "msg": "success",
        "data": {
            "server": {
                "ip": "0.0.0.0",
                "port": 8002,
                "http_port": 8003,
                "auth": {"enabled": False},
                "vision_explain": "http://127.0.0.1:8003/mcp/vision/explain"
            },
            "log": {
                "log_format": "<green>{time:YYMMDD HH:mm:ss}</green>[{version}_{selected_module}][<light-blue>{extra[tag]}</light-blue>]-<level>{level}</level>-<light-green>{message}</light-green>",
                "log_format_file": "{time:YYYY-MM-DD HH:mm:ss} - {version}_{selected_module} - {name} - {level} - {extra[tag]} - {message}",
                "log_level": "INFO",
                "log_dir": "tmp",
                "log_file": "server.log",
                "data_dir": "data"
            },
            "xiaozhi": {
                "type": "hello",
                "version": 1,
                "transport": "websocket",
                "audio_params": {
                    "format": "opus",
                    "sample_rate": 16000,
                    "channels": 1,
                    "frame_duration": 60
                }
            },
            "delete_audio": True,
            "close_connection_no_voice_time": 120,
            "tts_timeout": 15,
            "enable_wakeup_words_response_cache": False,
            "enable_greeting": False,
            "enable_stop_tts_notify": False,
            "enable_websocket_ping": True,
            "tts_audio_send_delay": 50,
            "exit_commands": ["退出", "再见", "拜拜", "stop", "exit", "quit"],
            "prompt_template": "agent-base-prompt.txt",
            "selected_module": {
                "VAD": "SileroVAD",
                "ASR": "OpenAIAudioASR",
                "LLM": "OpenAILLM",
                "TTS": "OpenAITTS",
                "Memory": "nomem",
                "Intent": "Intent_nointent"
            },
            "VAD": {
                "SileroVAD": {
                    "type": "silero",
                    "model_dir": "models/snakers4_silero-vad",
                    "threshold": 0.5,
                    "threshold_low": 0.2,
                    "min_silence_duration_ms": 1000
                }
            },
            "ASR": {
                "OpenAIAudioASR": {
                    "type": "openai",
                    "base_url": WHISPER_URL,
                    "api_key": "sk-local",
                    "model_name": "small",
                    "output_dir": "tmp/"
                }
            },
            "TTS": {
                "OpenAITTS": {
                    "type": "openai",
                    "api_url": PIPER_URL,
                    "api_key": "sk-local",
                    "model": "tts-1",
                    "voice": "vi_VN-vais1000-medium",
                    "output_dir": "tmp/"
                }
            },
            "LLM": {
                "OpenAILLM": {
                    "type": "openai",
                    "base_url": LLM_GATEWAY_URL,
                    "api_key": os.getenv("API_KEY", ""),
                    "model_name": "qwen2.5:3b-instruct"
                }
            },
            "Memory": {
                "nomem": {
                    "type": "nomem"
                }
            },
            "Intent": {
                "Intent_nointent": {
                    "type": "nointent"
                }
            }
        }
    }


def response_prompt(agent: Dict[str, Any], prompt: str) -> str:
    language = {"en": "English", "vi": "Vietnamese"}.get(agent.get("language"), "Vietnamese")
    return (f"{prompt}\n\nRespond in {language}. This response language takes precedence "
            "over conflicting persona instructions, unless the user explicitly requests another language.")


class AgentModelsRequest(BaseModel):
    macAddress: Optional[str] = None
    clientId: Optional[str] = None
    selectedModule: Optional[Dict[str, Any]] = None


@app.post("/xiaozhi/config/agent-models", dependencies=[Depends(verify_secret)])
@app.post("/config/agent-models", dependencies=[Depends(verify_secret)])
async def get_agent_models(req: AgentModelsRequest):
    """
    Resolves the active Agent Profile and ThingsBoard context for the connecting device.
    Matches the incoming MAC address to the platform's Agent Profile.
    """
    mac = req.macAddress or req.clientId or "default"
    logger.info("Resolving agent models for MAC: %s (client_id: %s)", mac, req.clientId)

    device = device_db.get_device_by_mac(normalize_mac(mac))
    agent = accounts.get_agent_by_id(device['agent_id']) if device else None
    if not agent:
        return {"code": 10041, "msg": f"Device {mac} not registered"}

    prompt = response_prompt(agent, agent.get("prompt", ""))
    tts_voice = agent.get("tts", {}).get("voice", "vi_VN-vais1000-medium")
    if tts_voice in ("vi_female_linh", "female", "male", "default", "standard"):
        tts_voice = "vi_VN-vais1000-medium"
    agent_model = agent.get("llm", {}).get("model", "qwen2.5:3b-instruct")

    return {
        "code": 0,
        "msg": "success",
        "data": {
            "agent_id": agent.get("id"),
            "role": agent.get("role"),
            "tool_policy": agent.get("tool_policy", "full_control"),
            "prompt": prompt,
            "TTS": {
                "OpenAITTS": {
                    "type": "openai",
                    "api_url": PIPER_URL,
                    "api_key": "sk-local",
                    "model": "tts-1",
                    "voice": tts_voice,
                    "output_dir": "tmp/"
                }
            },
            "LLM": {
                "OpenAILLM": {
                    "type": "openai",
                    "base_url": f"{os.getenv('BRIDGE_INTERNAL_URL', 'http://platform-bridge:8005').rstrip('/')}/api/agents/{agent['id']}/v1",
                    "api_key": SECRET_KEY,
                    "model_name": agent_model
                }
            },
            "selected_module": {
                "TTS": "OpenAITTS",
                "LLM": "OpenAILLM"
            },
            "chat_history_conf": 1
        }
    }


class ChatReportRequest(BaseModel):
    macAddress: Optional[str] = None
    sessionId: Optional[str] = None
    chatType: Optional[int] = None  # 1 = user, 2 = assistant
    content: Optional[str] = None
    reportTime: Optional[Any] = None
    audioBase64: Optional[str] = None


@app.post("/xiaozhi/agent/chat-history/report", dependencies=[Depends(verify_secret)])
@app.post("/agent/chat-history/report", dependencies=[Depends(verify_secret)])
async def report_chat_history(req: ChatReportRequest):
    """Stores conversation transcript chunks reported by the XiaoZhi runtime."""
    if req.macAddress and req.content:
        mac = normalize_mac(req.macAddress)
        device = device_db.get_device_by_mac(mac)
        if device:
            accounts.append_chat(device['agent_id'], {
                'session_id': req.sessionId or 'default_session', 'mac': mac,
                'role': 'assistant' if req.chatType == 2 else 'user',
                'content': req.content, 'timestamp': int(time.time()),
            })
    return {"code": 0, "msg": "success"}


@app.post("/xiaozhi/agent/chat-summary/{session_id}/save")
@app.post("/agent/chat-summary/{session_id}/save")
async def save_chat_summary(session_id: str):
    return {"code": 0, "msg": "success"}


# ==============================================================================
# 2. Simple OTA Handshake Endpoint
# ==============================================================================




# ==============================================================================
# 3. Platform Management APIs
# ==============================================================================

class LoginRequest(BaseModel):
    username: str = Field(max_length=128)
    password: str = Field(max_length=1024)


def console_user(authorization: Optional[str]) -> str:
    token = authorization[7:].strip() if authorization and authorization.startswith('Bearer ') else ''
    username = accounts.session_user(token)
    if not username:
        raise HTTPException(status_code=401, detail='Invalid or expired session')
    return username


@app.post('/api/auth/login')
async def console_login(body: LoginRequest, request: Request):
    address = request.client.host if request.client else 'unknown'
    if not accounts.record_attempt(f'login:{address}'):
        raise HTTPException(status_code=429, detail='Too many login attempts')
    token = await run_in_threadpool(accounts.login, body.username, body.password)
    if not token:
        raise HTTPException(status_code=401, detail='Invalid credentials')
    return {'token': token}


@app.get('/api/auth/me')
async def console_me(authorization: Optional[str] = Header(None)):
    return {'username': console_user(authorization)}


@app.post('/api/auth/logout')
async def console_logout(authorization: Optional[str] = Header(None)):
    console_user(authorization)
    accounts.logout(authorization[7:].strip())
    return {'status': 'ok'}


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "xiaozhi-platform-bridge",
        "timestamp": int(time.time())
    }


def validate_thingsboard_origin(host: str) -> str:
    try:
        parsed = urlsplit(host)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username is not None or
                parsed.password is not None or parsed.path not in ('', '/') or parsed.query or parsed.fragment):
            raise ValueError
        port = parsed.port
        hostname = parsed.hostname.lower()
        if ':' in hostname:
            hostname = f'[{hostname}]'
        origin = f'{parsed.scheme}://{hostname}' + (f':{port}' if port is not None else '')
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail='Invalid ThingsBoard origin')
    allowed = {value.strip().rstrip('/').lower() for value in os.getenv('THINGSBOARD_ALLOWED_ORIGINS', '').split(',') if value.strip()}
    if origin not in allowed:
        raise HTTPException(status_code=400, detail='ThingsBoard origin is not allowed')
    return origin


def validate_agent_integration(payload: Dict[str, Any]):
    config = payload.get('config') or {}
    if not isinstance(config, dict):
        raise HTTPException(status_code=400, detail='Invalid configuration')
    for integrations in (payload.get('integrations'), config.get('integrations')):
        if integrations is None:
            continue
        if not isinstance(integrations, dict) or not isinstance(integrations.get('thingsboard', {}), dict):
            raise HTTPException(status_code=400, detail='Invalid integration')
        host = integrations.get('thingsboard', {}).get('host')
        if host:
            validate_thingsboard_origin(host)



def user_store(authorization: Optional[str]) -> PlatformStore:
    return PlatformStore(accounts, console_user(authorization))


def owned_agent(store: PlatformStore, agent_id: str):
    agent = store.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail='Agent not found')
    return agent


@app.get("/api/agents")
async def list_agents(authorization: Optional[str] = Header(None)):
    return {"agents": user_store(authorization).list_safe_agents()}


@app.get("/api/agents/{agent_id}")
async def get_agent_endpoint(agent_id: str, authorization: Optional[str] = Header(None)):
    store = user_store(authorization)
    owned_agent(store, agent_id)
    return next(agent for agent in store.list_safe_agents() if agent['id'] == agent_id)


@app.post("/api/agents")
async def create_agent_endpoint(payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    store = user_store(authorization)
    validate_agent_integration(payload)
    payload = {**payload, 'id': 'agent_' + uuid.uuid4().hex}
    new_agent = store.create_agent(payload)
    return {"status": "success", "agent": next(agent for agent in store.list_safe_agents() if agent['id'] == new_agent['id'])}


@app.put("/api/agents/{agent_id}")
async def update_agent_endpoint(agent_id: str, payload: Dict[str, Any], authorization: Optional[str] = Header(None)):
    store = user_store(authorization)
    owned_agent(store, agent_id)
    validate_agent_integration(payload)
    try:
        store.update_agent(agent_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success", "message": f"Updated agent {agent_id}"}


@app.delete("/api/agents/{agent_id}")
async def delete_agent_endpoint(agent_id: str, authorization: Optional[str] = Header(None)):
    store = user_store(authorization)
    owned_agent(store, agent_id)
    device_db.revoke_agent_devices(agent_id)
    store.delete_agent(agent_id)
    return {"status": "success", "message": f"Deleted agent {agent_id}"}


class AgentChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, Any]]] = []


@app.post("/api/agents/{agent_id}/chat")
async def agent_chat_endpoint(agent_id: str, req: AgentChatRequest, authorization: Optional[str] = Header(None)):
    agent = owned_agent(user_store(authorization), agent_id)
    return await run_agent_chat(agent, req)


async def run_agent_chat(agent: Dict[str, Any], req: AgentChatRequest):
    """Executes inference using only the selected agent's configuration."""
    user_text = req.message.strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="Empty message")

    prompt = agent.get("prompt") or (
        f"Bạn là {agent.get('name', 'Nova')}, trợ lý giọng nói thông minh cho gia đình. "
        "Trả lời bằng tiếng Việt ngắn gọn, súc tích (1-2 câu), tự nhiên."
    )
    prompt = response_prompt(agent, prompt)
    model_name = agent.get("llm", {}).get("model", "qwen2.5:3b-instruct")
    ollama_url = os.getenv("OLLAMA_URL", "http://ollama:11434").rstrip("/")
    tb_conf = agent.get("integrations", {}).get("thingsboard", {})

    try:
        return await tool_pipeline.run_tool_pipeline(
            agent=agent,
            user_text=user_text,
            history=req.history or [],
            base_prompt=prompt,
            tb_conf=tb_conf,
            validate_origin=validate_thingsboard_origin,
            ollama_url=ollama_url,
            model_name=model_name,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error during agent chat inference: %s", e)
        raise HTTPException(status_code=500, detail=f"LLM inference failure: {str(e)}")


@app.post("/api/agents/{agent_id}/v1/chat/completions")
async def device_agent_chat(agent_id: str, request: Request, authorization: Optional[str] = Header(None)):
    token = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not SECRET_KEY or not secrets.compare_digest(token, SECRET_KEY):
        raise HTTPException(status_code=401, detail="Unauthorized")
    body = await request.json()
    messages = body.get("messages")
    if not isinstance(messages, list):
        raise HTTPException(status_code=400, detail="Messages are required")
    history = [message for message in messages if isinstance(message, dict)
               and message.get("role") in ("user", "assistant") and isinstance(message.get("content"), str)]
    if not history or history[-1]["role"] != "user":
        raise HTTPException(status_code=400, detail="The last message must be from the user")
    agent = accounts.get_agent_by_id(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    result = await run_agent_chat(agent, AgentChatRequest(message=history[-1]["content"], history=history[:-1]))
    response_id = "chatcmpl-" + uuid.uuid4().hex
    model = body.get("model", "")
    created = int(time.time())
    if body.get("stream"):
        async def stream():
            for delta, reason in (({"role": "assistant", "content": result["reply"]}, None), ({}, "stop")):
                payload = {"id": response_id, "object": "chat.completion.chunk", "created": created,
                           "model": model, "choices": [{"index": 0, "delta": delta, "finish_reason": reason}]}
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(stream(), media_type="text/event-stream")
    return {"id": response_id, "object": "chat.completion", "created": created, "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": result["reply"]}, "finish_reason": "stop"}]}


@app.get("/api/devices")
async def list_devices_endpoint(authorization: Optional[str] = Header(None)):
    store = user_store(authorization)
    devices = []
    for device in device_db.list_authenticated_devices():
        agent = store.get_agent(device['agent_id'])
        if agent:
            devices.append({**device, 'agent_name': agent['name'], 'agent_role': agent.get('role', 'Assistant'),
                            'is_auth': True, 'ota_enabled': True})
    return {'devices': devices}


class CreateActivationRequest(BaseModel):
    agent_id: str
    expiration_seconds: Optional[int] = 300


@app.post("/api/devices/activation")
async def create_activation_endpoint(req: CreateActivationRequest, authorization: Optional[str] = Header(None)):
    """Generates a temporary cryptographically random 6-digit numeric activation code."""
    agent = owned_agent(user_store(authorization), req.agent_id)

    ttl = min(max(req.expiration_seconds or 300, 60), 3600)
    record = device_db.create_activation_code(req.agent_id, ttl_seconds=ttl)
    return {
        "status": "success",
        "code": record["code"],
        "agent_id": record["agent_id"],
        "expires_at": record["expires_at"],
        "ttl_seconds": record["ttl_seconds"]
    }


class ActivationStatusRequest(BaseModel):
    code: str


@app.post("/api/devices/activation/status")
async def get_activation_status_endpoint(body: ActivationStatusRequest, authorization: Optional[str] = Header(None)):
    """Queries an activation code without putting it in the URL."""
    store = user_store(authorization)
    status_info = device_db.get_activation_status(body.code)
    if not store.get_agent(status_info.get('agent_id')):
        raise HTTPException(status_code=404, detail='Activation code not found')
    return status_info


class BindActivationCodeRequest(BaseModel):
    code: str
    agent_id: str
    device_name: Optional[str] = None


@app.post("/api/devices/activation/bind")
@app.post("/api/devices/activate")
async def bind_activation_code_endpoint(req: BindActivationCodeRequest, request: Request, authorization: Optional[str] = Header(None)):
    store = user_store(authorization)
    owned_agent(store, req.agent_id)
    address = request.client.host if request.client else 'unknown'
    rate_id = f'bind:{address}'
    if not accounts.record_attempt(rate_id):
        raise HTTPException(status_code=429, detail='Too many attempts')
    record = device_db.enrollment_record(req.code.strip())
    if (not SECRET_KEY or not record or not record.get('enrollment_hash') or
            record['status'] != 'pending' or record['expires_at'] <= time.time() or
            (record['agent_id'] and record['agent_id'] != req.agent_id)):
        raise HTTPException(status_code=400, detail='Invalid activation code')
    token = hmac.new(SECRET_KEY.encode(), record['enrollment_hash'].encode(), hashlib.sha256).hexdigest()
    existing = device_db.get_device_by_mac(record.get('mac_address') or '')
    legacy_agent_id = existing['agent_id'] if existing and not accounts.get_agent_by_id(existing['agent_id']) else None
    try:
        result = device_db.bind_device_by_code(req.code.strip(), req.agent_id, req.device_name,
                                               raw_token=token, legacy_agent_id=legacy_agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    result.pop('device_token', None)
    return {'status': 'success', 'device': result}


# ==============================================================================
# XiaoZhi ESP32 Hardware OTA & Activation Handlers
# ==============================================================================

@app.api_route("/xiaozhi/ota/", methods=["GET", "POST"])
@app.api_route("/xiaozhi/ota", methods=["GET", "POST"])
async def xiaozhi_ota_check_endpoint(request: Request):
    """Called by XiaoZhi ESP32 upon connecting to Wi-Fi.

    If device is already bound: delivers WebSocket runtime endpoint without challenge.
    If device is unbound: delivers 6-digit code for device to speak out and display.
    """
    device_mac = (
        request.headers.get("Device-Id")
        or request.headers.get("device-id")
        or request.headers.get("X-Device-Mac")
        or request.query_params.get("device_id")
        or ""
    )

    # Fallback to JSON body if not in headers
    if not device_mac and request.method == "POST":
        try:
            body = await request.json()
            device_mac = body.get("device_id") or body.get("mac_address") or ""
        except Exception:
            pass

    norm_mac = normalize_mac(device_mac)
    if not re.fullmatch(r'(?:[0-9A-F]{2}:){5}[0-9A-F]{2}', norm_mac):
        raise HTTPException(status_code=400, detail='Valid device MAC is required')
    logger.info("XiaoZhi ESP32 OTA Check from MAC: %s", norm_mac)

    server_time = {
        "timestamp": int(round(time.time() * 1000)),
        "timezone_offset": 420
    }

    # Check if this hardware is already registered/bound
    authorization = request.headers.get('authorization', '')
    token = authorization[7:].strip() if authorization.startswith('Bearer ') else ''
    device = device_db.authenticate_device(token) if token else None
    bound_agent = accounts.get_agent_by_id(device['agent_id']) if device and device['mac_address'] == norm_mac else None

    if bound_agent:
        logger.info("Device %s is already bound to %s (%s)", norm_mac, bound_agent["id"], bound_agent["name"])
        return {
            "server_time": server_time,
            "firmware": {
                "version": "1.0.0",
                "url": ""
            },
            "websocket": {
                "url": PUBLIC_WS_URL
            }
        }

    # Device is unregistered: require a device-held secret before issuing a code.
    enrollment_key = request.headers.get('X-Enrollment-Key', '')
    if not re.fullmatch(r'[0-9a-f]{64}', enrollment_key) or not SECRET_KEY:
        raise HTTPException(status_code=400, detail='Enrollment credential required')
    enrollment_hash = hashlib.sha256(enrollment_key.encode()).hexdigest()
    code = device_db.get_or_create_code_for_device(norm_mac, ttl_seconds=300, enrollment_hash=enrollment_hash)
    logger.info("Delivering activation challenge to device %s", norm_mac)

    return {
        "server_time": server_time,
        "firmware": {
            "version": "1.0.0",
            "url": ""
        },
        "activation": {
            "code": code,
            "message": f"Mã kích hoạt là {code}. Vui lòng nhập mã trên trang quản lý.",
            "challenge": f"challenge_{norm_mac.replace(':', '')}",
            "timeout_ms": 300000
        },
        "websocket": {
            "url": PUBLIC_WS_URL
        }
    }


@app.post("/xiaozhi/ota/activate")
@app.post("/xiaozhi/ota/activate/")
async def xiaozhi_ota_activate_poll_endpoint(request: Request):
    """Polled by ESP32 while waiting for user to enter code in web console.

    Returns HTTP 202 (Timeout/Retry) while pending.
    Returns HTTP 200 (Success) once user enters code and selects profile on console.
    """
    device_mac = (
        request.headers.get("Device-Id")
        or request.headers.get("device-id")
        or ""
    )
    if not device_mac:
        try:
            body = await request.json()
            device_mac = body.get("serial_number") or ""
        except Exception:
            pass

    norm_mac = normalize_mac(device_mac) if device_mac else ""

    enrollment_key = request.headers.get('X-Enrollment-Key', '')
    if not SECRET_KEY or not re.fullmatch(r'[0-9a-f]{64}', enrollment_key):
        return Response(content='{"code":202,"msg":"waiting for user input"}', media_type='application/json', status_code=202)
    enrollment_hash = hashlib.sha256(enrollment_key.encode()).hexdigest()
    device = device_db.redeemed_enrollment(norm_mac, enrollment_hash)
    if device and accounts.get_agent_by_id(device['agent_id']):
        token = hmac.new(SECRET_KEY.encode(), enrollment_hash.encode(), hashlib.sha256).hexdigest()
        if secrets.compare_digest(device['token_hash'], hashlib.sha256(token.encode()).hexdigest()):
            return {'code': 0, 'device_id': device['device_id'], 'agent_id': device['agent_id'], 'device_token': token,
                    'ws_url': PUBLIC_WS_URL}
    return Response(content='{"code":202,"msg":"waiting for user input"}', media_type='application/json', status_code=202)


class RegisterDeviceRequest(BaseModel):
    activation_code: str
    mac_address: str
    device_name: Optional[str] = None
    hardware_model: Optional[str] = "ESP32-S3"
    firmware_version: Optional[str] = "v2.1.8"


@app.post("/api/devices/register")
async def register_device_endpoint(req: RegisterDeviceRequest, request: Request):
    """Redeems an activation code, registers device, and issues hashed token credentials."""
    client_ip = request.client.host if request.client else "unknown"
    norm_mac = normalize_mac(req.mac_address)
    rate_id = f"register:{client_ip}"
    if not re.fullmatch(r'(?:[0-9A-F]{2}:){5}[0-9A-F]{2}', norm_mac):
        raise HTTPException(status_code=400, detail='Valid device MAC is required')

    if not accounts.record_attempt(rate_id):
        raise HTTPException(status_code=429, detail='Too many attempts')

    try:
        activation = device_db.get_activation_status(req.activation_code.strip())
        if not accounts.get_agent_by_id(activation.get('agent_id')):
            raise ValueError('Invalid activation code.')
        existing = device_db.get_device_by_mac(norm_mac)
        legacy_agent_id = existing['agent_id'] if existing and not accounts.get_agent_by_id(existing['agent_id']) else None
        reg_result = device_db.register_device_with_code(
            code=req.activation_code.strip(),
            mac_address=norm_mac,
            device_name=req.device_name,
            hardware_model=req.hardware_model or "ESP32-S3",
            firmware_version=req.firmware_version or "v2.1.8",
            legacy_agent_id=legacy_agent_id
        )

        return {
            "status": "success",
            "device_id": reg_result["device_id"],
            "device_token": reg_result["device_token"],
            "mac_address": norm_mac,
            "agent_id": reg_result["agent_id"],
            "device_name": reg_result["device_name"],
            "config": {
                "ws_url": PUBLIC_WS_URL,
                "ota_url": PUBLIC_OTA_URL,
                "heartbeat_interval_seconds": 30
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Device registration error: %s", e)
        raise HTTPException(status_code=500, detail="Internal registration failure.")


def extract_device_token(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_device_token: Optional[str] = Header(None, alias="X-Device-Token")
) -> str:
    """Extracts raw bearer token from authorization header or X-Device-Token."""
    if x_device_token:
        return x_device_token.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    raise HTTPException(status_code=401, detail="Missing device authentication credential.")


def authenticated_device(token: str):
    device = device_db.authenticate_device(token)
    if not device or not accounts.get_agent_by_id(device['agent_id']):
        raise HTTPException(status_code=401, detail='Invalid or revoked device token.')
    return device


@app.websocket('/xiaozhi/v1/')
async def device_websocket(socket: WebSocket):
    authorization = socket.headers.get('authorization', '')
    token = authorization[7:].strip() if authorization.startswith('Bearer ') else ''
    device = device_db.authenticate_device(token) if token else None
    if (not device or not accounts.get_agent_by_id(device['agent_id']) or
            normalize_mac(socket.headers.get('device-id', '')) != device['mac_address']):
        await socket.close(code=4401)
        return

    import websockets
    from websockets.exceptions import WebSocketException
    upstream_url = os.getenv('XIAOZHI_UPSTREAM_WS', 'ws://xiaozhi-server:8002/xiaozhi/v1/')
    headers = {key: value for key, value in socket.headers.items()
               if key in ('device-id', 'client-id', 'protocol-version')}
    try:
        async with websockets.connect(upstream_url, additional_headers=headers) as upstream:
            await socket.accept()

            last_check = 0.0
            allowed = False
            check_lock = asyncio.Lock()

            def check_device():
                active = device_db.authenticate_device(token)
                return bool(active and active['agent_id'] == device['agent_id'] and
                            accounts.get_agent_by_id(active['agent_id']))

            async def still_authorized():
                nonlocal last_check, allowed
                async with check_lock:
                    # shortcut: revocation may take one second, shorten if immediate disconnect is required.
                    if time.monotonic() - last_check >= 1.0:
                        allowed = await run_in_threadpool(check_device)
                        last_check = time.monotonic()
                    return allowed

            async def to_upstream():
                while True:
                    message = await socket.receive()
                    if message['type'] == 'websocket.disconnect' or not await still_authorized():
                        return
                    data = message.get('bytes') if message.get('bytes') is not None else message.get('text')
                    if data is not None:
                        await upstream.send(data)

            async def to_device():
                async for data in upstream:
                    if not await still_authorized():
                        return
                    if isinstance(data, bytes):
                        await socket.send_bytes(data)
                    else:
                        await socket.send_text(data)

            tasks = [asyncio.create_task(to_upstream()), asyncio.create_task(to_device())]
            try:
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
    except (WebSocketDisconnect, OSError, WebSocketException):
        pass
    finally:
        try:
            await socket.close()
        except (RuntimeError, WebSocketDisconnect):
            pass


@app.get("/api/devices/me")
async def get_device_me_endpoint(request: Request, authorization: Optional[str] = Header(None), x_device_token: Optional[str] = Header(None, alias="X-Device-Token")):
    """Returns authenticated identity and metadata for the calling physical device."""
    raw_token = extract_device_token(request, authorization, x_device_token)
    device = authenticated_device(raw_token)

    return {
        "device_id": device["device_id"],
        "mac_address": device["mac_address"],
        "agent_id": device["agent_id"],
        "device_name": device["device_name"],
        "hardware_model": device["hardware_model"],
        "firmware_version": device["firmware_version"],
        "status": device["status"],
        "online_status": device["online_status"],
        "registered_at": device["registered_at"],
        "last_seen": device["last_seen"]
    }


@app.get("/api/devices/me/config")
async def get_device_me_config_endpoint(request: Request, authorization: Optional[str] = Header(None), x_device_token: Optional[str] = Header(None, alias="X-Device-Token")):
    """Returns assigned runtime configuration without exposing sensitive ThingsBoard keys."""
    raw_token = extract_device_token(request, authorization, x_device_token)
    device = authenticated_device(raw_token)

    agent = accounts.get_agent_by_id(device["agent_id"]) or {}

    return {
        "device_id": device["device_id"],
        "mac_address": device["mac_address"],
        "ws_url": PUBLIC_WS_URL,
        "ota_url": PUBLIC_OTA_URL,
        "heartbeat_interval_seconds": 30,
        "agent": {
            "id": agent.get("id", device["agent_id"]),
            "name": agent.get("name", "Unknown Agent"),
            "role": agent.get("role", "Assistant"),
            "language": agent.get("language", "vi")
        }
    }


class HeartbeatRequest(BaseModel):
    token: Optional[str] = None


@app.post("/api/devices/heartbeat")
async def device_heartbeat_endpoint(
    request: Request,
    payload: Optional[HeartbeatRequest] = None,
    authorization: Optional[str] = Header(None),
    x_device_token: Optional[str] = Header(None, alias="X-Device-Token")
):
    """Updates device heartbeat and last seen timestamp."""
    raw_token = None
    if payload and payload.token:
        raw_token = payload.token
    else:
        try:
            raw_token = extract_device_token(request, authorization, x_device_token)
        except Exception:
            raw_token = None

    if not raw_token:
        raise HTTPException(status_code=401, detail="Missing authentication token for heartbeat.")

    authenticated_device(raw_token)
    updated = device_db.update_heartbeat(raw_token)
    if not updated:
        raise HTTPException(status_code=401, detail="Invalid or revoked device token.")

    return {"status": "ok", "last_seen": updated["last_seen"]}


@app.post("/api/devices/me/unbind")
async def device_me_unbind_endpoint(request: Request, authorization: Optional[str] = Header(None), x_device_token: Optional[str] = Header(None, alias="X-Device-Token")):
    """Allows device to initiate self-unbinding and revoke credentials."""
    raw_token = extract_device_token(request, authorization, x_device_token)
    device = authenticated_device(raw_token)

    device_db.unbind_device_by_token(raw_token)
    return {"status": "success", "message": f"Device {device['device_id']} unbound successfully"}


class BindDeviceRequest(BaseModel):
    mac_address: str
    agent_id: str
    device_name: Optional[str] = "ESP32 Device"


@app.post("/api/devices/bind")
async def bind_device_endpoint(req: BindDeviceRequest):
    try:
        platform_store.bind_device(req.mac_address, req.agent_id, req.device_name or "ESP32 Device")
        return {"status": "success", "message": f"Bound {req.mac_address} to {req.agent_id}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class UnbindDeviceRequest(BaseModel):
    mac_address: str


@app.post("/api/devices/unbind")
async def unbind_device_endpoint(req: UnbindDeviceRequest, authorization: Optional[str] = Header(None)):
    store = user_store(authorization)
    device = device_db.get_device_by_mac(normalize_mac(req.mac_address))
    if not device or not store.get_agent(device['agent_id']):
        raise HTTPException(status_code=404, detail='Device not found')
    device_db.unbind_device_by_identifier(device['mac_address'])
    return {'status': 'success', 'message': 'Device unbound'}


class ThingsBoardTestRequest(BaseModel):
    host: Optional[str] = None
    api_key: Optional[str] = None
    agent_id: Optional[str] = None


@app.post("/api/integrations/thingsboard/test")
async def test_thingsboard_integration(req: ThingsBoardTestRequest, authorization: Optional[str] = Header(None)):
    """Tests connectivity to ThingsBoard instance and reports discovered devices."""
    store = user_store(authorization)
    if not req.agent_id:
        raise HTTPException(status_code=400, detail='Agent is required')
    agent = owned_agent(store, req.agent_id)
    tb = agent.get('integrations', {}).get('thingsboard', {})
    host = (req.host or tb.get('host') or '').rstrip('/')
    api_key = req.api_key
    if not api_key or '...' in api_key or api_key == '***':
        api_key = tb.get('api_key', '')
    if not host:
        return {'status': 'error', 'message': 'No ThingsBoard host configured.'}
    host = validate_thingsboard_origin(host)

    if not api_key:
        return {"status": "error", "message": "No API key provided or configured."}

    import httpx
    headers = {
        "User-Agent": "XiaoZhi-Platform/1.0",
        "X-Authorization": f"ApiKey {api_key}"
    }
    url = f"{host}/api/tenant/devices?pageSize=10&page=0"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                total = data.get("totalElements", len(data.get("data", [])))
                return {
                    "status": "success",
                    "device_count": total,
                    "host": host,
                    "message": f"Connected to ThingsBoard successfully ({total} devices found)"
                }
            else:
                return {
                    "status": "error",
                    "status_code": resp.status_code,
                    "message": f"ThingsBoard returned HTTP {resp.status_code}: {resp.text[:120]}"
                }
    except Exception as e:
        return {"status": "error", "message": f"Connection failed: {str(e)}"}


@app.get("/api/integrations/thingsboard/telemetry")
async def get_thingsboard_telemetry(agent_id: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """Safe read-only telemetry preview exposing authorized ThingsBoard data."""
    store = user_store(authorization)
    if not agent_id:
        raise HTTPException(status_code=400, detail='Agent is required')
    agent = owned_agent(store, agent_id)
    tb = agent.get('integrations', {}).get('thingsboard', {})
    host = (tb.get('host') or '').rstrip('/')
    api_key = tb.get('api_key') or ''
    if not host or not api_key:
        return {'status': 'error', 'message': 'ThingsBoard is not configured.'}
    host = validate_thingsboard_origin(host)

    import httpx
    headers = {
        "User-Agent": "XiaoZhi-Platform/1.0",
        "X-Authorization": f"ApiKey {api_key}"
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            dev_resp = await client.get(f"{host}/api/tenant/devices?pageSize=6&page=0", headers=headers)
            if dev_resp.status_code != 200:
                return {"status": "error", "message": f"Failed to list devices: HTTP {dev_resp.status_code}"}
            devices_data = dev_resp.json().get("data", [])
            results = []
            for d in devices_data:
                d_id = d["id"]["id"]
                d_name = d.get("name", "Unknown")
                tel_resp = await client.get(
                    f"{host}/api/plugins/telemetry/DEVICE/{d_id}/values/timeseries",
                    headers=headers
                )
                telemetry = tel_resp.json() if tel_resp.status_code == 200 else {}
                results.append({
                    "id": d_id,
                    "name": d_name,
                    "type": d.get("type", "default"),
                    "telemetry": telemetry
                })
            return {
                "status": "success",
                "host": host,
                "agent_id": agent_id,
                "tool_policy": agent.get("tool_policy", "full_control") if agent else "read_only_telemetry",
                "devices": results
            }
    except Exception as e:
        return {"status": "error", "message": str(e)}
