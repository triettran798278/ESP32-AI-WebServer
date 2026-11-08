"""
Independent ThingsBoard MCP Server entry point.
Supports stdio and network transports.
"""

import argparse
import logging
import os
import sys
from typing import Any, Dict, Optional

try:
    from mcp.server.mcpserver import MCPServer
except (ImportError, ModuleNotFoundError):
    from mcp.server.fastmcp import FastMCP as MCPServer

from .client import ThingsBoardClient
from .config import ThingsBoardConfig, resolve_thingsboard_config
from .tools import register_all_tools

# Configure logging strictly to stderr to prevent corrupting stdio JSON-RPC transport
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)
logger = logging.getLogger("thingsboard_mcp.server")


def create_server(
    profile_path: Optional[str] = None,
    profile_dict: Optional[Dict[str, Any]] = None,
    config: Optional[ThingsBoardConfig] = None,
    server_name: str = "thingsboard-tools",
) -> MCPServer:
    """
    Factory function to initialize and configure the ThingsBoard MCP Server.
    Resolves ThingsBoard credentials from the active Agent Profile.
    """
    if config is None:
        config = resolve_thingsboard_config(profile_path=profile_path, profile_dict=profile_dict)

    client = ThingsBoardClient(config)
    mcp_server = MCPServer(server_name)

    # Register modular tools
    register_all_tools(mcp_server, client)
    logger.info("Initialized ThingsBoard MCP Server with tools: list_devices, get_telemetry, send_rpc")
    return mcp_server


def main():
    """CLI entry point for running the MCP Server independently."""
    parser = argparse.ArgumentParser(description="ThingsBoard MCP Server for AI Agents")
    parser.add_argument(
        "--profile",
        "-p",
        type=str,
        default=os.getenv("AGENT_PROFILE_PATH"),
        help="Path to the active Agent Profile JSON file containing integrations.thingsboard",
    )
    parser.add_argument(
        "--transport",
        "-t",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="MCP transport to use (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind host for SSE/HTTP transports (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "8009")),
        help="Bind port for SSE/HTTP transports (default: 8009)",
    )

    args = parser.parse_args()

    try:
        server = create_server(profile_path=args.profile)
    except Exception as e:
        logger.error("Failed to start ThingsBoard MCP Server: %s", e)
        sys.exit(1)

    logger.info("Starting ThingsBoard MCP Server on transport '%s'...", args.transport)
    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
