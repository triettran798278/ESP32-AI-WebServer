"""
Tool: get_telemetry
Retrieves the latest telemetry values for a specified device and optional telemetry keys.
"""

import logging
from typing import List, Optional
from ..client import ThingsBoardClient, ThingsBoardError, DeviceNotFoundError
from ..schemas import GetTelemetryResult

logger = logging.getLogger("thingsboard_mcp.tools.telemetry")


def register_get_telemetry_tool(mcp_server, client: ThingsBoardClient):
    """Register get_telemetry tool with MCP Server."""

    @mcp_server.tool()
    async def get_telemetry(
        device_identifier: str,
        keys: Optional[List[str]] = None,
    ) -> str:
        """Retrieve the latest telemetry readings (sensor measurements) for a specified ThingsBoard device.
        
        Use this tool when you need to:
        - Check current temperature, humidity, power consumption, air quality, or battery level.
        - Inspect the most recent state reported by an IoT sensor or edge device.

        Args:
            device_identifier: The device display name (e.g. 'Virtual-Environmental-Monitor')
                               or device UUID (e.g. '0db31590-da5d-11f1-9c26-21abd05992f6').
            keys: Optional list of specific telemetry keys to fetch (e.g. ['temperature', 'humidity']).
                  If omitted or empty, all available latest telemetry keys are returned.

        Returns:
            JSON string containing device metadata and a map of sensor keys with their latest values
            and ISO timestamps.
        """
        logger.info("Executing get_telemetry(device=%s, keys=%s)", device_identifier, keys)
        try:
            result: GetTelemetryResult = await client.get_latest_telemetry(
                device_identifier=device_identifier,
                keys=keys,
            )
            return result.model_dump_json(indent=2)
        except DeviceNotFoundError as e:
            logger.warning("Device not found in get_telemetry: %s", e)
            return f'{{"error": "{str(e)}", "device_identifier": "{device_identifier}", "success": false}}'
        except ThingsBoardError as e:
            logger.error("ThingsBoard error in get_telemetry: %s", e)
            return f'{{"error": "{str(e)}", "device_identifier": "{device_identifier}", "success": false}}'
        except Exception as e:
            logger.exception("Unexpected error in get_telemetry")
            return f'{{"error": "Internal error: {str(e)}", "device_identifier": "{device_identifier}", "success": false}}'
