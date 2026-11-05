"""
XiaoZhi MCP Agent Gateway.
Lightweight FastAPI bridge between XiaoZhi ESP32 / Piper TTS and Ollama (Qwen2.5:3b)
with Model Context Protocol (MCP) tool-calling support.
"""
import asyncio
from contextlib import asynccontextmanager
import json
import logging
import os
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
import httpx

from services.mcp_server import (
    configure_coreiot,
    device_control as tb_device_control,
    fetch_iot_dashboard_data,
    get_coreiot_config,
)

# MCP SDK imports
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except (ImportError, ModuleNotFoundError) as err:
    sys.exit(f"Failed to import MCP SDK: {err}. Please install 'mcp>=1.3.0'.")

# Configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mcp_gateway")

API_KEY = os.getenv("API_KEY", "sk-xiaozhi-local-secret").strip()
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b-instruct").strip()
PORT = int(os.getenv("PORT", "8008"))
HOST = os.getenv("HOST", "0.0.0.0")

MCP_SERVER_SCRIPT = os.getenv(
    "MCP_SERVER_SCRIPT",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server.py"),
)

DEFAULT_SYSTEM_PROMPT = (
    "Bạn là XiaoZhi, trợ lý giọng nói thông minh cho gia đình. "
    "Trả lời bằng tiếng Việt ngắn gọn, súc tích (1-2 câu), tự nhiên để phát âm qua loa TTS. "
    "Khi người dùng hỏi về thời gian, thời tiết hoặc yêu cầu điều khiển thiết bị, hãy sử dụng công cụ (tool) tương ứng."
)


class MCPClientManager:
    """Manages MCP Server lifecycle via stdio and caches discovered tools."""

    def __init__(self, script_path: str):
        self.script_path = script_path
        self._ctx = None
        self._session_ctx = None
        self.session: Optional[ClientSession] = None
        self.openai_tools: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        logger.info("Starting MCP stdio server process: %s", self.script_path)
        params = StdioServerParameters(
            command=sys.executable,
            args=[self.script_path],
            env=None,
        )
        self._ctx = stdio_client(params)
        read, write = await self._ctx.__aenter__()
        self._session_ctx = ClientSession(read, write)
        self.session = await self._session_ctx.__aenter__()
        await self.session.initialize()

        tool_list = await self.session.list_tools()
        self.openai_tools = []
        for t in tool_list.tools:
            schema = getattr(t, "input_schema", getattr(t, "inputSchema", {}))
            self.openai_tools.append({
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": schema or {"type": "object", "properties": {}},
                },
            })
        logger.info(
            "MCP Server initialized. Discovered %d tools: %s",
            len(self.openai_tools),
            [t["function"]["name"] for t in self.openai_tools],
        )

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """Call a tool through MCP session and return string result."""
        if not self.session:
            return "Lỗi: MCP Session chưa được khởi tạo."
        async with self._lock:
            try:
                res = await self.session.call_tool(name, arguments)
                texts = []
                for c in res.content:
                    if hasattr(c, "text"):
                        texts.append(c.text)
                    elif isinstance(c, dict) and "text" in c:
                        texts.append(c["text"])
                return "\n".join(texts) if texts else str(res)
            except Exception as exc:
                logger.error("Error executing tool %s: %s", name, exc)
                return f"Lỗi khi thực thi công cụ '{name}': {exc}"

    async def stop(self) -> None:
        logger.info("Stopping MCP stdio server process...")
        try:
            if self._session_ctx:
                await self._session_ctx.__aexit__(None, None, None)
            if self._ctx:
                await self._ctx.__aexit__(None, None, None)
        except Exception as exc:
            logger.warning("Error during MCP shutdown: %s", exc)


mcp_manager = MCPClientManager(MCP_SERVER_SCRIPT)
http_client: Optional[httpx.AsyncClient] = None
MCP_ENDPOINT = os.getenv("MCP_ENDPOINT", "").strip()
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "console_state.json")
CONSOLE_HTML_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "console.html")

ALL_TOOL_NAMES = [
    "get_current_time",
    "get_weather",
    "list_iot_devices",
    "get_sensor_data",
    "get_dht20_environment",
    "device_control",
]

DEFAULT_AGENTS: List[Dict[str, Any]] = [
    {
        "id": "xiaozhi-home",
        "name": "XiaoZhi Quản Gia Nhà Thông Minh",
        "role": "Quản gia IoT & Điều khiển Thiết bị",
        "model": OLLAMA_MODEL,
        "voice": "vi_VN-vais1000-medium",
        "temperature": 0.7,
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
        "enabled_tools": list(ALL_TOOL_NAMES),
    },
    {
        "id": "xiaozhi-lab",
        "name": "Chuyên Gia Giám Sát CoreIoT Lab",
        "role": "Phân tích cảm biến DHT20 & LAB1 trên ThingsBoard",
        "model": OLLAMA_MODEL,
        "voice": "vi_VN-vais1000-medium",
        "temperature": 0.3,
        "system_prompt": (
            "Bạn là kỹ sư giám sát trạm IoT trên nền tảng CoreIoT ThingsBoard. "
            "Khi người dùng hỏi về thiết bị hoặc cảm biến (như DHT20, LAB1_2414100), "
            "hãy dùng công cụ list_iot_devices hoặc get_sensor_data để báo cáo chính xác thông số và đưa ra nhận xét ngắn gọn."
        ),
        "enabled_tools": ["list_iot_devices", "get_sensor_data", "get_dht20_environment", "device_control", "get_current_time"],
    },
    {
        "id": "xiaozhi-companion",
        "name": "Trợ Lý Gia Đình Thân Thiện",
        "role": "Trò chuyện, thời tiết & giải đáp kiến thức",
        "model": OLLAMA_MODEL,
        "voice": "vi_VN-vais1000-medium",
        "temperature": 0.8,
        "system_prompt": (
            "Bạn là người bạn đồng hành vui vẻ trong gia đình. "
            "Trả lời bằng tiếng Việt ấm áp, dí dỏm, ngắn gọn (1-2 câu) phù hợp để phát qua loa."
        ),
        "enabled_tools": ["get_current_time", "get_weather"],
    },
]

console_state: Dict[str, Any] = {
    "active_agent_id": "xiaozhi-home",
    "agents": list(DEFAULT_AGENTS),
}
recent_logs: List[Dict[str, Any]] = []


def _load_state() -> None:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data.get("agents"), list) and data["agents"]:
                    console_state["agents"] = data["agents"]
                if data.get("active_agent_id"):
                    console_state["active_agent_id"] = data["active_agent_id"]
                if isinstance(data.get("coreiot"), dict):
                    configure_coreiot(**data["coreiot"])
        except Exception as exc:
            logger.warning("Could not load console_state.json: %s", exc)


def _save_state() -> None:
    try:
        cfg = get_coreiot_config()
        payload = {
            "active_agent_id": console_state["active_agent_id"],
            "agents": console_state["agents"],
            "coreiot": {
                "url": cfg["url"],
                "public_id": cfg["public_id"],
                "dashboard_id": cfg["dashboard_id"],
                "device_token": cfg["device_token"],
            },
        }
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.warning("Could not save console_state.json: %s", exc)


def _get_agent(agent_id: Optional[str] = None) -> Dict[str, Any]:
    target_id = agent_id or console_state.get("active_agent_id") or "xiaozhi-home"
    for a in console_state["agents"]:
        if a["id"] == target_id:
            return a
    return console_state["agents"][0]


def _append_log(entry: Dict[str, Any]) -> None:
    recent_logs.insert(0, entry)
    del recent_logs[30:]


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    _load_state()
    http_client = httpx.AsyncClient(timeout=120.0)
    await mcp_manager.start()
    pipe_task = None
    if MCP_ENDPOINT:
        from services.mcp_pipe import run_pipe
        pipe_task = asyncio.create_task(run_pipe(MCP_ENDPOINT, MCP_SERVER_SCRIPT))
    yield
    if pipe_task:
        pipe_task.cancel()
    await mcp_manager.stop()
    if http_client:
        await http_client.aclose()


app = FastAPI(
    title="XiaoZhi MCP Agent Gateway",
    description="Bridge connecting XiaoZhi ESP32, FastMCP tools, and Ollama",
    version="1.0.0",
    lifespan=lifespan,
)


def verify_api_key(authorization: Optional[str] = Header(None)) -> None:
    if not API_KEY:
        return
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    elif authorization:
        token = authorization.strip()

    if token != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "Invalid or missing API Key"},
        )


@app.get("/console", response_class=HTMLResponse)
async def serve_console():
    if os.path.exists(CONSOLE_HTML_FILE):
        with open(CONSOLE_HTML_FILE, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Console UI file not found</h1>", status_code=404)


@app.get("/api/console/state")
async def get_console_state(authorization: Optional[str] = Header(None)):
    verify_api_key(authorization)
    return {
        "active_agent_id": console_state["active_agent_id"],
        "agents": console_state["agents"],
        "available_tools": mcp_manager.openai_tools,
        "coreiot": get_coreiot_config(),
        "logs": recent_logs,
    }


@app.post("/api/console/agents")
async def save_agent(request: Request, authorization: Optional[str] = Header(None)):
    verify_api_key(authorization)
    body = await request.json()
    agent_id = (body.get("id") or f"agent-{uuid.uuid4().hex[:6]}").strip()
    agent_data = {
        "id": agent_id,
        "name": (body.get("name") or "Agent Mới").strip(),
        "role": (body.get("role") or "Trợ lý thông minh").strip(),
        "model": (body.get("model") or OLLAMA_MODEL).strip(),
        "voice": (body.get("voice") or "vi_VN-vais1000-medium").strip(),
        "temperature": float(body.get("temperature", 0.7)),
        "system_prompt": (body.get("system_prompt") or DEFAULT_SYSTEM_PROMPT).strip(),
        "enabled_tools": body.get("enabled_tools") if isinstance(body.get("enabled_tools"), list) else list(ALL_TOOL_NAMES),
    }
    updated = False
    for idx, existing in enumerate(console_state["agents"]):
        if existing["id"] == agent_id:
            console_state["agents"][idx] = agent_data
            updated = True
            break
    if not updated:
        console_state["agents"].append(agent_data)
    if body.get("set_active"):
        console_state["active_agent_id"] = agent_id
    _save_state()
    return {"status": "ok", "agent": agent_data, "active_agent_id": console_state["active_agent_id"]}


@app.post("/api/console/agents/activate")
async def activate_agent(request: Request, authorization: Optional[str] = Header(None)):
    verify_api_key(authorization)
    body = await request.json()
    agent_id = body.get("agent_id", "").strip()
    if any(a["id"] == agent_id for a in console_state["agents"]):
        console_state["active_agent_id"] = agent_id
        _save_state()
        return {"status": "ok", "active_agent_id": agent_id}
    raise HTTPException(status_code=404, detail="Agent not found")


@app.delete("/api/console/agents/{agent_id}")
async def delete_agent(agent_id: str, authorization: Optional[str] = Header(None)):
    verify_api_key(authorization)
    if len(console_state["agents"]) <= 1:
        raise HTTPException(status_code=400, detail="Phải giữ lại ít nhất 1 Agent.")
    console_state["agents"] = [a for a in console_state["agents"] if a["id"] != agent_id]
    if console_state["active_agent_id"] == agent_id:
        console_state["active_agent_id"] = console_state["agents"][0]["id"]
    _save_state()
    return {"status": "ok", "active_agent_id": console_state["active_agent_id"]}


@app.get("/api/console/iot")
async def get_console_iot(refresh: bool = False, authorization: Optional[str] = Header(None)):
    verify_api_key(authorization)
    data = await asyncio.to_thread(fetch_iot_dashboard_data, refresh)
    return data


@app.post("/api/console/coreiot")
async def update_console_coreiot(request: Request, authorization: Optional[str] = Header(None)):
    verify_api_key(authorization)
    body = await request.json()
    configure_coreiot(
        url=body.get("url"),
        public_id=body.get("public_id"),
        dashboard_id=body.get("dashboard_id"),
        device_token=body.get("device_token"),
    )
    _save_state()
    data = await asyncio.to_thread(fetch_iot_dashboard_data, True)
    return data


@app.post("/api/console/iot/control")
async def control_console_iot(request: Request, authorization: Optional[str] = Header(None)):
    verify_api_key(authorization)
    body = await request.json()
    dev = body.get("device_name", "den_phong_khach")
    act = body.get("action", "on")
    msg = await asyncio.to_thread(tb_device_control, dev, act)
    return {"status": "ok", "message": msg, "controls": fetch_iot_dashboard_data(False)["controls"]}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "mcp-gateway",
        "ollama_url": OLLAMA_URL,
        "ollama_model": OLLAMA_MODEL,
        "active_agent_id": console_state["active_agent_id"],
        "agents_count": len(console_state["agents"]),
        "tools_count": len(mcp_manager.openai_tools),
        "tools": [t["function"]["name"] for t in mcp_manager.openai_tools],
    }


@app.get("/v1/tools")
async def get_tools(authorization: Optional[str] = Header(None)):
    verify_api_key(authorization)
    return {"tools": mcp_manager.openai_tools}


@app.post("/v1/chat/completions")
@app.post("/api/agent")
async def chat_completions(request: Request, authorization: Optional[str] = Header(None)):
    verify_api_key(authorization)

    body = await request.json()
    agent = _get_agent(body.get("agent_id"))
    model = body.get("model") or agent.get("model") or OLLAMA_MODEL
    stream_requested = bool(body.get("stream", False))
    temperature = body.get("temperature", agent.get("temperature", 0.7))

    # Standardize messages
    raw_messages = body.get("messages")
    if not raw_messages:
        prompt = body.get("prompt") or body.get("text", "")
        raw_messages = [{"role": "user", "content": prompt}]

    user_text = next((m.get("content", "") for m in reversed(raw_messages) if m.get("role") == "user"), "")

    # Ensure system prompt exists (from selected Agent profile)
    messages = list(raw_messages)
    has_system = any(m.get("role") == "system" for m in messages)
    if not has_system:
        messages.insert(0, {"role": "system", "content": agent.get("system_prompt") or DEFAULT_SYSTEM_PROMPT})

    # Filter tools enabled for this Agent
    enabled_names = set(agent.get("enabled_tools") or ALL_TOOL_NAMES)
    agent_tools = [
        t for t in mcp_manager.openai_tools
        if t.get("function", {}).get("name") in enabled_names
    ]

    # 1. Turn 1: Inference with Tools
    t0 = time.perf_counter()
    turn1_payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,  # Turn 1 must inspect tool_calls
    }
    if agent_tools:
        turn1_payload["tools"] = agent_tools

    try:
        resp = await http_client.post(
            f"{OLLAMA_URL}/v1/chat/completions",
            json=turn1_payload,
        )
        resp.raise_for_status()
        turn1_data = resp.json()
    except Exception as exc:
        logger.error("Failed to connect to Ollama at %s: %s", OLLAMA_URL, exc)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "error": {
                    "message": f"Ollama connection error: {exc}",
                    "type": "upstream_error",
                }
            },
        )

    t_inf1 = (time.perf_counter() - t0) * 1000
    choice = turn1_data.get("choices", [{}])[0]
    message = choice.get("message", {})
    tool_calls = message.get("tool_calls") or []

    # Case A: No tool calls -> Return direct natural response
    if not tool_calls:
        t_total = (time.perf_counter() - t0) * 1000
        logger.info(
            "[Latency] ⚡ Direct inference: %.1fms | Total: %.1fms (No tool invoked)",
            t_inf1,
            t_total,
        )

        content = message.get("content", "")
        _append_log({
            "ts": time.strftime("%H:%M:%S"),
            "agent_id": agent["id"],
            "agent_name": agent["name"],
            "user": user_text,
            "tools": [],
            "reply": content,
            "total_ms": round(t_total, 1),
        })
        if stream_requested:
            return StreamingResponse(
                _stream_openai_text(content, model),
                media_type="text/event-stream",
            )
        return JSONResponse(content=turn1_data)

    # Case B: Tool call triggered -> Dispatch to MCP Server
    logger.info("[MCP] 🛠️ Model requested %d tool call(s): %s", len(tool_calls), [tc.get("function", {}).get("name") for tc in tool_calls])

    updated_messages = list(messages)
    updated_messages.append({
        "role": "assistant",
        "content": message.get("content") or "",
        "tool_calls": tool_calls,
    })

    t_tool_total = 0.0
    executed_tools: List[Dict[str, Any]] = []
    for tc in tool_calls:
        func = tc.get("function", {})
        tool_name = func.get("name", "")
        raw_args = func.get("arguments", {})
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args)
            except Exception:
                args = {}
        else:
            args = raw_args

        t_tool_start = time.perf_counter()
        tool_res = await mcp_manager.call_tool(tool_name, args)
        t_tool_ms = (time.perf_counter() - t_tool_start) * 1000
        t_tool_total += t_tool_ms
        executed_tools.append({
            "name": tool_name,
            "args": args,
            "result": tool_res,
            "ms": round(t_tool_ms, 1),
        })

        logger.info(
            "[Tool Call] 🔧 '%s'(args=%s) -> '%s' (%.1fms)",
            tool_name,
            args,
            tool_res,
            t_tool_ms,
        )

        updated_messages.append({
            "role": "tool",
            "tool_call_id": tc.get("id", f"call_{uuid.uuid4().hex[:8]}"),
            "name": tool_name,
            "content": tool_res,
        })

    # 2. Turn 2: Follow-up inference with tool results to synthesize natural answer
    t_inf2_start = time.perf_counter()
    turn2_payload = {
        "model": model,
        "messages": updated_messages,
        "temperature": temperature,
        "stream": stream_requested,
    }

    if stream_requested:
        # Stream response back to client (XiaoZhi / Piper TTS)
        t_prep_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "[Latency] 🚀 Streaming Turn 2: inf1=%.1fms | tool=%.1fms | prep=%.1fms",
            t_inf1,
            t_tool_total,
            t_prep_ms,
        )
        return StreamingResponse(
            _proxy_stream_ollama(turn2_payload),
            media_type="text/event-stream",
        )

    try:
        resp2 = await http_client.post(
            f"{OLLAMA_URL}/v1/chat/completions",
            json=turn2_payload,
        )
        resp2.raise_for_status()
        turn2_data = resp2.json()
    except Exception as exc:
        logger.error("Failed on Turn 2 Ollama inference: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"error": {"message": f"Ollama Turn 2 error: {exc}"}},
        )

    t_inf2 = (time.perf_counter() - t_inf2_start) * 1000
    t_total = (time.perf_counter() - t0) * 1000

    final_content = (
        turn2_data.get("choices", [{}])[0].get("message", {}).get("content", "")
    )
    logger.info(
        "[Latency] ✅ Pipeline complete: inf1=%.1fms | tool=%.1fms | inf2=%.1fms | Total=%.1fms",
        t_inf1,
        t_tool_total,
        t_inf2,
        t_total,
    )
    logger.info("[Response] 🗣️ XiaoZhi: %s", final_content)
    _append_log({
        "ts": time.strftime("%H:%M:%S"),
        "agent_id": agent["id"],
        "agent_name": agent["name"],
        "user": user_text,
        "tools": executed_tools,
        "reply": final_content,
        "total_ms": round(t_total, 1),
    })

    return JSONResponse(
        content=turn2_data,
        headers={
            "X-Latency-Inf1-Ms": f"{t_inf1:.1f}",
            "X-Latency-Tool-Ms": f"{t_tool_total:.1f}",
            "X-Latency-Inf2-Ms": f"{t_inf2:.1f}",
            "X-Latency-Total-Ms": f"{t_total:.1f}",
        },
    )


async def _stream_openai_text(content: str, model: str):
    """Yield simulated OpenAI-compatible SSE chunks for plain text."""
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"content": content},
                "finish_reason": "stop",
            }
        ],
    }
    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


async def _proxy_stream_ollama(payload: Dict[str, Any]):
    """Proxy streaming SSE chunks from Ollama directly to client."""
    async with http_client.stream(
        "POST",
        f"{OLLAMA_URL}/v1/chat/completions",
        json=payload,
    ) as upstream_resp:
        async for line in upstream_resp.aiter_lines():
            if line:
                yield f"{line}\n\n"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
