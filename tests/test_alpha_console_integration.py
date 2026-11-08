#!/usr/bin/env python3
"""
Alpha 0.1 End-to-End Integration Test Suite.
Verifies:
1. Console SPA frontend serving and asset delivery.
2. Agent profile CRUD and data persistence.
3. Credential security and API key masking.
4. Device inventory, binding, unbinding, and MAC-to-profile resolution.
5. ThingsBoard external IoT integration test and telemetry retrieval.
"""

import json
import logging
import sys
import time
import urllib.request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("alpha_test")

BRIDGE_URL = "http://localhost:8005"
TEST_MAC = "AA:BB:CC:11:22:33"


def http_get(path: str) -> dict | str:
    url = f"{BRIDGE_URL}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "Alpha-Test/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        content_type = resp.headers.get("Content-Type", "")
        raw = resp.read()
        if "application/json" in content_type:
            return json.loads(raw.decode("utf-8"))
        return raw.decode("utf-8")


def http_post(path: str, payload: dict) -> dict:
    url = f"{BRIDGE_URL}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "Alpha-Test/1.0"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_put(path: str, payload: dict) -> dict:
    url = f"{BRIDGE_URL}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="PUT",
        headers={"Content-Type": "application/json", "User-Agent": "Alpha-Test/1.0"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_delete(path: str) -> dict:
    url = f"{BRIDGE_URL}{path}"
    req = urllib.request.Request(
        url,
        method="DELETE",
        headers={"User-Agent": "Alpha-Test/1.0"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_console_frontend_serving():
    logger.info("=== [1/6] Testing Frontend UI Console Delivery ===")
    html = http_get("/")
    assert "<!doctype html>" in html.lower()
    assert "Xiaozhi Console" in html
    logger.info("  ✓ Root index serves AI Agent Management Console SPA")

    console_html = http_get("/console/")
    assert "<!doctype html>" in console_html.lower()
    logger.info("  ✓ /console/ path accessible and operational")


def test_agent_profiles_and_credential_masking():
    logger.info("=== [2/6] Testing Agent Profiles & Credential Masking ===")
    res = http_get("/api/agents")
    agents = res.get("agents", [])
    assert len(agents) >= 3, f"Expected at least 3 agent profiles, found {len(agents)}"

    agent_ids = [a["id"] for a in agents]
    assert "agent_101" in agent_ids
    assert "agent_102" in agent_ids
    assert "agent_103" in agent_ids

    # Verify credential masking
    for a in agents:
        tb = a.get("integrations", {}).get("thingsboard", {})
        api_key = tb.get("api_key", "")
        if api_key:
            assert "..." in api_key or api_key == "***", f"API key was not masked: {api_key}"
            assert not api_key.startswith("tb_G5TSH2WJsF3g25Q_"), "Plaintext secret leaked in frontend response!"
            logger.info("  ✓ Agent %s (%s) ThingsBoard API key securely masked: %s", a["id"], a["role"], api_key)

    # Test Agent Update (editing name & prompt)
    target_agent = next(a for a in agents if a["id"] == "agent_101")
    orig_name = target_agent["name"]
    update_res = http_put("/api/agents/agent_101", {
        "name": f"{orig_name} (Updated)",
        "config": {
            "character": target_agent["config"]["character"],
            "tool_policy": "full_control",
            "integrations": target_agent["integrations"]  # Sending masked key back
        }
    })
    assert update_res.get("status") == "success"

    # Re-fetch and verify update succeeded without secret erasure
    updated_agent = http_get("/api/agents/agent_101")
    assert "(Updated)" in updated_agent["name"]
    assert updated_agent["integrations"]["thingsboard"]["is_configured"] is True

    # Restore original name
    http_put("/api/agents/agent_101", {
        "name": orig_name,
        "config": target_agent["config"]
    })
    logger.info("  ✓ Agent Profile update verified; masked credential preservation confirmed")


def test_agent_crud_lifecycle():
    logger.info("=== [3/6] Testing Agent Creation & Deletion Lifecycle ===")
    new_agent_payload = {
        "id": "agent_test_temp",
        "name": "Temporary Test Agent",
        "role": "Tester",
        "language": "en",
        "prompt": "Test prompt for temporary agent",
        "tool_policy": "read_only_telemetry",
        "integrations": {
            "thingsboard": {
                "host": "https://codehelpers.tech",
                "display_name": "Temporary Integration"
            }
        }
    }
    create_res = http_post("/api/agents", new_agent_payload)
    assert create_res.get("status") == "success"

    # Verify created agent
    created = http_get("/api/agents/agent_test_temp")
    assert created["id"] == "agent_test_temp"
    assert created["name"] == "Temporary Test Agent"
    logger.info("  ✓ Created agent_test_temp successfully")

    # Delete agent
    del_res = http_delete("/api/agents/agent_test_temp")
    assert del_res.get("status") == "success"
    logger.info("  ✓ Deleted agent_test_temp successfully")


def test_device_management_and_mac_binding():
    logger.info("=== [4/6] Testing Device Inventory, Binding & Unbinding ===")
    dev_res = http_get("/api/devices")
    devices = dev_res.get("devices", [])
    assert len(devices) >= 2, f"Expected devices, got: {devices}"
    logger.info("  ✓ Found %d registered hardware devices", len(devices))

    # Test Binding new MAC
    bind_res = http_post("/api/devices/bind", {
        "mac_address": TEST_MAC,
        "agent_id": "agent_102",
        "device_name": "Integration Test Node"
    })
    assert bind_res.get("status") == "success"
    logger.info("  ✓ Bound MAC %s to agent_102 (Luna)", TEST_MAC)

    # Verify MAC-to-Profile resolution via Management Contract
    model_cfg = http_post("/config/agent-models", {"macAddress": TEST_MAC, "clientId": "test-client"})
    assert model_cfg.get("code") == 0
    assert model_cfg["data"]["agent_id"] == "agent_102"
    assert model_cfg["data"]["role"] == "Luna"
    assert model_cfg["data"]["tool_policy"] == "read_only_telemetry"
    logger.info("  ✓ Verified MAC-to-Profile resolution: %s -> agent_102 (Luna)", TEST_MAC)

    # Test Unbinding
    unbind_res = http_post("/api/devices/unbind", {"mac_address": TEST_MAC})
    assert unbind_res.get("status") == "success"
    logger.info("  ✓ Unbound MAC %s successfully", TEST_MAC)


def test_thingsboard_integration_and_telemetry():
    logger.info("=== [5/6] Testing ThingsBoard Integration & Read-Only Telemetry ===")
    test_res = http_post("/api/integrations/thingsboard/test", {"agent_id": "agent_101"})
    assert test_res.get("status") == "success", f"ThingsBoard test failed: {test_res}"
    assert test_res.get("device_count", 0) > 0
    logger.info("  ✓ ThingsBoard connection OK: %s (%d devices discovered)", test_res.get("host"), test_res.get("device_count"))

    # Test Telemetry Preview
    tel_res = http_get("/api/integrations/thingsboard/telemetry?agent_id=agent_101")
    assert tel_res.get("status") == "success"
    assert len(tel_res.get("devices", [])) > 0
    first_device = tel_res["devices"][0]
    logger.info("  ✓ Telemetry preview operational: Fetched %s (ID: %s)", first_device["name"], first_device["id"])


def test_regression_phase1b():
    logger.info("=== [6/6] Verifying Regression: Health & Management Contract Compatibility ===")
    health = http_get("/api/health")
    assert health.get("status") == "healthy"
    logger.info("  ✓ /api/health OK")

    base = http_post("/config/server-base", {})
    assert base.get("code") == 0
    logger.info("  ✓ /config/server-base contract OK")


def main():
    logger.info("Starting Alpha 0.1 Integration Test Suite")
    start = time.time()
    try:
        test_console_frontend_serving()
        test_agent_profiles_and_credential_masking()
        test_agent_crud_lifecycle()
        test_device_management_and_mac_binding()
        test_thingsboard_integration_and_telemetry()
        test_regression_phase1b()
    except Exception as e:
        logger.exception("Alpha 0.1 verification FAILED: %s", e)
        sys.exit(1)

    elapsed = time.time() - start
    logger.info("=================================================================")
    logger.info("ALPHA 0.1 ALL INTEGRATION TESTS PASSED in %.2f seconds!", elapsed)
    logger.info("=================================================================")


if __name__ == "__main__":
    main()
