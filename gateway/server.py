import os
import httpx
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI(title="XiaoZhi Unified AI Gateway")

API_KEY = os.getenv("API_KEY", "sk-xiaozhi-local-secret").strip()
WHISPER_URL = os.getenv("WHISPER_URL", "http://faster-whisper:8000").rstrip("/")
PIPER_URL = os.getenv("PIPER_URL", "http://piper-tts:10200").rstrip("/")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434").rstrip("/")
MCP_GATEWAY_URL = os.getenv("MCP_GATEWAY_URL", "http://mcp-gateway:8008").rstrip("/")

client: httpx.AsyncClient = None  # type: ignore


@app.on_event("startup")
async def startup():
    global client
    client = httpx.AsyncClient(timeout=120.0)


@app.on_event("shutdown")
async def shutdown():
    if client:
        await client.aclose()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "gateway": "unified",
        "auth_required": bool(API_KEY),
        "routes": {
            "/v1/audio/transcriptions": WHISPER_URL,
            "/v1/audio/speech": PIPER_URL,
            "/tts": PIPER_URL,
            "/v1/chat/completions": MCP_GATEWAY_URL,
            "/api/agent": MCP_GATEWAY_URL,
            "/v1/*": OLLAMA_URL,
        },
    }


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"])
async def proxy_all(request: Request, path: str):
    # 1. Check API Key
    if API_KEY:
        auth_header = request.headers.get("authorization", "").strip()
        provided_key = ""
        if auth_header.startswith("Bearer "):
            provided_key = auth_header[7:].strip()
        elif "api-key" in request.headers:
            provided_key = request.headers["api-key"].strip()

        if provided_key != API_KEY:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "error": {
                        "message": "Invalid or missing API Key. Set Authorization: Bearer <API_KEY>",
                        "type": "invalid_request_error",
                        "code": "invalid_api_key",
                    }
                },
            )

    # 2. Route destination
    norm_path = f"/{path}".rstrip("/")
    if norm_path.startswith("/v1/audio/transcriptions"):
        target_base = WHISPER_URL
    elif norm_path.startswith("/v1/audio/speech") or norm_path == "/tts":
        target_base = PIPER_URL
    elif norm_path in ("/v1/chat/completions", "/api/agent"):
        target_base = MCP_GATEWAY_URL
    else:
        # Default route to Ollama (/v1/models, /api/generate, etc.)
        target_base = OLLAMA_URL

    target_url = f"{target_base}/{path}"
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"

    # 3. Filter headers to avoid HTTP hop-by-hop conflicts
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length")
    }

    # 4. Stream forward request to target
    target_req = client.build_request(
        method=request.method,
        url=target_url,
        headers=headers,
        content=request.stream(),
    )

    target_resp = await client.send(target_req, stream=True)

    # 5. Filter response headers
    res_headers = {
        k: v for k, v in target_resp.headers.items()
        if k.lower() not in ("content-length", "transfer-encoding", "content-encoding")
    }

    return StreamingResponse(
        target_resp.aiter_raw(),
        status_code=target_resp.status_code,
        headers=res_headers,
        background=target_resp.aclose,
    )
