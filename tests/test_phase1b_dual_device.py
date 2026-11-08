#!/usr/bin/env python3
"""
Phase 1B: Multi-Agent Profile Isolation & Dual-Device Validation Test Harness.

Verifies:
1. Concurrent virtual device connections to XiaoZhi ESP32 WebSocket runtime.
2. Independent session ID generation and protocol handshake.
3. End-to-end Management API configuration flow (/config/server-base & /config/agent-models).
4. Strict MAC-to-Agent Profile resolution & MAC address normalization.
5. Zero cross-profile leakage under concurrent parallel querying.
6. Reconnection resilience and unknown-device fallback behavior.
"""

import asyncio
import json
import logging
import sys
import time
import urllib.request
import websockets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("phase1b_test")

BRIDGE_HTTP_URL = "http://localhost:8005"
XIAOZHI_WS_URL = "ws://localhost:8002/xiaozhi/v1/"

MAC_NOVA = "48:27:E2:B1:5A:1C"
MAC_LUNA = "00:11:22:33:44:55"
MAC_UNKNOWN = "DE:AD:BE:EF:99:88"


def query_bridge_agent_models(mac_address: str, client_id: str) -> dict:
    """Invokes the upstream management endpoint /config/agent-models."""
    payload = json.dumps({"macAddress": mac_address, "clientId": client_id}).encode("utf-8")
    req = urllib.request.Request(
        f"{BRIDGE_HTTP_URL}/config/agent-models",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": "Bearer sk-local"},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200
        return json.loads(resp.read().decode("utf-8"))


def test_management_api_contracts():
    """Validates baseline and agent configuration contracts."""
    logger.info("=== Step 1: Testing Management API Contracts ===")

    # Ensure test bindings for Phase 1B exist
    for mac, ag_id, name in [(MAC_NOVA, "agent_101", "Nova Box"), (MAC_LUNA, "agent_102", "Luna Box")]:
        b_req = urllib.request.Request(
            f"{BRIDGE_HTTP_URL}/api/devices/bind",
            data=json.dumps({"mac_address": mac, "agent_id": ag_id, "device_name": name}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            urllib.request.urlopen(b_req, timeout=5)
        except Exception:
            pass

    # 1. Base Server Config
    req = urllib.request.Request(
        f"{BRIDGE_HTTP_URL}/config/server-base",
        data=b"{}",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        base_cfg = json.loads(resp.read().decode("utf-8"))
        assert base_cfg.get("code") == 0
        assert "server" in base_cfg["data"]
        assert "ASR" in base_cfg["data"]
        assert "TTS" in base_cfg["data"]
        assert "LLM" in base_cfg["data"]
        logger.info("  ✓ /config/server-base returned compliant service schema")

    # 2. Agent Profile Resolution for Nova
    nova_cfg = query_bridge_agent_models(MAC_NOVA, "client-nova-01")
    assert nova_cfg.get("code") == 0, f"Failed for Nova: {nova_cfg}"
    data_nova = nova_cfg["data"]
    assert data_nova["agent_id"] == "agent_101", f"Expected agent_101, got {data_nova.get('agent_id')}"
    assert data_nova["role"] == "Nova", f"Expected Nova, got {data_nova.get('role')}"
    assert "Nova" in data_nova["prompt"]
    assert data_nova["TTS"]["OpenAITTS"]["voice"] == "vi_female_linh"
    assert data_nova["tool_policy"] == "full_control"
    logger.info("  ✓ /config/agent-models resolved Nova (agent_101) for %s", MAC_NOVA)

    # 3. Agent Profile Resolution for Luna
    luna_cfg = query_bridge_agent_models(MAC_LUNA, "client-luna-01")
    assert luna_cfg.get("code") == 0, f"Failed for Luna: {luna_cfg}"
    data_luna = luna_cfg["data"]
    assert data_luna["agent_id"] == "agent_102", f"Expected agent_102, got {data_luna.get('agent_id')}"
    assert data_luna["role"] == "Luna", f"Expected Luna, got {data_luna.get('role')}"
    assert "Luna" in data_luna["prompt"]
    assert data_luna["TTS"]["OpenAITTS"]["voice"] == "en_US-lessac-medium"
    assert data_luna["tool_policy"] == "read_only_telemetry"
    logger.info("  ✓ /config/agent-models resolved Luna (agent_102) for %s", MAC_LUNA)

    # 4. Profile Isolation Assertion
    assert data_nova["agent_id"] != data_luna["agent_id"]
    assert data_nova["prompt"] != data_luna["prompt"]
    assert data_nova["TTS"]["OpenAITTS"]["voice"] != data_luna["TTS"]["OpenAITTS"]["voice"]
    assert data_nova["tool_policy"] != data_luna["tool_policy"]
    logger.info("  ✓ Static profile isolation verified between Nova and Luna")


def test_mac_normalization():
    """Verifies various MAC formats (lowercase, hyphenated, no delimiters) resolve accurately."""
    logger.info("=== Step 2: Testing MAC Normalization ===")
    test_cases = [
        ("48:27:E2:B1:5A:1C", "agent_101", "Nova"),
        ("48-27-e2-b1-5a-1c", "agent_101", "Nova"),
        ("4827e2b15a1c", "agent_101", "Nova"),
        ("00:11:22:33:44:55", "agent_102", "Luna"),
        ("00-11-22-33-44-55", "agent_102", "Luna"),
        ("001122334455", "agent_102", "Luna"),
    ]
    for raw_mac, expected_id, expected_role in test_cases:
        res = query_bridge_agent_models(raw_mac, f"client-{raw_mac}")
        assert res.get("code") == 0
        assert res["data"]["agent_id"] == expected_id, f"MAC '{raw_mac}' resolved to {res['data'].get('agent_id')}, expected {expected_id}"
        assert res["data"]["role"] == expected_role
        logger.info("  ✓ Normalized MAC format '%s' -> %s (%s)", raw_mac, expected_id, expected_role)


async def simulate_esp32_device(
    device_name: str,
    mac_address: str,
    client_id: str,
    hold_duration_sec: float = 1.5,
) -> dict:
    """
    Connects a virtual ESP32 device to XiaoZhi server, sends 'hello' handshake frame,
    and maintains the connection while verifying session generation.
    """
    headers = {
        "Device-Id": mac_address,
        "Client-Id": client_id,
        "Authorization": "Bearer sk-local",
        "Protocol-Version": "1",
    }
    logger.info("[%s] Connecting to %s with MAC %s...", device_name, XIAOZHI_WS_URL, mac_address)

    async with websockets.connect(XIAOZHI_WS_URL, additional_headers=headers) as ws:
        hello_frame = {
            "type": "hello",
            "version": 1,
            "transport": "websocket",
            "audio_params": {
                "format": "opus",
                "sample_rate": 16000,
                "channels": 1,
                "frame_duration": 60,
            },
        }
        await ws.send(json.dumps(hello_frame))
        raw_resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
        handshake_data = json.loads(raw_resp)

        session_id = handshake_data.get("session_id")
        logger.info("[%s] Handshake complete! Assigned session_id: %s", device_name, session_id)

        # Hold connection open to simulate concurrent active runtime session
        await asyncio.sleep(hold_duration_sec)

        return {
            "device": device_name,
            "mac": mac_address,
            "session_id": session_id,
            "response": handshake_data,
        }


async def test_concurrent_sessions():
    """Exercises two virtual ESP32 devices connecting simultaneously."""
    logger.info("=== Step 3: Testing Concurrent Device Sessions ===")

    task_nova = asyncio.create_task(
        simulate_esp32_device("Device-Nova", MAC_NOVA, "esp32-nova-01", hold_duration_sec=2.0)
    )
    task_luna = asyncio.create_task(
        simulate_esp32_device("Device-Luna", MAC_LUNA, "esp32-luna-01", hold_duration_sec=2.0)
    )

    res_nova, res_luna = await asyncio.gather(task_nova, task_luna)

    # Assertions
    assert res_nova["session_id"], "Nova session ID must not be empty"
    assert res_luna["session_id"], "Luna session ID must not be empty"
    assert res_nova["session_id"] != res_luna["session_id"], (
        f"Session collision detected: {res_nova['session_id']} vs {res_luna['session_id']}"
    )

    logger.info("  ✓ Concurrent sessions established independently:")
    logger.info("    - Device Nova (MAC %s) -> Session: %s", MAC_NOVA, res_nova["session_id"])
    logger.info("    - Device Luna (MAC %s) -> Session: %s", MAC_LUNA, res_luna["session_id"])


async def test_concurrency_leakage(iterations: int = 20):
    """Fires interleaved parallel management queries to verify zero cross-talk under load."""
    logger.info("=== Step 4: Testing Concurrency Isolation & Cross-Profile Leakage (%d iterations) ===", iterations)

    loop = asyncio.get_running_loop()

    async def fetch_async(mac: str, expected_agent: str, expected_role: str):
        res = await loop.run_in_executor(None, query_bridge_agent_models, mac, f"leakage-test-{mac}")
        data = res.get("data", {})
        if data.get("agent_id") != expected_agent or data.get("role") != expected_role:
            raise ValueError(
                f"Cross-profile leakage detected! MAC {mac} returned agent {data.get('agent_id')} / role {data.get('role')}"
            )
        return True

    tasks = []
    for i in range(iterations):
        tasks.append(fetch_async(MAC_NOVA, "agent_101", "Nova"))
        tasks.append(fetch_async(MAC_LUNA, "agent_102", "Luna"))

    results = await asyncio.gather(*tasks)
    assert len(results) == iterations * 2
    assert all(results)
    logger.info("  ✓ Successfully completed %d interleaved queries without cross-profile leakage", len(results))


async def test_reconnection_and_unknown_device():
    """Tests session re-connection for known device and auto-handling of unknown device."""
    logger.info("=== Step 5: Testing Reconnection and Unknown-Device Handling ===")

    # 1. Reconnection
    logger.info("  Connecting Device-Nova initially...")
    first_conn = await simulate_esp32_device("Device-Nova-1st", MAC_NOVA, "esp32-nova-recon", hold_duration_sec=0.5)
    logger.info("  Reconnecting Device-Nova...")
    second_conn = await simulate_esp32_device("Device-Nova-2nd", MAC_NOVA, "esp32-nova-recon", hold_duration_sec=0.5)

    assert first_conn["session_id"] != second_conn["session_id"], "New connection must receive a fresh session ID"
    logger.info("  ✓ Device reconnection successful; cleanly assigned fresh session ID %s", second_conn["session_id"])

    # 2. Unknown Device Handling
    logger.info("  Testing unknown device MAC %s...", MAC_UNKNOWN)
    unknown_res = query_bridge_agent_models(MAC_UNKNOWN, "esp32-unknown-01")
    assert unknown_res.get("code") == 0, f"Expected successful fallback, got {unknown_res}"
    # Unknown device auto-binds to primary default agent without error
    assert unknown_res["data"]["agent_id"] == "agent_101"
    logger.info("  ✓ Unknown device smoothly handled via default agent fallback (%s)", unknown_res["data"]["role"])

    # Connect unknown device via WebSocket
    unknown_conn = await simulate_esp32_device("Device-Unknown", MAC_UNKNOWN, "esp32-unknown-01", hold_duration_sec=0.5)
    assert unknown_conn["session_id"]
    logger.info("  ✓ Unknown device connected and established session %s", unknown_conn["session_id"])


async def main_async():
    logger.info("Starting Phase 1B Automated Verification Suite")
    start = time.time()

    test_management_api_contracts()
    test_mac_normalization()
    await test_concurrent_sessions()
    await test_concurrency_leakage(iterations=25)
    await test_reconnection_and_unknown_device()

    # Clean up test MACs
    for mac in [MAC_NOVA, MAC_LUNA, MAC_UNKNOWN]:
        u_req = urllib.request.Request(
            f"{BRIDGE_HTTP_URL}/api/devices/unbind",
            data=json.dumps({"mac_address": mac}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        try:
            urllib.request.urlopen(u_req, timeout=5)
        except Exception:
            pass

    elapsed = time.time() - start
    logger.info("=================================================================")
    logger.info("PHASE 1B ALL TESTS PASSED SUCCESSFULLY in %.2f seconds!", elapsed)
    logger.info("=================================================================")


def main():
    try:
        asyncio.run(main_async())
    except Exception as e:
        logger.exception("Phase 1B verification FAILED: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
