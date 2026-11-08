"""
Platform Integration Bridge for XiaoZhi ESP32 Server.
Provides the upstream manager-api endpoints, resolves Agent Profiles dynamically,
and coordinates ThingsBoard MCP integration.
"""

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Header, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .store import platform_store, normalize_mac
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

SECRET_KEY = os.getenv("BRIDGE_SECRET", "sk-xiaozhi-local-secret").strip()

# Internal service URLs
WHISPER_URL = os.getenv("WHISPER_URL", "http://faster-whisper:8000/v1/audio/transcriptions")
PIPER_URL = os.getenv("PIPER_URL", "http://piper-tts:10200/v1/audio/speech")
LLM_GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "http://mcp-gateway:8008/v1")
WS_PUBLIC_PORT = int(os.getenv("WS_PUBLIC_PORT", "8002"))
HOST_IP = os.getenv("HOST_IP", "192.168.1.7")
if HOST_IP in ("127.0.0.1", "localhost", "0.0.0.0"):
    HOST_IP = "192.168.1.7"

app = FastAPI(title="XiaoZhi Platform Management Bridge", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Virtual PC Web Tester static client
STATIC_TEST_DIR = Path(__file__).resolve().parent / "static_test"
if STATIC_TEST_DIR.exists():
    app.mount("/test", StaticFiles(directory=str(STATIC_TEST_DIR), html=True), name="static_test")


@app.get("/pc-test")
async def redirect_to_pc_test():
    return RedirectResponse(url="/test/test_page.html")


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
    if not SECRET_KEY:
        return
    if not authorization:
        # Allow open access if bridge is in dev mode or secret not strictly enforced
        return
    token = authorization.replace("Bearer ", "").strip()
    if token != SECRET_KEY and token != "sk-local":
        logger.warning("Unauthorized request with token: %s", token[:6] + "...")


# ==============================================================================
# 1. XiaoZhi manager-api Contract Endpoints (read_config_from_api: true)
# ==============================================================================

@app.post("/xiaozhi/config/server-base")
@app.post("/config/server-base")
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
                    "api_key": SECRET_KEY,
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


class AgentModelsRequest(BaseModel):
    macAddress: Optional[str] = None
    clientId: Optional[str] = None
    selectedModule: Optional[Dict[str, Any]] = None


@app.post("/xiaozhi/config/agent-models")
@app.post("/config/agent-models")
async def get_agent_models(req: AgentModelsRequest):
    """
    Resolves the active Agent Profile and ThingsBoard context for the connecting device.
    Matches the incoming MAC address to the platform's Agent Profile.
    """
    mac = req.macAddress or req.clientId or "default"
    logger.info("Resolving agent models for MAC: %s (client_id: %s)", mac, req.clientId)

    agent = platform_store.get_agent_for_device(mac)

    # If device is not explicitly bound, fallback to default active agent
    if not agent:
        agents = platform_store.list_agents()
        if agents:
            agent = agents[0]
            logger.info("Auto-binding unassigned device %s to default agent: %s", mac, agent["name"])
            platform_store.bind_device(mac, agent["id"], "Auto-Discovered Device")
        else:
            return {"code": 10041, "msg": f"Device {mac} not registered"}

    # Export active agent profile to agent_profile.json so thingsboard-mcp has credentials
    shared_profile_path = os.getenv("SHARED_AGENT_PROFILE_PATH", "/app/agent_profile.json")
    try:
        platform_store.sync_to_agent_profile_json(agent["id"], shared_profile_path)
    except Exception as e:
        logger.warning("Could not sync agent profile to %s: %s", shared_profile_path, e)

    prompt = agent.get("prompt", "")
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
                    "base_url": LLM_GATEWAY_URL,
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


@app.post("/xiaozhi/agent/chat-history/report")
@app.post("/agent/chat-history/report")
async def report_chat_history(req: ChatReportRequest):
    """Stores conversation transcript chunks reported by the XiaoZhi runtime."""
    if req.macAddress and req.content:
        platform_store.record_chat(
            mac_address=req.macAddress,
            session_id=req.sessionId or "default_session",
            chat_type=req.chatType or 1,
            content=req.content
        )
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

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "xiaozhi-platform-bridge",
        "timestamp": int(time.time())
    }


@app.get("/api/agents")
async def list_agents():
    """Returns all configured agents with masked credentials for the frontend console."""
    return {"agents": platform_store.list_safe_agents()}


@app.get("/api/agents/{agent_id}")
async def get_agent_endpoint(agent_id: str):
    agent = platform_store.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    # Return formatted safe agent
    for safe in platform_store.list_safe_agents():
        if safe["id"] == agent_id:
            return safe
    return agent


@app.post("/api/agents")
async def create_agent_endpoint(payload: Dict[str, Any]):
    try:
        new_agent = platform_store.create_agent(payload)
        return {"status": "success", "agent": new_agent}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/agents/{agent_id}")
async def update_agent_endpoint(agent_id: str, payload: Dict[str, Any]):
    try:
        updated = platform_store.update_agent(agent_id, payload)
        return {"status": "success", "message": f"Updated agent {agent_id}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/agents/{agent_id}")
async def delete_agent_endpoint(agent_id: str):
    try:
        platform_store.delete_agent(agent_id)
        return {"status": "success", "message": f"Deleted agent {agent_id}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class AgentChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, Any]]] = []


@app.post("/api/agents/{agent_id}/chat")
async def agent_chat_endpoint(agent_id: str, req: AgentChatRequest):
    """Executes real LLM inference with ThingsBoard tool-calling for the Web Console."""
    agent = platform_store.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    user_text = req.message.strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="Empty message")

    shared_profile_path = os.getenv("SHARED_AGENT_PROFILE_PATH", "/app/agent_profile.json")
    try:
        platform_store.sync_to_agent_profile_json(agent_id, shared_profile_path)
    except Exception as e:
        logger.warning("Could not sync agent profile: %s", e)

    prompt = agent.get("prompt") or (
        f"Bạn là {agent.get('name', 'Nova')}, trợ lý giọng nói thông minh cho gia đình. "
        "Trả lời bằng tiếng Việt ngắn gọn, súc tích (1-2 câu), tự nhiên."
    )
    model_name = agent.get("llm", {}).get("model", "qwen2.5:3b-instruct")

    tb_tools = [
        {
            "type": "function",
            "function": {
                "name": "list_devices",
                "description": "List all IoT devices, sensors, and actuators connected to ThingsBoard.",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_telemetry",
                "description": "Query current environmental or sensor telemetry (temperature, humidity, CO2, etc.) for a device.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_name": {
                            "type": "string",
                            "description": "Name of the target ThingsBoard device, e.g. Test Device A1 or Virtual-Environmental-Monitor"
                        }
                    },
                    "required": ["device_name"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "send_rpc",
                "description": "Send a control command / RPC action (turn on, turn off, toggle, set state) to an actuator device.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_name": {"type": "string", "description": "Name of the target device"},
                        "method": {"type": "string", "description": "RPC method name, e.g. setLight, setPower"},
                        "params": {"type": "string", "description": "Command parameters as JSON string, e.g. {\"state\": true}"}
                    },
                    "required": ["device_name", "method"]
                }
            }
        }
    ]

    messages = [{"role": "system", "content": prompt}]
    for h in (req.history or [])[-6:]:
        r = h.get("role")
        c = h.get("content")
        if r in ("user", "assistant") and c:
            messages.append({"role": r, "content": c})
    messages.append({"role": "user", "content": user_text})

    import httpx
    ollama_url = os.getenv("OLLAMA_URL", "http://ollama:11434").rstrip("/")

    tb_conf = agent.get("integrations", {}).get("thingsboard", {})
    tb_host = (tb_conf.get("host") or os.getenv("THINGSBOARD_HOST", "https://codehelpers.tech")).rstrip("/")
    tb_key = tb_conf.get("api_key") or os.getenv("THINGSBOARD_API_KEY", "tb_G5TSH2WJsF3g25Q_7jImZwyUpdAYqGtI6cT86c-dMCKy_d8WZ3M3rNjn9zhzOT5Y9AnvV-KKQPpIQChD7qPluA")
    tb_headers = {"User-Agent": "XiaoZhi-Platform/1.0", "X-Authorization": f"ApiKey {tb_key}"}

    executed_tools = []

    async def execute_tool(tool_name: str, args_dict: Dict[str, Any]) -> str:
        async with httpx.AsyncClient(timeout=8.0) as client:
            if tool_name == "list_devices":
                url = f"{tb_host}/api/tenant/devices?pageSize=10&page=0"
                resp = await client.get(url, headers=tb_headers)
                if resp.status_code == 200:
                    raw_devs = resp.json().get("data", [])
                    res = [{"name": d.get("name"), "type": d.get("type"), "id": d.get("id", {}).get("id")} for d in raw_devs]
                    return json.dumps({"status": "success", "devices": res}, ensure_ascii=False)
                return json.dumps({"status": "error", "message": f"ThingsBoard HTTP {resp.status_code}"})

            elif tool_name == "get_telemetry":
                dev_name = args_dict.get("device_name", "").strip()
                url = f"{tb_host}/api/tenant/devices?pageSize=20&page=0"
                resp = await client.get(url, headers=tb_headers)
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    matched = next((d for d in data if d.get("name", "").lower() == dev_name.lower()), None)
                    if not matched and data:
                        matched = data[0]
                    if matched:
                        dev_id = matched["id"]["id"]
                        tel_url = f"{tb_host}/api/plugins/telemetry/DEVICE/{dev_id}/values/timeseries"
                        tel_resp = await client.get(tel_url, headers=tb_headers)
                        if tel_resp.status_code == 200:
                            tel_data = tel_resp.json()
                            summary = {k: v[0].get("value") for k, v in tel_data.items() if v}
                            return json.dumps({"device": matched.get("name"), "telemetry": summary}, ensure_ascii=False)
                return json.dumps({"status": "error", "message": f"Device '{dev_name}' telemetry not found"})

            elif tool_name == "send_rpc":
                policy = agent.get("tool_policy", "full_control")
                if policy == "read_only_telemetry":
                    return json.dumps({"status": "forbidden", "message": "Policy violation: Agent has read-only access and cannot send RPC commands."})
                dev_name = args_dict.get("device_name", "").strip()
                method = args_dict.get("method", "setState")
                params = args_dict.get("params", "{}")
                url = f"{tb_host}/api/tenant/devices?pageSize=20&page=0"
                resp = await client.get(url, headers=tb_headers)
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    matched = next((d for d in data if d.get("name", "").lower() == dev_name.lower()), None)
                    if matched:
                        dev_id = matched["id"]["id"]
                        rpc_url = f"{tb_host}/api/plugins/rpc/oneway/{dev_id}"
                        try:
                            rpc_params = json.loads(params) if isinstance(params, str) else params
                        except Exception:
                            rpc_params = {"command": params}
                        rpc_resp = await client.post(rpc_url, json={"method": method, "params": rpc_params}, headers=tb_headers)
                        return json.dumps({"status": "success", "device": dev_name, "method": method, "response_code": rpc_resp.status_code})
                return json.dumps({"status": "error", "message": f"Device '{dev_name}' not found for RPC"})

            return json.dumps({"status": "error", "message": f"Unknown tool: {tool_name}"})

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            t1_resp = await client.post(
                f"{ollama_url}/v1/chat/completions",
                json={
                    "model": model_name,
                    "messages": messages,
                    "tools": tb_tools,
                    "stream": False
                }
            )
            t1_resp.raise_for_status()
            t1_data = t1_resp.json()

            choice = t1_data.get("choices", [{}])[0]
            msg = choice.get("message", {})
            tool_calls = msg.get("tool_calls") or []

            if not tool_calls:
                content = msg.get("content", "").strip()
                if not content:
                    fb_resp = await client.post(
                        f"{ollama_url}/v1/chat/completions",
                        json={"model": model_name, "messages": messages, "stream": False}
                    )
                    content = fb_resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
                return {"reply": content, "tool_calls": []}

            t2_messages = list(messages)
            t2_messages.append(msg)

            for tc in tool_calls:
                fn = tc.get("function", {})
                tc_id = tc.get("id", "call_default")
                fn_name = fn.get("name", "")
                raw_args = fn.get("arguments", "{}")
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception:
                    args = {}

                tool_res_str = await execute_tool(fn_name, args)
                executed_tools.append({
                    "id": tc_id,
                    "name": fn_name,
                    "arguments": json.dumps(args, ensure_ascii=False),
                    "result": tool_res_str
                })
                t2_messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": tool_res_str
                })

            t2_resp = await client.post(
                f"{ollama_url}/v1/chat/completions",
                json={"model": model_name, "messages": t2_messages, "stream": False}
            )
            t2_resp.raise_for_status()
            final_reply = t2_resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            return {"reply": final_reply, "tool_calls": executed_tools}

    except Exception as e:
        logger.error("Error during agent chat inference: %s", e)
        raise HTTPException(status_code=500, detail=f"LLM inference failure: {str(e)}")


@app.get("/api/devices")
async def list_devices_endpoint():
    """Aggregates all registered hardware nodes across all agent profiles."""
    return {"devices": platform_store.list_devices()}


class CreateActivationRequest(BaseModel):
    agent_id: str
    expiration_seconds: Optional[int] = 300


@app.post("/api/devices/activation")
async def create_activation_endpoint(req: CreateActivationRequest):
    """Generates a temporary cryptographically random 6-digit numeric activation code."""
    agent = platform_store.get_agent(req.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{req.agent_id}' not found.")

    ttl = min(max(req.expiration_seconds or 300, 60), 3600)
    record = device_db.create_activation_code(req.agent_id, ttl_seconds=ttl)
    return {
        "status": "success",
        "code": record["code"],
        "agent_id": record["agent_id"],
        "expires_at": record["expires_at"],
        "ttl_seconds": record["ttl_seconds"]
    }


@app.get("/api/devices/activation/status")
async def get_activation_status_endpoint(code: str):
    """Queries activation status of a 6-digit code for frontend progress detection."""
    status_info = device_db.get_activation_status(code)
    return status_info


class BindActivationCodeRequest(BaseModel):
    code: str
    agent_id: str
    device_name: Optional[str] = None


@app.post("/api/devices/activation/bind")
@app.post("/api/devices/activate")
async def bind_activation_code_endpoint(req: BindActivationCodeRequest):
    """User enters the 6-digit code spoken/printed by the ESP32 and binds it to an Agent Profile."""
    clean_code = req.code.strip()
    agent = platform_store.get_agent(req.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{req.agent_id}' not found.")

    try:
        reg_result = device_db.bind_device_by_code(
            code=clean_code,
            agent_id=req.agent_id,
            device_name=req.device_name
        )
        norm_mac = reg_result["mac_address"]
        platform_store.bind_device(
            mac_address=norm_mac,
            agent_id=req.agent_id,
            device_name=reg_result["device_name"]
        )
        return {
            "status": "success",
            "message": f"Bound device {norm_mac} to {agent['name']}",
            "device": reg_result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Error binding device by activation code: %s", e)
        raise HTTPException(status_code=500, detail="Internal binding error.")


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

    norm_mac = normalize_mac(device_mac) if device_mac else "30:ED:A0:29:54:4C"
    logger.info("XiaoZhi ESP32 OTA Check from MAC: %s", norm_mac)

    server_time = {
        "timestamp": int(round(time.time() * 1000)),
        "timezone_offset": 420
    }

    # Check if this hardware is already registered/bound
    bound_agent = platform_store.get_agent_for_device(norm_mac)

    if bound_agent:
        logger.info("Device %s is already bound to %s (%s)", norm_mac, bound_agent["id"], bound_agent["name"])
        return {
            "server_time": server_time,
            "firmware": {
                "version": "1.0.0",
                "url": ""
            },
            "websocket": {
                "url": f"ws://{HOST_IP}:{WS_PUBLIC_PORT}/xiaozhi/v1/"
            }
        }

    # Device is unregistered: generate 6-digit code for ESP32 to speak out
    code = device_db.get_or_create_code_for_device(norm_mac, ttl_seconds=300)
    logger.info("Delivering activation challenge code %s to device %s", code, norm_mac)

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
            "url": f"ws://{HOST_IP}:{WS_PUBLIC_PORT}/xiaozhi/v1/"
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

    # Check if device is now activated
    is_active = False
    if norm_mac:
        is_active = device_db.is_device_activated(norm_mac) or bool(platform_store.get_agent_for_device(norm_mac))

    if is_active:
        logger.info("ESP32 %s activation confirmed! Delivering 200 OK.", norm_mac)
        return Response(content='{"code":0,"msg":"success"}', media_type="application/json", status_code=200)

    # Still waiting for user to enter code on web console
    return Response(content='{"code":202,"msg":"waiting for user input"}', media_type="application/json", status_code=202)


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
    rate_id = f"{client_ip}:{norm_mac}"

    # Check brute-force rate limit
    allowed, remaining = device_db.check_rate_limit(rate_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed registration attempts. Locked for {remaining} seconds."
        )

    try:
        reg_result = device_db.register_device_with_code(
            code=req.activation_code.strip(),
            mac_address=norm_mac,
            device_name=req.device_name,
            hardware_model=req.hardware_model or "ESP32-S3",
            firmware_version=req.firmware_version or "v2.1.8"
        )
        device_db.reset_failed_attempts(rate_id)

        # Sync with agent profile device list in platform_store
        platform_store.bind_device(
            mac_address=norm_mac,
            agent_id=reg_result["agent_id"],
            device_name=reg_result["device_name"]
        )

        return {
            "status": "success",
            "device_id": reg_result["device_id"],
            "device_token": reg_result["device_token"],
            "mac_address": norm_mac,
            "agent_id": reg_result["agent_id"],
            "device_name": reg_result["device_name"],
            "config": {
                "ws_url": f"ws://{HOST_IP}:{WS_PUBLIC_PORT}/xiaozhi/v1/",
                "ota_url": f"http://{HOST_IP}:8003/xiaozhi/ota/",
                "heartbeat_interval_seconds": 30
            }
        }
    except ValueError as e:
        device_db.record_failed_attempt(rate_id, max_attempts=5, lockout_seconds=300)
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


@app.get("/api/devices/me")
async def get_device_me_endpoint(request: Request, authorization: Optional[str] = Header(None), x_device_token: Optional[str] = Header(None, alias="X-Device-Token")):
    """Returns authenticated identity and metadata for the calling physical device."""
    raw_token = extract_device_token(request, authorization, x_device_token)
    device = device_db.authenticate_device(raw_token)
    if not device:
        raise HTTPException(status_code=401, detail="Invalid or revoked device token.")

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
    device = device_db.authenticate_device(raw_token)
    if not device:
        raise HTTPException(status_code=401, detail="Invalid or revoked device token.")

    agent = platform_store.get_agent(device["agent_id"]) or {}

    return {
        "device_id": device["device_id"],
        "mac_address": device["mac_address"],
        "ws_url": f"ws://{HOST_IP}:{WS_PUBLIC_PORT}/xiaozhi/v1/",
        "ota_url": f"http://{HOST_IP}:8003/xiaozhi/ota/",
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

    updated = device_db.update_heartbeat(raw_token)
    if not updated:
        raise HTTPException(status_code=401, detail="Invalid or revoked device token.")

    return {"status": "ok", "last_seen": updated["last_seen"]}


@app.post("/api/devices/me/unbind")
async def device_me_unbind_endpoint(request: Request, authorization: Optional[str] = Header(None), x_device_token: Optional[str] = Header(None, alias="X-Device-Token")):
    """Allows device to initiate self-unbinding and revoke credentials."""
    raw_token = extract_device_token(request, authorization, x_device_token)
    device = device_db.authenticate_device(raw_token)
    if not device:
        raise HTTPException(status_code=401, detail="Invalid or revoked device token.")

    device_db.unbind_device_by_token(raw_token)
    platform_store.unbind_device(device["mac_address"])
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
async def unbind_device_endpoint(req: UnbindDeviceRequest):
    try:
        platform_store.unbind_device(req.mac_address)
        return {"status": "success", "message": f"Unbound device {req.mac_address}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class ThingsBoardTestRequest(BaseModel):
    host: Optional[str] = None
    api_key: Optional[str] = None
    agent_id: Optional[str] = None


@app.post("/api/integrations/thingsboard/test")
async def test_thingsboard_integration(req: ThingsBoardTestRequest):
    """Tests connectivity to ThingsBoard instance and reports discovered devices."""
    host = req.host
    api_key = req.api_key

    if req.agent_id:
        agent = platform_store.get_agent(req.agent_id)
        if agent:
            tb = agent.get("integrations", {}).get("thingsboard", {})
            if not host:
                host = tb.get("host")
            if not api_key or "..." in api_key or api_key == "***":
                api_key = tb.get("api_key")

    host = (host or os.getenv("THINGSBOARD_HOST", "https://codehelpers.tech")).rstrip("/")
    api_key = api_key or os.getenv(
        "THINGSBOARD_API_KEY",
        "tb_G5TSH2WJsF3g25Q_7jImZwyUpdAYqGtI6cT86c-dMCKy_d8WZ3M3rNjn9zhzOT5Y9AnvV-KKQPpIQChD7qPluA"
    )

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
async def get_thingsboard_telemetry(agent_id: Optional[str] = "agent_101"):
    """Safe read-only telemetry preview exposing authorized ThingsBoard data."""
    agent = platform_store.get_agent(agent_id or "agent_101")
    tb = agent.get("integrations", {}).get("thingsboard", {}) if agent else {}
    host = (tb.get("host") or os.getenv("THINGSBOARD_HOST", "https://codehelpers.tech")).rstrip("/")
    api_key = tb.get("api_key") or os.getenv(
        "THINGSBOARD_API_KEY",
        "tb_G5TSH2WJsF3g25Q_7jImZwyUpdAYqGtI6cT86c-dMCKy_d8WZ3M3rNjn9zhzOT5Y9AnvV-KKQPpIQChD7qPluA"
    )

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
