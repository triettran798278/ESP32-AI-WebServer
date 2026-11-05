"""
WebSocket <-> Stdio MCP Pipe for https://xiaozhi.me/console/agents.
Bridges local FastMCP server (services/mcp_server.py) directly to XiaoZhi Cloud Agent MCP Endpoint.
"""
import asyncio
import logging
import os
import sys

import websockets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] mcp_pipe: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mcp_pipe")

SERVER_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server.py")


async def run_pipe(endpoint_url: str, script_path: str = SERVER_SCRIPT) -> None:
    backoff = 2
    while True:
        proc = None
        try:
            logger.info("Connecting to XiaoZhi MCP Endpoint: %s...", endpoint_url[:45])
            async with websockets.connect(endpoint_url, ping_interval=20, ping_timeout=20) as ws:
                logger.info("Connected to XiaoZhi Cloud Console! Spawning %s", script_path)
                backoff = 2
                proc = await asyncio.create_subprocess_exec(
                    sys.executable,
                    script_path,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=sys.stderr,
                )

                async def ws_to_stdio():
                    async for message in ws:
                        if proc.stdin:
                            data = message if isinstance(message, str) else message.decode("utf-8")
                            proc.stdin.write((data.strip() + "\n").encode("utf-8"))
                            await proc.stdin.drain()

                async def stdio_to_ws():
                    while proc.stdout and not proc.stdout.at_eof():
                        line = await proc.stdout.readline()
                        if not line:
                            break
                        text = line.decode("utf-8", errors="ignore").strip()
                        if text:
                            await ws.send(text)

                await asyncio.gather(ws_to_stdio(), stdio_to_ws())
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("MCP Pipe disconnected (%s). Retrying in %ds...", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
        finally:
            if proc and proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=3)
                except asyncio.TimeoutError:
                    proc.kill()


if __name__ == "__main__":
    endpoint = sys.argv[1] if len(sys.argv) > 1 else os.getenv("MCP_ENDPOINT", "").strip()
    if not endpoint:
        sys.exit(
            "Error: Missing MCP_ENDPOINT.\n"
            "Usage: python services/mcp_pipe.py \"wss://api.xiaozhi.me/mcp/?token=...\"\n"
            "   or: set MCP_ENDPOINT=wss://... && python services/mcp_pipe.py"
        )
    try:
        asyncio.run(run_pipe(endpoint))
    except KeyboardInterrupt:
        logger.info("Stopped by user.")
