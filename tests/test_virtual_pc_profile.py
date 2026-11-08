#!/usr/bin/env python3
"""
Test Suite for Virtual PC Tester Profile (agent_103: Aero).
Verifies:
1. End-to-end management API resolution for Virtual PC MAC (02:00:00:00:00:01).
2. Static test client availability at http://localhost:8005/test/test_page.html.
3. WebSocket handshake and session creation for the PC virtual device.
"""

import asyncio
import json
import urllib.request
import websockets

BRIDGE_URL = "http://localhost:8005"
XIAOZHI_WS_URL = "ws://localhost:8002/xiaozhi/v1/"
VIRTUAL_PC_MAC = "02:00:00:00:00:01"


def test_virtual_pc_profile_api():
    print("[1/3] Testing Virtual PC Profile Resolution via Management API...")
    payload = json.dumps({"macAddress": VIRTUAL_PC_MAC, "clientId": "pc-client-test"}).encode()
    req = urllib.request.Request(
        f"{BRIDGE_URL}/config/agent-models",
        data=payload,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        res = json.loads(r.read())
        assert res["code"] == 0
        data = res["data"]
        assert data["agent_id"] == "agent_103"
        assert data["role"] == "Aero"
        assert "Aero" in data["prompt"]
        assert data["TTS"]["OpenAITTS"]["voice"] == "vi_female_linh"
        assert data["tool_policy"] == "full_control"
        print(f"  ✓ Resolved agent_103 (Role: {data['role']}) for MAC {VIRTUAL_PC_MAC}")


def test_static_web_client_served():
    print("[2/3] Testing Static Web Client Availability...")
    url = f"{BRIDGE_URL}/test/test_page.html"
    with urllib.request.urlopen(url, timeout=5) as r:
        assert r.status == 200
        content = r.read().decode("utf-8")
        assert "test_page" in content
        print(f"  ✓ Web test page accessible at {url}")


async def test_websocket_handshake():
    print("[3/3] Testing WebSocket Handshake for Virtual PC Device...")
    headers = {
        "Device-Id": VIRTUAL_PC_MAC,
        "Client-Id": "virtual_pc_client",
        "Authorization": "Bearer sk-local",
        "Protocol-Version": "1"
    }
    async with websockets.connect(XIAOZHI_WS_URL, additional_headers=headers) as ws:
        hello_frame = {
            "type": "hello",
            "version": 1,
            "transport": "websocket",
            "audio_params": {
                "format": "opus",
                "sample_rate": 16000,
                "channels": 1,
                "frame_duration": 60
            }
        }
        await ws.send(json.dumps(hello_frame))
        resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
        data = json.loads(resp)
        assert data["type"] == "hello"
        assert data.get("session_id")
        print(f"  ✓ Connected and established Session ID: {data['session_id']}")


def main():
    test_virtual_pc_profile_api()
    test_static_web_client_served()
    asyncio.run(test_websocket_handshake())
    print("\nVirtual PC Profile & Web Client verification SUCCESSFUL!\n")


if __name__ == "__main__":
    main()
