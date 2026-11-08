"""
Unit tests for ThingsBoard REST Client using mocked HTTP responses.
"""

import json
import unittest
from unittest.mock import patch, AsyncMock
import httpx

from src.client import (
    ThingsBoardClient,
    ThingsBoardError,
    ThingsBoardAuthError,
    DeviceNotFoundError,
)
from src.config import ThingsBoardConfig


class TestThingsBoardClient(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.config = ThingsBoardConfig(
            host="http://tb-mock.test:8080",
            api_key="tb_mock_test_key",
            timeout_seconds=5.0,
        )
        self.client = ThingsBoardClient(self.config)

    def test_auth_headers_with_api_key(self):
        headers = self.client._get_headers()
        self.assertEqual(headers["X-Authorization"], "ApiKey tb_mock_test_key")
        self.assertEqual(headers["Content-Type"], "application/json")

    def test_auth_headers_with_token(self):
        jwt_config = ThingsBoardConfig(
            host="http://tb-mock.test:8080",
            token="mock_jwt_token",
        )
        client = ThingsBoardClient(jwt_config)
        headers = client._get_headers()
        self.assertEqual(headers["X-Authorization"], "Bearer mock_jwt_token")

    @patch("httpx.AsyncClient.get")
    async def test_list_devices_success(self, mock_get):
        mock_response = httpx.Response(
            status_code=200,
            json={
                "data": [
                    {
                        "id": {"id": "11111111-2222-3333-4444-555555555555", "entityType": "DEVICE"},
                        "name": "Smart-Sensor-01",
                        "type": "environmental-sensor",
                        "label": "Living Room Sensor",
                        "createdTime": 1700000000000,
                        "additionalInfo": {"gateway": False}
                    },
                    {
                        "id": {"id": "22222222-2222-3333-4444-555555555555", "entityType": "DEVICE"},
                        "name": "Gateway-Hub",
                        "type": "gateway",
                        "label": "",
                        "createdTime": 1700000000000,
                        "additionalInfo": {"gateway": True}
                    }
                ],
                "hasNext": False,
                "totalElements": 2
            },
            request=httpx.Request("GET", "http://tb-mock.test:8080/api/tenant/devices")
        )
        mock_get.return_value = mock_response

        result = await self.client.list_devices(page_size=10, page=0)
        self.assertEqual(result.total_devices, 2)
        self.assertEqual(result.devices[0].name, "Smart-Sensor-01")
        self.assertEqual(result.devices[0].id, "11111111-2222-3333-4444-555555555555")
        self.assertFalse(result.devices[0].is_gateway)
        self.assertTrue(result.devices[1].is_gateway)

    @patch("httpx.AsyncClient.get")
    async def test_list_devices_auth_error(self, mock_get):
        mock_response = httpx.Response(
            status_code=401,
            text="Invalid API Key",
            request=httpx.Request("GET", "http://tb-mock.test:8080/api/tenant/devices")
        )
        mock_get.return_value = mock_response

        with self.assertRaises(ThingsBoardAuthError):
            await self.client.list_devices()

    @patch.object(ThingsBoardClient, "list_devices")
    async def test_resolve_device_by_name(self, mock_list_devices):
        from src.schemas import ListDevicesResult, DeviceSummary
        mock_list_devices.return_value = ListDevicesResult(
            total_devices=1,
            page=0,
            has_next=False,
            devices=[
                DeviceSummary(
                    id="11111111-2222-3333-4444-555555555555",
                    name="Virtual-Environmental-Monitor",
                    type="sensor",
                    label=""
                )
            ]
        )

        dev_id, dev_name = await self.client.resolve_device("virtual-environmental-monitor")
        self.assertEqual(dev_id, "11111111-2222-3333-4444-555555555555")
        self.assertEqual(dev_name, "Virtual-Environmental-Monitor")

    @patch.object(ThingsBoardClient, "list_devices")
    async def test_resolve_device_not_found(self, mock_list_devices):
        from src.schemas import ListDevicesResult
        mock_list_devices.return_value = ListDevicesResult(
            total_devices=0,
            page=0,
            has_next=False,
            devices=[]
        )

        with self.assertRaises(DeviceNotFoundError):
            await self.client.resolve_device("NonExistentDevice")

    @patch.object(ThingsBoardClient, "resolve_device")
    @patch("httpx.AsyncClient.get")
    async def test_get_latest_telemetry_success(self, mock_get, mock_resolve):
        mock_resolve.return_value = ("11111111-2222-3333-4444-555555555555", "TestDevice")
        mock_response = httpx.Response(
            status_code=200,
            json={
                "temperature": [{"ts": 1700000000000, "value": "26.4"}],
                "humidity": [{"ts": 1700000000000, "value": "62.5"}],
                "active": [{"ts": 1700000000000, "value": "true"}]
            },
            request=httpx.Request("GET", "http://tb-mock.test:8080/api/plugins/telemetry/DEVICE/1111/values/timeseries")
        )
        mock_get.return_value = mock_response

        res = await self.client.get_latest_telemetry("TestDevice", keys=["temperature", "humidity"])
        self.assertEqual(res.device_id, "11111111-2222-3333-4444-555555555555")
        self.assertEqual(res.device_name, "TestDevice")
        self.assertEqual(res.telemetry["temperature"].value, 26.4)
        self.assertEqual(res.telemetry["humidity"].value, 62.5)
        self.assertTrue(res.telemetry["active"].value is True)

    @patch.object(ThingsBoardClient, "resolve_device")
    @patch("httpx.AsyncClient.post")
    async def test_send_rpc_success(self, mock_post, mock_resolve):
        mock_resolve.return_value = ("11111111-2222-3333-4444-555555555555", "SmartRelay")
        mock_response = httpx.Response(
            status_code=200,
            json={"result": "ok", "state": True},
            request=httpx.Request("POST", "http://tb-mock.test:8080/api/rpc/twoway/1111")
        )
        mock_post.return_value = mock_response

        res = await self.client.send_rpc(
            device_identifier="SmartRelay",
            method="setGpio",
            params={"pin": 4, "value": 1},
            timeout_ms=3000,
            two_way=True
        )
        self.assertTrue(res.success)
        self.assertEqual(res.method, "setGpio")
        self.assertEqual(res.response, {"result": "ok", "state": True})
        self.assertIsNone(res.error)

    @patch.object(ThingsBoardClient, "resolve_device")
    @patch("httpx.AsyncClient.post")
    async def test_send_rpc_timeout_504(self, mock_post, mock_resolve):
        mock_resolve.return_value = ("11111111-2222-3333-4444-555555555555", "OfflineDevice")
        mock_response = httpx.Response(
            status_code=504,
            text="",
            request=httpx.Request("POST", "http://tb-mock.test:8080/api/rpc/twoway/1111")
        )
        mock_post.return_value = mock_response

        res = await self.client.send_rpc(
            device_identifier="OfflineDevice",
            method="reboot",
            timeout_ms=2000
        )
        self.assertFalse(res.success)
        self.assertIn("RPC timeout", res.error)
        self.assertIn("did not respond within 2000ms", res.error)

    async def test_send_rpc_empty_method(self):
        res = await self.client.send_rpc("SomeDevice", method="")
        self.assertFalse(res.success)
        self.assertIn("cannot be empty", res.error)


if __name__ == "__main__":
    unittest.main()
