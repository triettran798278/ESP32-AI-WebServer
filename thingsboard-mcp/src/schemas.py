"""
Pydantic schemas and data models for ThingsBoard MCP Server.
Provides structured input validation and concise, LLM-friendly output formats.
"""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class DeviceSummary(BaseModel):
    """Concise representation of a ThingsBoard device for LLM consumption."""
    id: str = Field(description="Unique device UUID")
    name: str = Field(description="Device display name")
    type: str = Field(description="Device profile type, e.g. sensor, default, thermostat")
    label: Optional[str] = Field(default="", description="Human-readable label or location note")
    created_time: Optional[str] = Field(default=None, description="ISO timestamp of device creation")
    is_gateway: Optional[bool] = Field(default=False, description="Whether device is an IoT gateway")


class ListDevicesResult(BaseModel):
    """Output schema for list_devices tool."""
    total_devices: int = Field(description="Number of devices returned in this batch")
    page: int = Field(description="Current page index (0-indexed)")
    has_next: bool = Field(description="Whether more devices exist on next pages")
    devices: List[DeviceSummary] = Field(description="List of accessible devices")


class TelemetryItem(BaseModel):
    """A single sensor metric value with its timestamp."""
    value: Union[float, int, bool, str, dict] = Field(description="Latest metric value")
    timestamp: str = Field(description="ISO 8601 formatted timestamp of the reading")
    epoch_ms: int = Field(description="Unix timestamp in milliseconds")


class GetTelemetryResult(BaseModel):
    """Output schema for get_telemetry tool."""
    device_id: str = Field(description="Target device UUID")
    device_name: str = Field(description="Target device name")
    telemetry_keys: List[str] = Field(description="List of telemetry keys returned")
    telemetry: Dict[str, TelemetryItem] = Field(
        description="Map of telemetry key name to its latest value and timestamp"
    )


class SendRpcResult(BaseModel):
    """Output schema for send_rpc tool."""
    success: bool = Field(description="Whether the RPC command succeeded")
    device_id: str = Field(description="Target device UUID")
    device_name: Optional[str] = Field(default=None, description="Target device name")
    method: str = Field(description="RPC method invoked")
    response: Optional[Any] = Field(
        default=None,
        description="Response payload returned by device (for two-way RPC)"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if RPC failed or timed out"
    )
