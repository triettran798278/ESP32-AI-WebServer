"""
Tool: send_rpc
Sends a server-side Remote Procedure Call (RPC) command to a device with a method and parameters.
"""

import json
import logging
from typing import Any, Optional, Union
from ..client import ThingsBoardClient, ThingsBoardError
from ..schemas import SendRpcResult

logger = logging.getLogger("thingsboard_mcp.tools.rpc")


def register_send_rpc_tool(mcp_server, client: ThingsBoardClient):
    """Register send_rpc tool with MCP Server."""

    @mcp_server.tool()
    async def send_rpc(
        device_identifier: str,
        method: str,
        params: Optional[Union[dict, list, str, int, float, bool]] = None,
        timeout_ms: int = 5000,
        two_way: bool = True,
    ) -> str:
        """Send a server-side Remote Procedure Call (RPC) command to control a ThingsBoard device.
        
        Use this tool when you need to:
        - Trigger an actuator, toggle a relay/switch, or change GPIO state on hardware (e.g. ESP32).
        - Invoke a device method such as 'setGpio', 'setPower', 'setMode', 'reboot', or 'calibrate'.
        - Send control parameters to an edge device and optionally wait for its reply.

        Args:
            device_identifier: Device name (e.g. 'Virtual-Environmental-Monitor') or device UUID.
            method: The RPC method name to call on the target device (e.g. 'setValue', 'setGpio').
            params: Parameters/arguments for the RPC method. Can be a dictionary (e.g. {"pin": 2, "value": 1}),
                    a primitive (e.g. True or 42), or omitted.
            timeout_ms: Maximum time in milliseconds to wait for the device response (default: 5000).
            two_way: If True, waits for device confirmation/response; if False, sends one-way RPC.

        Returns:
            JSON string containing RPC success status, device ID, method name, response payload
            (if two-way RPC succeeded), or error details (e.g. timeout if device is disconnected).
        """
        logger.info(
            "Executing send_rpc(device=%s, method=%s, two_way=%s, timeout_ms=%d)",
            device_identifier, method, two_way, timeout_ms
        )
        try:
            result: SendRpcResult = await client.send_rpc(
                device_identifier=device_identifier,
                method=method,
                params=params,
                timeout_ms=timeout_ms,
                two_way=two_way,
            )
            return result.model_dump_json(indent=2)
        except ThingsBoardError as e:
            logger.error("ThingsBoard error in send_rpc: %s", e)
            return json.dumps({
                "success": False,
                "device_identifier": device_identifier,
                "method": method,
                "error": str(e)
            }, indent=2)
        except Exception as e:
            logger.exception("Unexpected error in send_rpc")
            return json.dumps({
                "success": False,
                "device_identifier": device_identifier,
                "method": method,
                "error": f"Internal error: {str(e)}"
            }, indent=2)
