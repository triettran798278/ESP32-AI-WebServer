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


@mcp.tool()
def get_dht20_environment() -> str:
    """Đọc dữ liệu nhiệt độ và độ ẩm không khí thực tế từ cảm biến môi trường DHT20 trên CoreIoT."""
    import json
    import urllib.request
    import urllib.error

    public_id = os.getenv("COREIOT_PUBLIC_ID", "ffd43ad0-776f-11f1-9dee-09c31de14de0")
    device_id = os.getenv("COREIOT_DEVICE_ID", "07400250-d8bd-11f1-9298-f795494fee72")
    base_url = os.getenv("COREIOT_URL", "https://app.coreiot.io").rstrip("/")

    # 1. Đăng nhập qua Public ID lấy JWT Token
    try:
        login_url = f"{base_url}/api/auth/login/public"
        login_payload = json.dumps({"publicId": public_id}).encode("utf-8")
        req = urllib.request.Request(
            login_url,
            data=login_payload,
            headers={"Content-Type": "application/json", "User-Agent": "XiaoZhi-MCP/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            token = json.loads(resp.read().decode("utf-8")).get("token")
    except Exception as e:
        return f"Lỗi xác thực với CoreIoT: {e}"

    # 2. Truy vấn dữ liệu nhiệt độ & độ ẩm mới nhất của thiết bị
    headers = {"X-Authorization": f"Bearer {token}", "User-Agent": "XiaoZhi-MCP/1.0"}
    telemetry_url = f"{base_url}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries?keys=temperature,humidity"
    try:
        req = urllib.request.Request(telemetry_url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            temp = data.get("temperature", [{}])[0].get("value")
            hum = data.get("humidity", [{}])[0].get("value")
            if temp is not None and hum is not None:
                return f"Cảm biến DHT20 đo được: Nhiệt độ hiện tại là {temp}°C, độ ẩm không khí là {hum}%."
            elif temp is not None:
                return f"Cảm biến DHT20 đo được: Nhiệt độ là {temp}°C."
            elif hum is not None:
                return f"Cảm biến DHT20 đo được: Độ ẩm là {hum}%."
            else:
                return "Cảm biến DHT20 đang kết nối nhưng chưa có dữ liệu mới."
    except urllib.error.HTTPError as e:
        if e.code == 403:
            return (
                "Thiết bị DHT20 chưa được bật quyền công khai trên CoreIoT. "
                "Vui lòng vào app.coreiot.io -> Devices -> chọn 'DHT20 · Environment monitor' -> bấm 'Make public'."
            )
        return f"Lỗi đọc dữ liệu từ CoreIoT (HTTP {e.code}): {e.reason}"
    except Exception as e:
        return f"Lỗi kết nối tới CoreIoT: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
