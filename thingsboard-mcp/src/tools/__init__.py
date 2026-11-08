"""
ThingsBoard MCP Tools package.
Exports tool registration logic to keep tool implementations modular and extensible.
"""

from ..client import ThingsBoardClient
from .devices import register_list_devices_tool
from .telemetry import register_get_telemetry_tool
from .rpc import register_send_rpc_tool


def register_all_tools(mcp_server, client: ThingsBoardClient) -> None:
    """Register all ThingsBoard tools with the MCP Server instance."""
    register_list_devices_tool(mcp_server, client)
    register_get_telemetry_tool(mcp_server, client)
    register_send_rpc_tool(mcp_server, client)
