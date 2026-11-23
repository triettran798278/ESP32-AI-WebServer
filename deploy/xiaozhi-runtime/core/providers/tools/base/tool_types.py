"""工具系统的类型定义"""

from enum import Enum

from dataclasses import dataclass
from typing import Any, Dict, Optional
from plugins_func.register import Action


class ToolType(Enum):
    """工具类型枚举"""

    SERVER_PLUGIN = "server_plugin"  # Server-side plugin
    SERVER_MCP = "server_mcp"  # Server-side MCP
    DEVICE_IOT = "device_iot"  # Device-side IoT
    DEVICE_MCP = "device_mcp"  # Device-side MCP
    MCP_ENDPOINT = "mcp_endpoint"  # MCP endpoint


@dataclass
class ToolDefinition:
    """工具定义"""

    name: str  # Tool name
    description: Dict[str, Any]  # Tool description (OpenAI function-calling format)
    tool_type: ToolType  # Tool type
    parameters: Optional[Dict[str, Any]] = None  # Extra parameters
