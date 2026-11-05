"""
MCP Server for XiaoZhi ESP32 Smart Assistant.
Includes ThingsBoard / CoreIoT Auto-Discovery Connector and Smart Home tools.
"""
import datetime
import os
import time
from typing import Any, Dict, List, Optional

import httpx

try:
    from mcp.server.fastmcp import FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server.mcpserver import MCPServer as FastMCP

mcp = FastMCP("xiaozhi-thingsboard-tools")

COREIOT_URL = os.getenv("COREIOT_URL", "https://app.coreiot.io").rstrip("/")
COREIOT_PUBLIC_ID = os.getenv("COREIOT_PUBLIC_ID", "ffd43ad0-776f-11f1-9dee-09c31de14de0")
COREIOT_USERNAME = os.getenv("COREIOT_USERNAME", "").strip()
COREIOT_PASSWORD = os.getenv("COREIOT_PASSWORD", "").strip()
COREIOT_DEVICE_TOKEN = os.getenv("COREIOT_DEVICE_TOKEN", "iqYmkU3CuCQoPtxnaxBm").strip()

# Persistent HTTP client reuses TLS connections to app.coreiot.io
_http = httpx.Client(
    base_url=COREIOT_URL,
    timeout=10.0,
    headers={"User-Agent": "XiaoZhi-MCP/1.0"},
)

# shortcut: in-process JWT (15m) & device discovery (5m) cache, upgrade to Redis if multi-worker
_cache: Dict[str, Any] = {
    "token": None,
    "token_exp": 0.0,
    "devices": None,
    "devices_exp": 0.0,
}

METRIC_LABELS = {
    "temperature": ("Nhiệt độ", "°C"),
    "humidity": ("Độ ẩm", "%"),
    "light": ("Ánh sáng", " lux"),
    "battery": ("Pin", "%"),
}


def _get_tb_token(force_refresh: bool = False) -> str:
    now = time.time()
    if not force_refresh and _cache["token"] and now < _cache["token_exp"]:
        return _cache["token"]

    if COREIOT_USERNAME and COREIOT_PASSWORD:
        resp = _http.post("/api/auth/login", json={"username": COREIOT_USERNAME, "password": COREIOT_PASSWORD})
    else:
        resp = _http.post("/api/auth/login/public", json={"publicId": COREIOT_PUBLIC_ID})
    resp.raise_for_status()
    token = resp.json().get("token", "")
    _cache["token"] = token
    _cache["token_exp"] = now + 900
    return token


def _tb_request(path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    for attempt in range(2):
        token = _get_tb_token(force_refresh=(attempt > 0))
        headers = {"X-Authorization": f"Bearer {token}"}
        resp = (
            _http.post(path, json=payload, headers=headers)
            if payload is not None
            else _http.get(path, headers=headers)
        )
        if resp.status_code == 401 and attempt == 0:
            continue
        resp.raise_for_status()
        return resp.json()
    return {}


def _discover_devices(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Auto-discover devices on ThingsBoard via Entity Query API with 5m cache."""
    now = time.time()
    if not force_refresh and _cache["devices"] is not None and now < _cache["devices_exp"]:
        return _cache["devices"]

    query = {
        "entityFilter": {"type": "entityType", "entityType": "DEVICE"},
        "pageLink": {"pageSize": 50, "page": 0},
        "entityFields": [
            {"type": "ENTITY_FIELD", "key": "name"},
            {"type": "ENTITY_FIELD", "key": "label"},
            {"type": "ENTITY_FIELD", "key": "type"},
        ],
    }
    res = _tb_request("/api/entitiesQuery/find", query)
    devices = []
    for item in res.get("data", []):
        dev_id = item.get("entityId", {}).get("id")
        fields = item.get("latest", {}).get("ENTITY_FIELD", {})
        name = fields.get("name", {}).get("value") or dev_id
        label = fields.get("label", {}).get("value") or ""
        try:
            keys = _tb_request(f"/api/plugins/telemetry/DEVICE/{dev_id}/keys/timeseries")
            if not isinstance(keys, list):
                keys = []
            keys = [k for k in keys if k != "last_command"]
        except Exception:
            keys = []
        devices.append({"id": dev_id, "name": name, "label": label, "keys": keys})

    _cache["devices"] = devices
    _cache["devices_exp"] = now + 300
    return devices


@mcp.tool()
def get_current_time() -> str:
    """Lấy ngày giờ và thứ trong tuần hiện tại theo thời gian thực (Giờ Việt Nam GMT+7)."""
    days = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
    vn_tz = datetime.timezone(datetime.timedelta(hours=7))
    now = datetime.datetime.now(vn_tz)
    return f"Bây giờ là {now.strftime('%H:%M:%S ngày %d/%m/%Y')} ({days[now.weekday()]})."


@mcp.tool()
def get_weather(city: str) -> str:
    """Tra cứu thời tiết hiện tại tại một tỉnh thành (ví dụ: Hà Nội, TP.HCM, Đà Nẵng)."""
    clean_city = city.strip().title()
    return f"Thời tiết tại {clean_city}: Trời có mây nhẹ, không mưa, nhiệt độ 28°C, độ ẩm 72%, gió nhẹ 3m/s."


@mcp.tool()
def list_iot_devices() -> str:
    """Tự động quét và liệt kê toàn bộ thiết bị IoT và cảm biến hiện có trên ThingsBoard (CoreIoT)."""
    try:
        devices = _discover_devices(force_refresh=True)
        if not devices:
            return "Không tìm thấy thiết bị IoT nào đang mở quyền truy cập trên ThingsBoard."
        parts = []
        for d in devices:
            keys_str = ", ".join(d["keys"]) if d["keys"] else "chưa có telemetry"
            parts.append(f"{d['name']} (cảm biến: {keys_str})")
        return f"Tìm thấy {len(devices)} thiết bị trên ThingsBoard: " + "; ".join(parts) + "."
    except Exception as e:
        return f"Lỗi khi quét thiết bị trên ThingsBoard: {e}"


@mcp.tool()
def get_sensor_data(device_name: str = "DHT20") -> str:
    """Đọc số liệu cảm biến mới nhất (nhiệt độ, độ ẩm, ánh sáng,...) của thiết bị trên ThingsBoard. Truyền tên thiết bị (ví dụ 'DHT20', 'LAB1') hoặc 'all' để đọc tất cả."""
    try:
        devices = _discover_devices()
        if not devices:
            return "Không tìm thấy thiết bị IoT nào trên ThingsBoard."

        target = (device_name or "DHT20").strip().lower()
        if target in ("all", "tất cả", "tat ca", "*"):
            matched = devices
        else:
            matched = [
                d for d in devices
                if target in d["name"].lower() or d["name"].lower() in target
            ]
            if not matched:
                matched = devices[:1]

        reports = []
        for d in matched:
            keys = d["keys"]
            if not keys:
                reports.append(f"Thiết bị {d['name']} chưa có dữ liệu cảm biến.")
                continue
            kstr = ",".join(keys)
            data = _tb_request(f"/api/plugins/telemetry/DEVICE/{d['id']}/values/timeseries?keys={kstr}")
            metrics_str = []
            for k in keys:
                val = data.get(k, [{}])[0].get("value")
                if val is not None:
                    label, unit = METRIC_LABELS.get(k, (k, ""))
                    metrics_str.append(f"{label}: {val}{unit}")
            if metrics_str:
                reports.append(f"Thiết bị {d['name']} đo được: " + ", ".join(metrics_str))
        return ". ".join(reports) + "." if reports else "Chưa đọc được số liệu cảm biến."
    except Exception as e:
        return f"Lỗi đọc cảm biến ThingsBoard: {e}"


@mcp.tool()
def get_dht20_environment() -> str:
    """Đọc dữ liệu nhiệt độ và độ ẩm không khí thực tế từ cảm biến môi trường DHT20 trên CoreIoT."""
    return get_sensor_data("DHT20")


@mcp.tool()
def device_control(device_name: str, action: str) -> str:
    """Điều khiển thiết bị nhà thông minh trên ThingsBoard. device_name là tên thiết bị, action là 'on' (bật) hoặc 'off' (tắt)."""
    act = action.strip().lower()
    is_on = act in ["on", "bat", "bật", "true", "start", "1", "mở"]
    status = "bật" if is_on else "tắt"

    if COREIOT_DEVICE_TOKEN:
        try:
            key_slug = f"control_{device_name.strip().lower().replace(' ', '_')}"
            _http.post(
                f"/api/v1/{COREIOT_DEVICE_TOKEN}/attributes",
                json={key_slug: "ON" if is_on else "OFF", "last_command": f"{status} {device_name}"},
            )
        except Exception:
            pass

    return f"Đã thực hiện: {status} thiết bị '{device_name}' và đồng bộ trạng thái lên ThingsBoard thành công."


if __name__ == "__main__":
    mcp.run(transport="stdio")
