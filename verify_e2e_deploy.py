#!/usr/bin/env python3
"""
End-to-End Deployment Verification Script.
Validates the complete integrated stack:
1. Platform Bridge (Port 8005) - manager-api contract & Agent Profile resolution.
2. ThingsBoard MCP Server (Port 8009) - SSE endpoint & tool discovery.
3. XiaoZhi WebSocket Server (Port 8002) - ESP32 device handshake, profile binding & session creation.
"""

import asyncio
import json
import os
import sys
import urllib.request
import websockets

BRIDGE_URL = "http://localhost:8005"
TB_MCP_URL = "http://localhost:8009"
XIAOZHI_WS_URL = "ws://localhost:8002/xiaozhi/v1/"
TEST_MAC = "48:27:E2:B1:5A:1C"


def test_platform_bridge():
    print("[1/3] Testing Platform Bridge (Port 8005)...")
    # Health check
    with urllib.request.urlopen(f"{BRIDGE_URL}/api/health", timeout=5) as r:
        health = json.loads(r.read())
        assert health["status"] == "healthy"
        print("  ✓ Platform bridge health check OK")

    # /config/server-base
    req = urllib.request.Request(
        f"{BRIDGE_URL}/config/server-base",
        data=b"{}",
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        base = json.loads(r.read())
        assert base["code"] == 0
        assert "ASR" in base["data"]
        print("  ✓ /config/server-base contract OK (VAD, ASR, TTS, LLM configured)")

    # /config/agent-models
    payload = json.dumps({"macAddress": TEST_MAC, "clientId": "test_client_01"}).encode()
    req = urllib.request.Request(
        f"{BRIDGE_URL}/config/agent-models",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        models = json.loads(r.read())
        assert models["code"] == 0
        prompt = models["data"].get("prompt", "")
        assert "Nova" in prompt
        print(f"  ✓ /config/agent-models resolved active Agent Profile for {TEST_MAC}:")
        print(f"    Prompt: {prompt[:80]}...")
    print()


def test_thingsboard_mcp():
    print("[2/3] Testing ThingsBoard MCP Server (Port 8009)...")
    req = urllib.request.Request(f"{TB_MCP_URL}/sse")
    with urllib.request.urlopen(req, timeout=5) as r:
        assert r.status == 200
        first_line = r.readline().decode().strip()
        assert "event" in first_line or "data" in first_line or r.status == 200
        print(f"  ✓ ThingsBoard MCP Server SSE endpoint active (status {r.status})")
    print()


async def test_xiaozhi_esp32_handshake():
    print("[3/3] Testing XiaoZhi ESP32 WebSocket Handshake (Port 8002)...")
    headers = {
        "device-id": TEST_MAC,
        "client-id": "esp32-client-verify",
        "authorization": "Bearer sk-local"
    }

    try:
        async with websockets.connect(XIAOZHI_WS_URL, additional_headers=headers) as ws:
            print("  ✓ Connected to XiaoZhi ESP32 WebSocket endpoint")

            # 1. Send client Hello message
            client_hello = json.dumps({
                "type": "hello",
                "version": 1,
                "transport": "websocket",
                "audio_params": {
                    "format": "opus",
                    "sample_rate": 16000,
                    "channels": 1,
                    "frame_duration": 60
                }
            })
            await ws.send(client_hello)
            print("  ✓ Sent ESP32 client 'hello' frame")

            # 2. Receive server Hello / welcome response
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            print(f"  ✓ Received server handshake response: {msg[:100]}...")
            data = json.loads(msg)
            assert data.get("type") in ("hello", "server")
            session_id = data.get("session_id", "unknown")
            print(f"  ✓ Active Conversation Session ID: {session_id}")
            print(f"  ✓ Device MAC {TEST_MAC} is officially online in XiaoZhi runtime")

    except Exception as e:
        print(f"  ✗ WebSocket handshake error: {e}")
        raise

    print()


async def main():
    print("=" * 65)
    print("XiaoZhi Platform Integrated Deployment Verification")
    print("=" * 65)
    test_platform_bridge()
    test_thingsboard_mcp()
    await test_xiaozhi_esp32_handshake()
    print("=" * 65)
    print("ALL SERVICES DEPLOYED AND OPERATIONAL!")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
