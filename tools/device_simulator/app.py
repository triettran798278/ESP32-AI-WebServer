"""Local control plane for the ThingsBoard HTTPS device API."""

import asyncio
from collections import deque
from contextlib import asynccontextmanager
import json
import logging
import os
from pathlib import Path
from time import time
from urllib.parse import quote, urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
import httpx
from pydantic import BaseModel, StrictBool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .devices import DEVICES, FIELDS, initial_state, rpc, update_state

STATIC = Path(__file__).with_name('static')
logging.getLogger('httpx').setLevel(logging.WARNING)


class Device:
    def __init__(self, name, base_url, client):
        self.name = name
        self.base_url = base_url
        self.client = client
        self.values = initial_state(name)
        self.enabled = True
        self.status = 'connecting'
        self.last_sent = None
        self.events = deque(maxlen=12)
        self.send_lock = asyncio.Lock()

    def record(self, kind, detail):
        self.events.appendleft({'time': time(), 'kind': kind, 'detail': detail})

    def snapshot(self):
        label, group, keys = DEVICES[self.name]
        return {'name': self.name, 'label': label, 'group': group, 'values': self.values.copy(),
                'fields': {key: FIELDS[key] for key in keys}, 'enabled': self.enabled,
                'status': self.status if self.enabled else 'paused', 'lastSent': self.last_sent,
                'events': list(self.events)}

    async def publish(self, manual=False):
        async with self.send_lock:
            if not self.enabled:
                return False
            values = self.values.copy()
            try:
                response = await self.client.post(self.base_url + '/telemetry', json=values)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                if self.status != 'unreachable' or manual:
                    self.record('Error', f'Telemetry received HTTP {code}' if code else 'Telemetry request failed')
                self.status = 'unreachable'
                return False
            self.status = 'connected'
            self.last_sent = time()
            self.record('Telemetry', 'Payload accepted' if manual else 'Scheduled payload accepted')
            return True

    async def telemetry_loop(self):
        while True:
            await self.publish()
            await asyncio.sleep(30)

    async def rpc_loop(self):
        while True:
            if not self.enabled:
                await asyncio.sleep(1)
                continue
            try:
                response = await self.client.get(self.base_url + '/rpc', params={'timeout': 10000})
                if response.status_code == 408:
                    continue
                response.raise_for_status()
                if not response.content:
                    await asyncio.sleep(1)
                    continue
                command = response.json()
                request_id = str(command['id'])
                if not request_id.isascii() or not request_id.isdecimal():
                    raise ValueError('Invalid RPC ID')
                method = command.get('method')
                result = rpc(self.values, method, command.get('params')) if self.enabled else {
                    'ok': False, 'error': 'REJECTED'}
                reply = await self.client.post(self.base_url + '/rpc/' + request_id, json=result)
                reply.raise_for_status()
                self.record('RPC', (method if isinstance(method, str) else 'Unknown method')[:80])
                if result['ok'] and method != 'getState':
                    await self.publish(manual=True)
            except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
                await asyncio.sleep(3)


@asynccontextmanager
async def lifespan(app):
    config = json.loads(Path(os.environ['DEVICE_WORKBENCH_CONFIG']).read_text())
    origin = urlsplit(config['host'].rstrip('/'))
    tokens = config['tokens']
    if origin.scheme != 'https' or not origin.hostname or origin.username or origin.password or origin.path or origin.query or origin.fragment:
        raise ValueError('Device transport needs an HTTPS origin')
    if not tokens or not tokens.keys() <= DEVICES.keys() or not all(isinstance(token, str) and token for token in tokens.values()):
        raise ValueError('Invalid device credential map')
    if len(set(tokens.values())) != len(tokens):
        raise ValueError('Each device needs its own access token')
    async with httpx.AsyncClient(timeout=16, headers={'User-Agent': 'python-requests/2.32.3'},
                                 trust_env=False) as client:
        app.state.devices = {name: Device(name, f"{origin.geturl()}/api/v1/{quote(tokens[name], safe='')}", client)
                             for name in DEVICES if name in tokens}
        for name, values in config.get('initialValues', {}).items():
            if name in app.state.devices:
                state = app.state.devices[name].values
                patch = dict(values)
                if patch.get('autoLightEnabled'):
                    patch.pop('lightOn', None)
                update_state(state, patch)
        tasks = [asyncio.create_task(run()) for device in app.state.devices.values()
                 for run in (device.telemetry_loop, device.rpc_loop)]
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost'])


class DeviceUpdate(BaseModel):
    enabled: StrictBool | None = None
    values: dict[str, object] | None = None


@app.get('/api/devices')
async def list_devices(request: Request):
    return [device.snapshot() for device in request.app.state.devices.values()]


@app.post('/api/devices/{name}')
async def send_device(name: str, update: DeviceUpdate, request: Request):
    if request.headers.get('content-type', '').split(';', 1)[0] != 'application/json':
        raise HTTPException(415, 'Use application/json')
    device = request.app.state.devices.get(name)
    if device is None:
        raise HTTPException(404, 'Unknown device')
    if update.values is not None:
        if not device.enabled and update.enabled is not True:
            raise HTTPException(409, 'Resume the device before sending telemetry')
        try:
            update_state(device.values, update.values)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    if update.enabled is not None and device.enabled != update.enabled:
        device.enabled = update.enabled
        device.record('Device', 'Resumed' if device.enabled else 'Paused')
    accepted = await device.publish(manual=True)
    return {'accepted': accepted, 'device': device.snapshot()}


app.mount('/', StaticFiles(directory=STATIC, html=True), name='workbench')
