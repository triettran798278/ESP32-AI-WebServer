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
from fastapi.responses import JSONResponse, StreamingResponse
import httpx

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
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


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "mcp-gateway",
        "ollama_url": OLLAMA_URL,
        "ollama_model": OLLAMA_MODEL,
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
    model = body.get("model") or OLLAMA_MODEL
    stream_requested = bool(body.get("stream", False))
    temperature = body.get("temperature", 0.7)

    # Standardize messages
    raw_messages = body.get("messages")
    if not raw_messages:
        # Support simple prompt or text parameter
        prompt = body.get("prompt") or body.get("text", "")
        raw_messages = [{"role": "user", "content": prompt}]

    # Ensure system prompt exists
    messages = list(raw_messages)
    has_system = any(m.get("role") == "system" for m in messages)
    if not has_system:
        messages.insert(0, {"role": "system", "content": DEFAULT_SYSTEM_PROMPT})

    # 1. Turn 1: Inference with Tools
    t0 = time.perf_counter()
    turn1_payload = {
        "model": model,
        "messages": messages,
        "tools": mcp_manager.openai_tools,
        "temperature": temperature,
        "stream": False,  # Turn 1 must inspect tool_calls
    }

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
