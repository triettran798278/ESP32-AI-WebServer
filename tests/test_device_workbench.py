import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import httpx

from tools.device_simulator import app as workbench_app
from tools.device_simulator import devices


class DeviceWorkbenchTest(unittest.TestCase):
    def test_telemetry_batch_validates_before_changing_state(self):
        state = devices.initial_state('Living Room')
        original = state.copy()
        with self.assertRaises(ValueError):
            devices.update_state(state, {'temperature': 22.3, 'lightOn': 1})
        self.assertEqual(state, original)
        with self.assertRaises(ValueError):
            devices.update_state(state, {'humidity': 101})
        devices.update_state(state, {'temperature': 22.3, 'lightOn': True})
        self.assertEqual(state, {'temperature': 22.3, 'humidity': 56, 'lightOn': True})

    def test_hallway_uses_motion_in_auto_mode(self):
        state = devices.initial_state('Hallway')
        self.assertTrue(devices.rpc(state, 'setAutoLight', {'enabled': True})['ok'])
        self.assertEqual(devices.rpc(state, 'setLight', {'state': True})['error'], 'REJECTED')
        devices.update_state(state, {'motionDetected': True})
        self.assertIs(state['lightOn'], True)
        devices.update_state(state, {'motionDetected': False})
        self.assertIs(state['lightOn'], False)

    def test_rpc_is_limited_to_each_devices_contract(self):
        state = devices.initial_state('Dining Room')
        self.assertEqual(devices.rpc(state, 'setFan', {'state': True})['error'], 'UNKNOWN_METHOD')
        self.assertEqual(devices.rpc(state, 'getState', [])['error'], 'INVALID_PARAMS')
        self.assertEqual(devices.rpc(state, 'getState', {}), {'ok': True, 'state': state})

    def test_each_room_has_one_actuator(self):
        for name, (_, _, fields) in devices.DEVICES.items():
            with self.subTest(room=name):
                outputs = [key for key in fields if devices.FIELDS[key].get('method') not in (None, 'setAutoLight')]
                self.assertEqual(len(outputs), 1)

    def test_workbench_app_loads_synthetic_credentials_and_serves_devices(self):
        config = {
            'host': 'https://tb.example.test',
            'tokens': {
                'Living Room': 'synthetic-living-token',
                'Hallway': 'synthetic-hallway-token',
            },
            'initialValues': {
                'Hallway': {'autoLightEnabled': True, 'motionDetected': True},
            },
        }

        async def fake_send(self, request, *args, **kwargs):
            if request.method == 'GET':
                await asyncio.sleep(0.05)
                return httpx.Response(408, request=request)
            return httpx.Response(200, request=request)

        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / 'device-credentials.json'
            config_path.write_text(json.dumps(config), encoding='utf-8')
            with patch.dict(os.environ, {'DEVICE_WORKBENCH_CONFIG': str(config_path)}), \
                 patch.object(httpx.AsyncClient, 'send', new=fake_send):
                with TestClient(workbench_app.app, base_url='http://127.0.0.1') as client:
                    home = client.get('/')
                    self.assertEqual(home.status_code, 200)
                    self.assertIn('Device Workbench', home.text)

                    listed = client.get('/api/devices')
                    self.assertEqual(listed.status_code, 200)
                    by_name = {entry['name']: entry for entry in listed.json()}
                    self.assertEqual(set(by_name), {'Living Room', 'Hallway'})
                    self.assertIs(by_name['Hallway']['values']['lightOn'], True)

                    updated = client.post('/api/devices/Living%20Room', json={'values': {'temperature': 23.5}})
                    self.assertEqual(updated.status_code, 200)
                    body = updated.json()
                    self.assertTrue(body['accepted'])
                    self.assertEqual(body['device']['values']['temperature'], 23.5)
