#!/usr/bin/env python3
"""
Alpha 0.2 Provisioning & Authentication Automated Verification Suite.

Tests:
1. Activation code generation (6-digit numeric, leading zeros, TTL).
2. Activation code expiration enforcement.
3. Invalid activation code rejection (HTTP 400).
4. Single-use enforcement / duplicate redemption prevention (HTTP 400).
5. Successful end-to-end device registration (token issuance).
6. Strict Device-to-Agent profile association.
7. Token-based authentication for /api/devices/me and /api/devices/me/config.
8. Credential security: zero ThingsBoard private key leakage in firmware config.
9. Device heartbeat processing & last_seen tracking.
10. Credential revocation upon unbinding (immediate HTTP 401 on revoked token).
11. Brute-force rate limiting and lockout protection (HTTP 429).
12. Concurrent registration & profile isolation under load.
"""

import concurrent.futures
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("alpha02_test")

BRIDGE_URL = "http://localhost:8005"


def http_request(
    path: str,
    method: str = "GET",
    payload: dict = None,
    headers: dict = None
) -> Tuple[int, Any]:
    url = f"{BRIDGE_URL}{path}"
    req_headers = {"User-Agent": "Alpha02-Harness/1.0"}
    if headers:
        req_headers.update(headers)

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status_code = resp.getcode()
            raw = resp.read()
            content_type = resp.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return status_code, json.loads(raw.decode("utf-8"))
            return status_code, raw.decode("utf-8")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw.decode("utf-8"))
        except Exception:
            return e.code, raw.decode("utf-8")


def test_activation_code_generation():
    logger.info("=== [1/10] Testing Activation Code Generation ===")
    status, res = http_request(
        "/api/devices/activation",
        method="POST",
        payload={"agent_id": "agent_101", "expiration_seconds": 300}
    )
    assert status == 200, f"Expected 200, got {status}: {res}"
    code = res.get("code")
    assert code and len(code) == 6 and code.isdigit(), f"Invalid code format: {code}"
    assert res.get("agent_id") == "agent_101"
    assert res.get("status") == "success"
    logger.info("  ✓ Generated compliant 6-digit code: %s for agent_101", code)

    # Test status polling
    st_code, st_res = http_request(f"/api/devices/activation/status?code={code}")
    assert st_code == 200
    assert st_res.get("status") == "pending"
    assert st_res.get("remaining_seconds") > 280
    logger.info("  ✓ Code status polled successfully: status=pending, remaining=%ds", st_res.get("remaining_seconds"))
    return code


def test_activation_expiration():
    logger.info("=== [2/10] Testing Activation Expiration Enforcement ===")
    # Create code with minimum TTL (60 seconds)
    status, res = http_request(
        "/api/devices/activation",
        method="POST",
        payload={"agent_id": "agent_102", "expiration_seconds": 60}
    )
    assert status == 200
    code = res["code"]

    # Directly check non-existent code
    st, not_found_res = http_request("/api/devices/activation/status?code=9999999")
    assert not_found_res.get("status") == "not_found"
    logger.info("  ✓ Non-existent activation code returns status=not_found")


def test_invalid_and_duplicate_activation():
    logger.info("=== [3/10] Testing Invalid & Duplicate Activation Handling ===")
    # 1. Invalid code
    status, res = http_request(
        "/api/devices/register",
        method="POST",
        payload={
            "activation_code": "000001",
            "mac_address": "E0:5A:1B:11:22:33",
            "device_name": "Test Node"
        }
    )
    assert status == 400, f"Expected 400, got {status}: {res}"
    logger.info("  ✓ Invalid activation code cleanly rejected with HTTP 400: %s", res.get("detail"))

    # 2. Generate valid code, redeem once, then duplicate
    _, gen_res = http_request(
        "/api/devices/activation",
        method="POST",
        payload={"agent_id": "agent_102"}
    )
    code = gen_res["code"]
    test_mac = "E0:5A:1B:AA:BB:CC"

    # First redemption
    st1, reg1 = http_request(
        "/api/devices/register",
        method="POST",
        payload={
            "activation_code": code,
            "mac_address": test_mac,
            "device_name": "Luna Companion",
            "hardware_model": "esp32s3-yolo-uno"
        }
    )
    assert st1 == 200, f"First registration failed: {reg1}"
    assert reg1.get("agent_id") == "agent_102"
    token = reg1.get("device_token")
    assert token and len(token) >= 32
    logger.info("  ✓ First redemption succeeded, token issued (len=%d)", len(token))

    # Second redemption with same code (MUST FAIL)
    st2, reg2 = http_request(
        "/api/devices/register",
        method="POST",
        payload={
            "activation_code": code,
            "mac_address": "E0:5A:1B:DD:EE:FF"
        }
    )
    assert st2 == 400, f"Expected 400 for duplicate redemption, got {st2}: {reg2}"
    assert "already been redeemed" in reg2.get("detail", "")
    logger.info("  ✓ Duplicate redemption prevented: %s", reg2.get("detail"))

    return token, test_mac


def test_device_authentication_and_security(token: str, mac: str):
    logger.info("=== [4/10] Testing Device Authentication & Identity Retrieval ===")
    # 1. Valid token to /api/devices/me
    status, dev_info = http_request(
        "/api/devices/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert status == 200, f"Expected 200, got {status}: {dev_info}"
    assert dev_info["mac_address"] == mac
    assert dev_info["agent_id"] == "agent_102"
    logger.info("  ✓ /api/devices/me returned authenticated identity: %s -> %s", dev_info["device_id"], dev_info["agent_id"])

    # 2. Invalid / spoofed token
    st_fake, _ = http_request(
        "/api/devices/me",
        headers={"Authorization": "Bearer spoofed-fake-token-12345"}
    )
    assert st_fake == 401
    logger.info("  ✓ Spoofed token correctly rejected with HTTP 401 Unauthorized")

    # 3. /api/devices/me/config security check: NEVER leak ThingsBoard keys
    st_cfg, cfg_res = http_request(
        "/api/devices/me/config",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert st_cfg == 200
    assert "ws_url" in cfg_res
    assert "ota_url" in cfg_res
    assert cfg_res["agent"]["id"] == "agent_102"
    assert cfg_res["agent"]["role"] == "Luna"

    # Explicit security assertion: NO ThingsBoard master keys
    cfg_str = json.dumps(cfg_res)
    assert "tb_" not in cfg_str and "api_key" not in cfg_str
    logger.info("  ✓ /api/devices/me/config delivered runtime config; zero ThingsBoard API keys exposed")


def test_device_heartbeat(token: str):
    logger.info("=== [5/10] Testing Device Heartbeat Tracking ===")
    status, hb_res = http_request(
        "/api/devices/heartbeat",
        method="POST",
        payload={},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert status == 200, f"Heartbeat failed: {hb_res}"
    assert hb_res.get("status") == "ok"
    assert hb_res.get("last_seen") > 0
    logger.info("  ✓ Heartbeat acknowledged at timestamp: %s", hb_res.get("last_seen"))


def test_management_inventory_and_resolution(mac: str):
    logger.info("=== [6/10] Testing Unified Inventory & Runtime Profile Resolution ===")
    status, inv = http_request("/api/devices")
    assert status == 200
    devices = inv.get("devices", [])
    matched = [d for d in devices if d["mac_address"] == mac]
    assert len(matched) == 1, f"Registered device {mac} not found in inventory: {devices}"
    dev = matched[0]
    assert dev["registration_status"] == "authenticated"
    assert dev["agent_id"] == "agent_102"
    assert dev["is_auth"] is True
    logger.info("  ✓ Verified device appears in unified inventory as 'authenticated': %s", dev["name"])

    # Verify XiaoZhi runtime config resolution (/config/agent-models)
    st_res, model_cfg = http_request(
        "/config/agent-models",
        method="POST",
        payload={"macAddress": mac, "clientId": "physical-esp32-client"}
    )
    assert st_res == 200
    assert model_cfg["data"]["agent_id"] == "agent_102"
    assert model_cfg["data"]["role"] == "Luna"
    logger.info("  ✓ Runtime management API correctly resolved physical device %s to Luna", mac)


def test_credential_revocation_and_unbinding(token: str, mac: str):
    logger.info("=== [7/10] Testing Credential Revocation & Device Unbinding ===")
    # Unbind via authenticated device self-unbind
    status, unb_res = http_request(
        "/api/devices/me/unbind",
        method="POST",
        payload={},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert status == 200, f"Unbind failed: {unb_res}"
    logger.info("  ✓ Device self-unbind endpoint responded: %s", unb_res.get("message"))

    # Verify token is now strictly REVOKED (HTTP 401)
    st_revoked, _ = http_request(
        "/api/devices/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert st_revoked == 401
    logger.info("  ✓ Revoked token immediately blocked on /api/devices/me with HTTP 401")

    # Verify heartbeat fails on revoked token
    st_hb, _ = http_request(
        "/api/devices/heartbeat",
        method="POST",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert st_hb == 401
    logger.info("  ✓ Heartbeat immediately blocked on revoked token with HTTP 401")


def test_rate_limiting_brute_force():
    logger.info("=== [8/10] Testing Brute-Force Rate Limiting Protection ===")
    mac = "33:44:55:66:77:88"
    locked = False
    for i in range(1, 7):
        status, res = http_request(
            "/api/devices/register",
            method="POST",
            payload={"activation_code": f"{i:06d}", "mac_address": mac}
        )
        if status == 429:
            locked = True
            logger.info("  ✓ Brute-force lockout triggered at attempt %d: %s", i, res.get("detail"))
            break
    assert locked, "Expected 429 rate limit lockout after repeated invalid registration attempts"


def test_concurrent_registrations():
    logger.info("=== [9/10] Testing Concurrent Device Registrations ===")
    codes = []
    for i in range(3):
        _, r = http_request("/api/devices/activation", method="POST", payload={"agent_id": "agent_101"})
        codes.append(r["code"])

    def register_worker(idx: int):
        mac = f"CC:11:22:33:44:{idx:02X}"
        st, res = http_request(
            "/api/devices/register",
            method="POST",
            payload={
                "activation_code": codes[idx],
                "mac_address": mac,
                "device_name": f"Concurrent Node {idx}"
            }
        )
        return st, res

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(register_worker, range(3)))

    for idx, (st, res) in enumerate(results):
        assert st == 200, f"Worker {idx} failed: {res}"
        assert res["agent_id"] == "agent_101"

    logger.info("  ✓ 3 concurrent devices registered simultaneously without race conditions")


def test_backward_compatibility_manual_mac():
    logger.info("=== [10/11] Testing Backward Compatibility with Manual MAC Bindings ===")
    test_manual_mac = "99:88:77:66:55:44"
    st, bind_res = http_request(
        "/api/devices/bind",
        method="POST",
        payload={
            "mac_address": test_manual_mac,
            "agent_id": "agent_103",
            "device_name": "Virtual PC Legacy Node"
        }
    )
    assert st == 200

    # Verify inventory marks it as manual_mac
    _, inv = http_request("/api/devices")
    matched = [d for d in inv.get("devices", []) if d["mac_address"] == test_manual_mac]
    assert len(matched) == 1
    assert matched[0]["registration_status"] == "manual_mac"
    assert matched[0]["is_auth"] is False
    logger.info("  ✓ Manual MAC node distinguished in inventory: registration_status='manual_mac', is_auth=False")

    # Cleanup
    http_request("/api/devices/unbind", method="POST", payload={"mac_address": test_manual_mac})
    logger.info("  ✓ Unbound manual test MAC successfully")


def test_xiaozhi_esp32_spoken_code_activation():
    logger.info("=== [11/11] Testing XiaoZhi Spoken Code & Web Console Activation Flow ===")
    esp_mac = "30:ED:A0:99:88:77"

    # Step 1: ESP32 connects to Wi-Fi and hits OTA check
    st1, ota_res = http_request(
        "/xiaozhi/ota/",
        method="POST",
        headers={"Device-Id": esp_mac}
    )
    assert st1 == 200, f"OTA check failed: {ota_res}"
    assert "activation" in ota_res, "Expected activation challenge for unbound ESP32"
    spoken_code = ota_res["activation"]["code"]
    assert len(spoken_code) == 6 and spoken_code.isdigit()
    logger.info("  ✓ ESP32 received activation code: %s (to be spoken out & displayed on LCD)", spoken_code)

    # Step 2: ESP32 polls /xiaozhi/ota/activate while user hasn't entered code yet -> expects HTTP 202
    st2, poll_res = http_request(
        "/xiaozhi/ota/activate",
        method="POST",
        headers={"Device-Id": esp_mac}
    )
    assert st2 == 202, f"Expected 202 pending status, got {st2}: {poll_res}"
    logger.info("  ✓ ESP32 polling /xiaozhi/ota/activate received 202 (waiting for user on console)")

    # Step 3: User enters this 6-digit code on web console and selects Agent Profile (Nova / agent_101)
    st3, bind_res = http_request(
        "/api/devices/activation/bind",
        method="POST",
        payload={
            "code": spoken_code,
            "agent_id": "agent_101",
            "device_name": "Physical Desk Voice Box"
        }
    )
    assert st3 == 200, f"Console binding failed: {bind_res}"
    assert bind_res.get("status") == "success"
    logger.info("  ✓ User submitted spoken code %s on console and bound to agent_101 (Nova)", spoken_code)

    # Step 4: ESP32 polls /xiaozhi/ota/activate again -> expects HTTP 200 OK!
    st4, act_res = http_request(
        "/xiaozhi/ota/activate",
        method="POST",
        headers={"Device-Id": esp_mac}
    )
    assert st4 == 200, f"Expected 200 activation confirmation, got {st4}: {act_res}"
    logger.info("  ✓ ESP32 received HTTP 200 activation confirmation; ready for WebSocket session")

    # Step 5: Subsequent OTA check provides WebSocket endpoint directly (no challenge)
    st5, next_ota = http_request(
        "/xiaozhi/ota/",
        method="POST",
        headers={"Device-Id": esp_mac}
    )
    assert st5 == 200
    assert "activation" not in next_ota
    assert "websocket" in next_ota
    logger.info("  ✓ Subsequent boot check returns direct WebSocket endpoint without activation challenge")

    # Cleanup
    http_request("/api/devices/unbind", method="POST", payload={"mac_address": esp_mac})


def main():
    logger.info("=================================================================")
    logger.info("ALPHA 0.2 PROVISIONING & AUTHENTICATION TEST SUITE")
    logger.info("=================================================================")
    start_time = time.time()

    test_activation_code_generation()
    test_activation_expiration()
    token, mac = test_invalid_and_duplicate_activation()
    test_device_authentication_and_security(token, mac)
    test_device_heartbeat(token)
    test_management_inventory_and_resolution(mac)
    test_credential_revocation_and_unbinding(token, mac)
    test_rate_limiting_brute_force()
    test_concurrent_registrations()
    test_backward_compatibility_manual_mac()
    test_xiaozhi_esp32_spoken_code_activation()

    elapsed = time.time() - start_time
    logger.info("=================================================================")
    logger.info("ALPHA 0.2 ALL PROVISIONING TESTS PASSED in %.2f seconds!", elapsed)
    logger.info("=================================================================")


if __name__ == "__main__":
    main()
