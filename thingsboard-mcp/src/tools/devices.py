"""
Tool: list_devices
Retrieves devices accessible through the configured ThingsBoard integration.
"""

import logging
from typing import Optional
from ..client import ThingsBoardClient, ThingsBoardError
from ..schemas import ListDevicesResult

logger = logging.getLogger("thingsboard_mcp.tools.devices")


def register_list_devices_tool(mcp_server, client: ThingsBoardClient):
    """Register list_devices tool with MCP Server."""

    @mcp_server.tool()
    async def list_devices(
        page_size: int = 50,
        page: int = 0,
        device_type: Optional[str] = None,
    ) -> str:
        """List all IoT devices registered in ThingsBoard accessible by the active agent.
        
        Use this tool when you need to:
        - Discover available sensors, actuators, smart plugs, or microcontrollers.
        - Look up a device's UUID identifier from its name or label.
        - Check what device profiles/types are active in the system.

        Args:
            page_size: Number of devices to return per page (default: 50, max: 100).
            page: Page index (0-indexed, default: 0).
            device_type: Optional device type/profile filter (e.g. 'default', 'environmental-sensor').

        Returns:
            JSON string containing total_devices count, has_next flag, and the list of devices
            with their UUIDs, names, types, and labels.
        """
        logger.info("Executing list_devices(page_size=%d, page=%d, type=%s)", page_size, page, device_type)
        try:
            result: ListDevicesResult = await client.list_devices(
                page_size=page_size,
                page=page,
                device_type=device_type,
            )
            return result.model_dump_json(indent=2)
        except ThingsBoardError as e:
            logger.error("Failed to list devices: %s", e)
            return f'{{"error": "{str(e)}", "success": false}}'
        except Exception as e:
            logger.exception("Unexpected error in list_devices")
            return f'{{"error": "Internal error: {str(e)}", "success": false}}'
