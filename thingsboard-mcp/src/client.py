"""
ThingsBoard REST API Client.
Interacts with ThingsBoard Community Edition via standard REST API endpoints.
Provides device resolution, latest timeseries querying, and server-side RPC dispatching.
"""

from datetime import datetime, timezone
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union
import httpx

from .config import ThingsBoardConfig
from .schemas import (
    DeviceSummary,
    GetTelemetryResult,
    ListDevicesResult,
    SendRpcResult,
    TelemetryItem,
)

logger = logging.getLogger("thingsboard_mcp.client")

UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


class ThingsBoardError(Exception):
    """Base exception for ThingsBoard API interaction errors."""
    pass


class DeviceNotFoundError(ThingsBoardError):
    """Raised when a specified device cannot be located."""
    pass


class ThingsBoardAuthError(ThingsBoardError):
    """Raised on authentication or permission failure."""
    pass


class ThingsBoardClient:
    """HTTP client communicating with ThingsBoard REST API."""

    def __init__(self, config: ThingsBoardConfig):
        self.config = config
        self.host = config.host.rstrip("/")
        self._jwt_token = config.token
        self.timeout = config.timeout_seconds

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "XiaoZhi-Platform-MCP/1.0"
        }
        if self.config.api_key:
            headers["X-Authorization"] = f"ApiKey {self.config.api_key}"
        elif self._jwt_token:
            headers["X-Authorization"] = f"Bearer {self._jwt_token}"
        return headers

    async def ensure_authenticated(self, client: httpx.AsyncClient) -> None:
        """Authenticate using username/password if API key or token is not provided."""
        if self.config.api_key or self._jwt_token:
            return

        if self.config.username and self.config.password:
            login_url = f"{self.host}/api/auth/login"
            payload = {"username": self.config.username, "password": self.config.password}
            try:
                resp = await client.post(login_url, json=payload, timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    self._jwt_token = data.get("token")
                    logger.info("Successfully authenticated via ThingsBoard login endpoint.")
                else:
                    raise ThingsBoardAuthError(f"Login failed (HTTP {resp.status_code}): {resp.text}")
            except httpx.RequestError as e:
                raise ThingsBoardError(f"Failed to connect to ThingsBoard auth endpoint: {e}")
        else:
            raise ThingsBoardAuthError("No valid ThingsBoard credentials provided.")

    async def list_devices(
        self,
        page_size: int = 50,
        page: int = 0,
        device_type: Optional[str] = None,
    ) -> ListDevicesResult:
        """
        List devices accessible to the authenticated tenant.
        """
        page_size = max(1, min(100, page_size))
        page = max(0, page)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            await self.ensure_authenticated(client)
            url = f"{self.host}/api/tenant/devices"
            params = {"pageSize": page_size, "page": page}
            if device_type:
                params["type"] = device_type

            try:
                resp = await client.get(url, params=params, headers=self._get_headers())
            except httpx.RequestError as e:
                raise ThingsBoardError(f"Network error querying devices: {e}")

            if resp.status_code == 401:
                raise ThingsBoardAuthError("Unauthorized: ThingsBoard API key or token is invalid.")
            if resp.status_code != 200:
                raise ThingsBoardError(f"ThingsBoard device listing failed ({resp.status_code}): {resp.text}")

            data = resp.json()
            raw_devices = data.get("data", [])
            has_next = data.get("hasNext", False)

            devices: List[DeviceSummary] = []
            for d in raw_devices:
                dev_id = d.get("id", {}).get("id") if isinstance(d.get("id"), dict) else d.get("id")
                created_ts = d.get("createdTime")
                iso_time = None
                if created_ts:
                    iso_time = datetime.fromtimestamp(created_ts / 1000.0, tz=timezone.utc).isoformat()

                additional = d.get("additionalInfo") or {}
                is_gw = bool(additional.get("gateway", False))

                devices.append(
                    DeviceSummary(
                        id=str(dev_id),
                        name=d.get("name", "Unnamed"),
                        type=d.get("type", "default"),
                        label=d.get("label") or "",
                        created_time=iso_time,
                        is_gateway=is_gw,
                    )
                )

            return ListDevicesResult(
                total_devices=len(devices),
                page=page,
                has_next=has_next,
                devices=devices,
            )

    async def resolve_device(self, identifier: str) -> Tuple[str, str]:
        """
        Resolve device identifier (UUID or device name) to a (device_id, device_name) tuple.
        """
        clean_id = identifier.strip()
        if UUID_PATTERN.match(clean_id):
            # Already a valid UUID, fetch device to confirm and get name
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                await self.ensure_authenticated(client)
                url = f"{self.host}/api/device/{clean_id}"
                try:
                    resp = await client.get(url, headers=self._get_headers())
                    if resp.status_code == 200:
                        name = resp.json().get("name", clean_id)
                        return clean_id, name
                    elif resp.status_code == 404:
                        raise DeviceNotFoundError(f"Device UUID '{clean_id}' does not exist on ThingsBoard.")
                except httpx.RequestError as e:
                    logger.warning("Could not verify device UUID '%s': %s. Using provided UUID.", clean_id, e)
                    return clean_id, clean_id

        # Search device by name
        res = await self.list_devices(page_size=100, page=0)
        for dev in res.devices:
            if dev.name.lower() == clean_id.lower() or dev.id == clean_id:
                return dev.id, dev.name

        raise DeviceNotFoundError(
            f"Device '{identifier}' not found in ThingsBoard tenant devices."
        )

    @staticmethod
    def _parse_telemetry_value(raw_val: Any) -> Union[float, int, bool, str, dict]:
        """Convert stringified numbers or booleans to native Python types."""
        if not isinstance(raw_val, str):
            return raw_val

        lowered = raw_val.lower()
        if lowered in ("true", "false"):
            return lowered == "true"

        # Try int
        try:
            return int(raw_val)
        except ValueError:
            pass

        # Try float
        try:
            return float(raw_val)
        except ValueError:
            pass

        # Try JSON
        if (raw_val.startswith("{") and raw_val.endswith("}")) or (raw_val.startswith("[") and raw_val.endswith("]")):
            try:
                return json.loads(raw_val)
            except Exception:
                pass

        return raw_val

    async def get_latest_telemetry(
        self,
        device_identifier: str,
        keys: Optional[List[str]] = None,
    ) -> GetTelemetryResult:
        """
        Retrieve latest telemetry values for a device and optional keys list.
        """
        device_id, device_name = await self.resolve_device(device_identifier)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            await self.ensure_authenticated(client)
            url = f"{self.host}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
            params = {}
            if keys:
                clean_keys = [k.strip() for k in keys if k.strip()]
                if clean_keys:
                    params["keys"] = ",".join(clean_keys)

            try:
                resp = await client.get(url, params=params, headers=self._get_headers())
            except httpx.RequestError as e:
                raise ThingsBoardError(f"Network error querying telemetry for device '{device_name}': {e}")

            if resp.status_code == 401:
                raise ThingsBoardAuthError("Unauthorized: ThingsBoard API key or token is invalid.")
            if resp.status_code == 404:
                raise DeviceNotFoundError(f"Device '{device_id}' telemetry endpoint returned 404.")
            if resp.status_code != 200:
                raise ThingsBoardError(f"ThingsBoard telemetry query failed ({resp.status_code}): {resp.text}")

            raw_data = resp.json()
            telemetry_map: Dict[str, TelemetryItem] = {}

            for key_name, entries in raw_data.items():
                if entries and isinstance(entries, list):
                    latest_entry = entries[0]
                    val = self._parse_telemetry_value(latest_entry.get("value"))
                    ts_ms = latest_entry.get("ts", 0)
                    iso_time = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()
                    telemetry_map[key_name] = TelemetryItem(
                        value=val,
                        timestamp=iso_time,
                        epoch_ms=ts_ms,
                    )

            return GetTelemetryResult(
                device_id=device_id,
                device_name=device_name,
                telemetry_keys=list(telemetry_map.keys()),
                telemetry=telemetry_map,
            )

    async def send_rpc(
        self,
        device_identifier: str,
        method: str,
        params: Any = None,
        timeout_ms: int = 5000,
        two_way: bool = True,
    ) -> SendRpcResult:
        """
        Send a server-side RPC command to a device.
        Handles timeout (504), device not found, and error responses cleanly.
        """
        if not method or not method.strip():
            return SendRpcResult(
                success=False,
                device_id="",
                method="",
                error="RPC method name cannot be empty.",
            )

        try:
            device_id, device_name = await self.resolve_device(device_identifier)
        except DeviceNotFoundError as e:
            return SendRpcResult(
                success=False,
                device_id=device_identifier,
                method=method,
                error=str(e),
            )

        endpoint_type = "twoway" if two_way else "oneway"
        url = f"{self.host}/api/rpc/{endpoint_type}/{device_id}"

        payload = {
            "method": method.strip(),
            "params": params if params is not None else {},
            "timeout": timeout_ms,
        }

        # Use an HTTP timeout slightly higher than the RPC device timeout to prevent client abort
        http_timeout = max(self.timeout, (timeout_ms / 1000.0) + 3.0)

        async with httpx.AsyncClient(timeout=http_timeout) as client:
            await self.ensure_authenticated(client)
            try:
                resp = await client.post(url, json=payload, headers=self._get_headers())
            except httpx.TimeoutException:
                return SendRpcResult(
                    success=False,
                    device_id=device_id,
                    device_name=device_name,
                    method=method,
                    error=f"RPC timeout: ThingsBoard gateway did not respond within {http_timeout}s.",
                )
            except httpx.RequestError as e:
                return SendRpcResult(
                    success=False,
                    device_id=device_id,
                    device_name=device_name,
                    method=method,
                    error=f"Network error sending RPC to '{device_name}': {e}",
                )

            # ThingsBoard returns 504 when device is offline or doesn't reply in time
            if resp.status_code == 504:
                return SendRpcResult(
                    success=False,
                    device_id=device_id,
                    device_name=device_name,
                    method=method,
                    error=f"RPC timeout: Device '{device_name}' did not respond within {timeout_ms}ms.",
                )

            if resp.status_code in (200, 201):
                resp_payload = None
                if resp.text:
                    try:
                        resp_payload = resp.json()
                    except Exception:
                        resp_payload = resp.text
                return SendRpcResult(
                    success=True,
                    device_id=device_id,
                    device_name=device_name,
                    method=method,
                    response=resp_payload,
                )

            # Error from ThingsBoard
            error_msg = resp.text or f"HTTP error {resp.status_code}"
            return SendRpcResult(
                success=False,
                device_id=device_id,
                device_name=device_name,
                method=method,
                error=f"ThingsBoard RPC error ({resp.status_code}): {error_msg}",
            )
