"""
Unit tests for the three MCP tools: list_devices, get_telemetry, send_rpc.
Validates input/output schemas and error wrapping.
"""

import json
import unittest
from unittest.mock import AsyncMock, MagicMock

from src.client import ThingsBoardClient, DeviceNotFoundError, ThingsBoardError
from src.schemas import (
    DeviceSummary,
    GetTelemetryResult,
    ListDevicesResult,
    SendRpcResult,
    TelemetryItem,
)
from src.tools.devices import register_list_devices_tool
from src.tools.telemetry import register_get_telemetry_tool
from src.tools.rpc import register_send_rpc_tool


class MockMCPServer:
    """Mock container for inspecting registered MCP tools."""
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn
        return decorator


class TestMcpTools(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_client = MagicMock(spec=ThingsBoardClient)
        self.mcp = MockMCPServer()
        register_list_devices_tool(self.mcp, self.mock_client)
        register_get_telemetry_tool(self.mcp, self.mock_client)
        register_send_rpc_tool(self.mcp, self.mock_client)

    def test_tools_registered(self):
        self.assertIn("list_devices", self.mcp.tools)
        self.assertIn("get_telemetry", self.mcp.tools)
        self.assertIn("send_rpc", self.mcp.tools)

    async def test_tool_list_devices_success(self):
        fn = self.mcp.tools["list_devices"]
        self.mock_client.list_devices = AsyncMock(return_value=ListDevicesResult(
            total_devices=1,
            page=0,
            has_next=False,
            devices=[
                DeviceSummary(id="dev-uuid-1", name="DHT20-Sensor", type="sensor", label="Lab A")
            ]
        ))

        output = await fn(page_size=10, page=0)
        data = json.loads(output)
        self.assertEqual(data["total_devices"], 1)
        self.assertEqual(data["devices"][0]["name"], "DHT20-Sensor")

    async def test_tool_list_devices_error(self):
        fn = self.mcp.tools["list_devices"]
        self.mock_client.list_devices = AsyncMock(side_effect=ThingsBoardError("API down"))

        output = await fn()
        data = json.loads(output)
        self.assertFalse(data["success"])
        self.assertIn("API down", data["error"])

    async def test_tool_get_telemetry_success(self):
        fn = self.mcp.tools["get_telemetry"]
        self.mock_client.get_latest_telemetry = AsyncMock(return_value=GetTelemetryResult(
            device_id="dev-uuid-1",
            device_name="DHT20-Sensor",
            telemetry_keys=["temperature", "humidity"],
            telemetry={
                "temperature": TelemetryItem(value=25.5, timestamp="2026-11-07T09:00:00Z", epoch_ms=1700000000000),
                "humidity": TelemetryItem(value=55.0, timestamp="2026-11-07T09:00:00Z", epoch_ms=1700000000000),
            }
        ))

        output = await fn(device_identifier="DHT20-Sensor", keys=["temperature"])
        data = json.loads(output)
        self.assertEqual(data["device_id"], "dev-uuid-1")
        self.assertEqual(data["telemetry"]["temperature"]["value"], 25.5)

    async def test_tool_get_telemetry_device_not_found(self):
        fn = self.mcp.tools["get_telemetry"]
        self.mock_client.get_latest_telemetry = AsyncMock(
            side_effect=DeviceNotFoundError("Device 'UnknownDevice' not found.")
        )

        output = await fn(device_identifier="UnknownDevice")
        data = json.loads(output)
        self.assertFalse(data["success"])
        self.assertIn("not found", data["error"])

    async def test_tool_send_rpc_success(self):
        fn = self.mcp.tools["send_rpc"]
        self.mock_client.send_rpc = AsyncMock(return_value=SendRpcResult(
            success=True,
            device_id="dev-uuid-1",
            device_name="SmartSwitch",
            method="toggle",
            response={"status": "on"}
        ))

        output = await fn(device_identifier="SmartSwitch", method="toggle", params={"state": True})
        data = json.loads(output)
        self.assertTrue(data["success"])
        self.assertEqual(data["method"], "toggle")
        self.assertEqual(data["response"]["status"], "on")

    async def test_tool_send_rpc_timeout(self):
        fn = self.mcp.tools["send_rpc"]
        self.mock_client.send_rpc = AsyncMock(return_value=SendRpcResult(
            success=False,
            device_id="dev-uuid-1",
            device_name="SmartSwitch",
            method="toggle",
            error="RPC timeout: device did not respond within 5000ms."
        ))

        output = await fn(device_identifier="SmartSwitch", method="toggle")
        data = json.loads(output)
        self.assertFalse(data["success"])
        self.assertIn("RPC timeout", data["error"])


if __name__ == "__main__":
    unittest.main()
