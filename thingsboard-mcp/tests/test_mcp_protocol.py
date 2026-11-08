"""
End-to-End MCP Protocol Test.
Runs the ThingsBoard MCP server in a subprocess via standard stdio transport,
connects an MCP ClientSession, discovers tools, and invokes all three tools.
"""

import asyncio
import json
import os
import sys
import tempfile
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class TestMcpProtocolStdio(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Create a mock agent profile JSON for the MCP server process
        self.profile = {
            "id": "agent_test_profile",
            "name": "Integration Test Agent",
            "integrations": {
                "thingsboard": {
                    "host": "http://127.0.0.1:8080",
                    "api_key": "tb_test_mock_protocol_key",
                    "timeout_seconds": 2
                }
            }
        }
        self.tmp_profile = tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False)
        json.dump(self.profile, self.tmp_profile)
        self.tmp_profile.flush()
        self.tmp_profile.close()

    async def asyncTearDown(self):
        if os.path.exists(self.tmp_profile.name):
            os.remove(self.tmp_profile.name)

    async def test_full_mcp_session_lifecycle(self):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "src.server", "--profile", self.tmp_profile.name],
            env={
                **os.environ,
                "PYTHONPATH": project_root,
                "LOG_LEVEL": "WARNING"
            }
        )

        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                # 1. Initialize MCP Session
                init_res = await session.initialize()
                self.assertIsNotNone(init_res)

                # 2. List tools
                tools_res = await session.list_tools()
                tool_names = [t.name for t in tools_res.tools]
                self.assertIn("list_devices", tool_names)
                self.assertIn("get_telemetry", tool_names)
                self.assertIn("send_rpc", tool_names)

                # 3. Call list_devices
                call_list = await session.call_tool("list_devices", {"page_size": 5})
                self.assertIsNotNone(call_list.content)
                text_content = call_list.content[0].text
                parsed_list = json.loads(text_content)
                # Should return either device list or clean error dict (if mock host not responding)
                self.assertIsInstance(parsed_list, dict)

                # 4. Call get_telemetry
                call_telem = await session.call_tool("get_telemetry", {
                    "device_identifier": "NonExistentSensor",
                    "keys": ["temperature"]
                })
                self.assertIsNotNone(call_telem.content)
                parsed_telem = json.loads(call_telem.content[0].text)
                self.assertIsInstance(parsed_telem, dict)

                # 5. Call send_rpc
                call_rpc = await session.call_tool("send_rpc", {
                    "device_identifier": "NonExistentSwitch",
                    "method": "toggle",
                    "params": {"state": True},
                    "timeout_ms": 1000
                })
                self.assertIsNotNone(call_rpc.content)
                parsed_rpc = json.loads(call_rpc.content[0].text)
                self.assertIsInstance(parsed_rpc, dict)
                self.assertFalse(parsed_rpc.get("success", False))


if __name__ == "__main__":
    unittest.main()
