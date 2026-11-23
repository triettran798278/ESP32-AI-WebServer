"""Simulate the ThingsBoard MCP test device using HTTP long polling."""

import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

RPC_CONTRACT = {
    'version': 1,
    'methods': {
        'setPower': {'description': 'Set the power switch on or off', 'params': {
            'type': 'object', 'properties': {'state': {'type': 'boolean'}},
            'required': ['state'], 'additionalProperties': False}},
        'getState': {'description': 'Read the power switch state', 'params': {
            'type': 'object', 'properties': {}, 'additionalProperties': False}},
        'togglePower': {'description': 'Toggle the power switch', 'params': {
            'type': 'object', 'properties': {}, 'additionalProperties': False}},
    },
}

ROOM_STATES = {
    'LivingRoom': {'temperature': 24.5, 'humidity': 56, 'lightOn': False},
    'BedRoom': {'temperature': 25.2, 'humidity': 60, 'fanOn': False},
    'Kitchen': {'temperature': 27.0, 'gasDetected': False, 'smokeDetected': False},
}
ROOM_ACTUATORS = {
    'LivingRoom': ('setLight', 'lightOn'),
    'BedRoom': ('setFan', 'fanOn'),
}


def update_room_sample(profile, state, elapsed):
    if profile == 'Kitchen':
        phase = int(elapsed // 30) % 4
        state['gasDetected'] = phase == 1
        state['smokeDetected'] = phase == 2


def room_reply(profile, method, params, state):
    actuator, key = ROOM_ACTUATORS.get(profile, (None, None))
    if method == 'getState':
        if params != {}:
            return {'ok': False, 'error': 'INVALID_PARAMS'}
    elif actuator is not None and method == actuator:
        if not isinstance(params, dict) or set(params) != {'state'} or type(params['state']) is not bool:
            return {'ok': False, 'error': 'INVALID_PARAMS'}
        state[key] = params['state']
    else:
        return {'ok': False, 'error': 'UNKNOWN_METHOD'}
    return {'ok': True, 'state': state.copy()}


def reply(method, params, state):
    if method in ('getState', 'togglePower') and params != {}:
        return {'error': f'{method} requires an empty object'}
    if method in ('turnOnPower', 'turnOffPower'):
        state['power'] = method == 'turnOnPower'
    elif method == 'togglePower':
        state['power'] = not state['power']
    elif method == 'setPower':
        if not isinstance(params, dict) or set(params) != {'state'} or not isinstance(params['state'], bool):
            return {'error': 'setPower requires a boolean state'}
        state['power'] = params['state']
    elif method in ('setState', 'setLight'):
        state['power'] = params.get('state', params.get('value', params)) if isinstance(params, dict) else params
    elif method not in ('getState', 'getPower'):
        return {'error': 'Unsupported test method', 'method': method}
    return {'power': state['power'], 'simulated': True}


def main():
    host = (os.environ.get('TB_HOST') or os.environ.get('THINGSBOARD_HOST') or '').rstrip('/')
    if not host:
        raise SystemExit('Set TB_HOST or THINGSBOARD_HOST')
    profile = os.environ.get('TB_SIM_PROFILE')
    if profile is not None and profile not in ROOM_STATES:
        raise SystemExit('TB_SIM_PROFILE must be LivingRoom, BedRoom or Kitchen')
    with open(os.environ['TB_DEVICE_TOKEN_FILE'], encoding='utf-8') as token_file:
        base = f"{host}/api/v1/{token_file.read().strip()}"
    state = ROOM_STATES[profile].copy() if profile else {'power': False}
    started_at = time.monotonic()
    telemetry_at = 0
    attributes_sent = profile is not None
    print(f'Simulator started: {host}', flush=True)

    def request(path, payload=None, timeout=35):
        data = None if payload is None else json.dumps(payload).encode()
        req = Request(base + path, data=data, headers={'Content-Type': 'application/json', 'User-Agent': 'python-requests/2.32.3'})
        with urlopen(req, timeout=timeout) as response:
            return response.read()

    while True:
        try:
            if not attributes_sent:
                request('/attributes', {'rpc_methods': 'setPower {"state": true|false}; getState {}; togglePower {}',
                                        'rpc_contract': RPC_CONTRACT})
                attributes_sent = True
            if time.monotonic() >= telemetry_at:
                if profile:
                    update_room_sample(profile, state, time.monotonic() - started_at)
                    telemetry = state
                else:
                    telemetry = {'test_temperature_c': 24.5, 'test_humidity_percent': 56,
                                 'test_co2_ppm': 650, 'test_data': True, 'test_power': state['power']}
                request('/telemetry', telemetry)
                print(f'Telemetry sent: {json.dumps(telemetry)}', flush=True)
                telemetry_at = time.monotonic() + 30
            poll_ms = 10000 if profile else 25000
            body = request(f'/rpc?timeout={poll_ms}')
            if body:
                command = json.loads(body)
                print(f"RPC received: {command.get('method')} {json.dumps(command.get('params'))}", flush=True)
                if profile:
                    update_room_sample(profile, state, time.monotonic() - started_at)
                    result = room_reply(profile, command.get('method'), command.get('params'), state)
                else:
                    result = reply(command.get('method'), command.get('params'), state)
                request('/rpc/' + str(command['id']), result)
                print(f'RPC response sent: {json.dumps(result)}', flush=True)
                telemetry_at = 0
        except HTTPError as exc:
            if exc.code == 408:
                continue
            print(f'Simulator HTTP error {exc.code}; retrying', flush=True)
            time.sleep(3)
        except (URLError, TimeoutError, OSError, ValueError, KeyError):
            print('Simulator connection error; retrying', flush=True)
            time.sleep(3)


if __name__ == '__main__':
    main()
