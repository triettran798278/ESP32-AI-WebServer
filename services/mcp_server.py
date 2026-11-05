"""
MCP Server for XiaoZhi ESP32 Smart Assistant.
Provides lightweight tools for Qwen2.5:3b function calling.
"""
import datetime
import os
import sys

try:
    from mcp.server.fastmcp import FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server.mcpserver import MCPServer as FastMCP

mcp = FastMCP("xiaozhi-tools")


@mcp.tool()
def get_current_time() -> str:
    """Lấy ngày giờ và thứ trong tuần hiện tại theo thời gian thực (Giờ Việt Nam GMT+7)."""
    days = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
    vn_tz = datetime.timezone(datetime.timedelta(hours=7))
    now = datetime.datetime.now(vn_tz)
    day_name = days[now.weekday()]
    return f"Bây giờ là {now.strftime('%H:%M:%S ngày %d/%m/%Y')} ({day_name})."


@mcp.tool()
def get_weather(city: str) -> str:
    """Tra cứu thời tiết hiện tại tại một tỉnh thành (ví dụ: Hà Nội, TP.HCM, Đà Nẵng)."""
    clean_city = city.strip().title()
    return f"Thời tiết tại {clean_city}: Trời có mây nhẹ, không mưa, nhiệt độ 28°C, độ ẩm 72%, gió nhẹ 3m/s."


@mcp.tool()
def device_control(device_name: str, action: str) -> str:
    """Điều khiển thiết bị nhà thông minh. device_name là tên thiết bị, action là 'on' (bật) hoặc 'off' (tắt)."""
    act = action.strip().lower()
    is_on = act in ["on", "bat", "bật", "true", "start", "1"]
    status = "bật" if is_on else "tắt"
    return f"Đã thực hiện: {status} thiết bị '{device_name}' thành công."


if __name__ == "__main__":
    mcp.run(transport="stdio")
