"""Per-agent ThingsBoard reads, capability discovery, and validated RPC."""

from contextlib import asynccontextmanager
import contextvars
import importlib
import json
import os
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
import uuid
import httpx

UUID_RE = re.compile(r'[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}')
_SCOPED_REGISTRY: contextvars.ContextVar = contextvars.ContextVar("tb_scoped_registry", default=None)


def redact_credentials(value, credential):
    if isinstance(value, dict):
        return {key: ('[redacted]' if re.search(r'password|credential|secret|api.?key|access.?token|refresh.?token', str(key), re.IGNORECASE) else redact_credentials(item, credential))
                for key, item in value.items()}
    if isinstance(value, list):
        return [redact_credentials(item, credential) for item in value]
    if isinstance(value, str) and credential:
        return value.replace(credential, "[redacted]")
    return value


class _ToolCollector:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def register(fn):
            self.tools[fn.__name__] = fn
            return fn
        return register


def _load_mcp_modules():
    capabilities = importlib.import_module('thingsboard-mcp.src.capabilities')
    tb_client = importlib.import_module('thingsboard-mcp.src.client')
    tb_config = importlib.import_module('thingsboard-mcp.src.config')
    cap_tools = importlib.import_module('thingsboard-mcp.src.tools.capabilities')
    return capabilities, tb_client, tb_config, cap_tools


def _create_mcp_runtime(config, profile_id):
    capabilities, tb_client, tb_config, cap_tools = _load_mcp_modules()
    settings = tb_config.ThingsBoardConfig(
        host=config['host'],
        api_key=config['api_key'],
        timeout_seconds=config.get('timeout_seconds', 10.0),
        profile_id=profile_id,
    )
    connection = tb_client.ThingsBoardClient(settings)
    data_dir = Path(os.getenv('PLATFORM_DATA_DIR', '/app/data' if os.path.exists('/app') else './data'))
    data_dir.mkdir(parents=True, exist_ok=True)
    registry = capabilities.CapabilityRegistry(connection, data_dir / 'capabilities.sqlite3')
    collector = _ToolCollector()
    cap_tools.register_capability_tools(collector, connection, registry)
    return connection, registry, collector.tools


async def _all_devices(client, host, headers):
    devices = []
    page = 0
    endpoint = "/api/tenant/devices"
    while True:
        response = await client.get(f"{host}{endpoint}?pageSize=100&page={page}", headers=headers)
        if response.status_code == 403 and endpoint == "/api/tenant/devices":
            identity = await client.get(f"{host}/api/auth/user", headers=headers)
            identity.raise_for_status()
            user = identity.json()
            if user.get("authority") != "CUSTOMER_USER":
                response.raise_for_status()
            customer_id = str(uuid.UUID(user["customerId"]["id"]))
            endpoint = f"/api/customer/{customer_id}/devices"
            continue
        response.raise_for_status()
        body = response.json()
        devices.extend(body.get("data", []))
        if not body.get("hasNext", False):
            return devices
        page += 1


def _normalize_device_name(value):
    return re.sub(r'[\s_-]+', ' ', value or '').strip().casefold()


def _matching_device(devices, name):
    if not name:
        return None
    target = name.strip().casefold()
    matches = [d for d in devices if target in (
        (d.get("name") or "").casefold(),
        (d.get("label") or "").casefold(),
        (d.get("id", {}).get("id") or "").casefold(),
    )]
    if len(matches) == 1:
        return matches[0]
    if matches:
        return None
    norm_target = _normalize_device_name(name)
    if not norm_target:
        return None
    norm_matches = [d for d in devices if norm_target in (
        _normalize_device_name(d.get("name")),
        _normalize_device_name(d.get("label")),
    )]
    return norm_matches[0] if len(norm_matches) == 1 else None


def _registry_scope_key(config, profile_id):
    return ((config.get('host') or '').rstrip('/'), config.get('api_key') or '', profile_id)


@asynccontextmanager
async def scoped_registry(config, profile_id):
    """Refresh CapabilityRegistry once and reuse it for authorize_rpc within this task scope."""
    if not profile_id:
        yield None
        return
    connection, registry, _ = _create_mcp_runtime(config, profile_id)
    await registry.refresh()
    token = _SCOPED_REGISTRY.set((_registry_scope_key(config, profile_id), connection, registry))
    try:
        yield registry
    finally:
        _SCOPED_REGISTRY.reset(token)


async def authorize_rpc(config, profile_id, device_id, method, params):
    """Refresh and validate against the same registry used by the MCP server."""
    if not profile_id:
        return 'An agent profile is required for RPC authorization.'
    registry = None
    resolved_id = None
    try:
        scoped = _SCOPED_REGISTRY.get()
        scope_key = _registry_scope_key(config, profile_id)
        if scoped and scoped[0] == scope_key and getattr(scoped[2], 'fresh', False):
            _, connection, registry = scoped
            resolved_id = next((d.id for d in getattr(registry, 'devices', ()) if d.id == device_id), None)
            if not resolved_id:
                resolved_id, _ = await connection.resolve_device(device_id)
        else:
            connection, registry, _ = _create_mcp_runtime(config, profile_id)
            await registry.refresh()
            resolved_id, _ = await connection.resolve_device(device_id)
        registry.validate(resolved_id, method, params)
        return None
    except Exception as exc:
        if exc.__class__.__name__ in ('CapabilityError', 'DeviceNotFoundError'):
            message = f'RPC not sent: capability discovery or parameter validation failed ({exc})'
            if registry is not None and resolved_id and exc.__class__.__name__ == 'CapabilityError':
                available = [
                    {'method': item['method'], 'params': item['parameter_schema']}
                    for item in registry.list(resolved_id) if item.get('schema_complete')
                ]
                if "is not of type 'boolean'" in str(exc):
                    message += ' Use unquoted JSON booleans true or false (not strings).'
                if available:
                    message += f' Available methods for this device: {json.dumps(available, ensure_ascii=False)}.'
            return message
        return 'RPC not sent: capability discovery or parameter validation failed.'


async def execute(client, config, name, args, read_only=False, profile_id=None):
    host = (config.get('host') or '').rstrip('/')
    key = config.get('api_key') or ''
    if not host or not key:
        return {'success': False, 'error': 'ThingsBoard host or API key is not configured.'}
    headers = {'X-Authorization': f'ApiKey {key}'}
    args = args if isinstance(args, dict) else {}
    try:
        if name == 'discover_capabilities':
            if not profile_id:
                return {'success': False, 'error': 'An agent profile is required.'}
            if (args.get('device_identifier') or args.get('device_name') or args.get('device_id') or '').strip():
                return await execute(client, config, 'list_available_rpc', args, read_only=read_only, profile_id=profile_id)
            _, _, mcp_tools = _create_mcp_runtime(config, profile_id)
            return redact_credentials(await mcp_tools['discover_capabilities'](), key)

        if name == 'get_platform_summary':
            if not profile_id:
                return {'success': False, 'error': 'An agent profile is required.'}
            _, _, mcp_tools = _create_mcp_runtime(config, profile_id)
            return redact_credentials(await mcp_tools['get_platform_summary'](), key)

        if name == 'list_available_rpc':
            if not profile_id:
                return {'success': False, 'error': 'An agent profile is required.'}
            identifier = (args.get('device_identifier') or args.get('device_name') or args.get('device_id') or '').strip()
            if not identifier:
                return {'status': 'error', 'success': False, 'error_code': 'device_not_found',
                        'error': 'A device name or UUID is required.'}
            if UUID_RE.fullmatch(identifier):
                resolved_id = identifier
            else:
                devices = await _all_devices(client, host, headers)
                matched = _matching_device(devices, identifier)
                if not matched:
                    return {'status': 'error', 'success': False, 'error_code': 'device_not_found',
                            'error': f"Device '{identifier}' not found or name is ambiguous.",
                            'devices': [{'name': d.get('name'), 'label': d.get('label'),
                                         'id': d.get('id', {}).get('id')} for d in devices]}
                resolved_id = matched['id']['id']
            _, _, mcp_tools = _create_mcp_runtime(config, profile_id)
            return redact_credentials(await mcp_tools['list_available_rpc'](resolved_id), key)

        if name == 'list_devices':
            devices = await _all_devices(client, host, headers)
            result = [{'name': d.get('name'), 'label': d.get('label'), 'type': d.get('type'),
                       'id': d.get('id', {}).get('id')} for d in devices]
            return {'status': 'success', 'success': True, 'devices': redact_credentials(result, key)}

        if name == 'get_telemetry':
            dev_name = (args.get('device_name') or args.get('device_identifier') or '').strip()
            devices = await _all_devices(client, host, headers)
            matched = _matching_device(devices, dev_name)
            if not matched:
                return {'status': 'error', 'success': False, 'error_code': 'device_not_found',
                        'message': f"Device '{dev_name}' telemetry not found or name is ambiguous",
                        'error': f"Device '{dev_name}' telemetry not found or name is ambiguous"}
            dev_id = matched['id']['id']
            params = {}
            keys = args.get('keys')
            if isinstance(keys, list) and keys:
                clean_keys = [str(k).strip() for k in keys if str(k).strip()]
                if clean_keys:
                    params['keys'] = ','.join(clean_keys)
            response = await client.get(f"{host}/api/plugins/telemetry/DEVICE/{dev_id}/values/timeseries",
                                        params=params or None, headers=headers)
            response.raise_for_status()
            telemetry = redact_credentials(response.json(), key)
            return {'status': 'success', 'success': True, 'device': matched.get('name'), 'device_id': dev_id,
                    'telemetry': telemetry,
                    'message': 'Device found; no telemetry is available.' if not telemetry else 'Device found; telemetry is available.'}

        if name in ('send_rpc', 'execute_device_action'):
            if read_only:
                return {'status': 'forbidden', 'success': False, 'confirmed': False, 'delivery': 'failed',
                        'error_code': 'forbidden', 'message': 'Agent policy does not allow RPC.',
                        'error': 'RPC is disabled by this agent policy.'}
            dev_name = (args.get('device_identifier') or args.get('device_name') or args.get('device_id') or '').strip()
            if UUID_RE.fullmatch(dev_name):
                device_id = dev_name
                resolved_name = dev_name
            else:
                devices = await _all_devices(client, host, headers)
                matched = _matching_device(devices, dev_name)
                if not matched:
                    return {'status': 'error', 'success': False, 'confirmed': False, 'delivery': 'failed',
                            'error_code': 'device_not_found',
                            'message': f"Device '{dev_name}' not found or name is ambiguous. Identify the exact device before calling RPC.",
                            'error': f"Device '{dev_name}' not found or name is ambiguous. Identify the exact device before calling RPC.",
                            'devices': [{'name': d.get('name'), 'label': d.get('label'),
                                         'id': d.get('id', {}).get('id')} for d in devices]}
                device_id = matched['id']['id']
                resolved_name = matched.get('name') or dev_name
            method = str(args.get('method') or '').strip()
            if not method:
                return {'status': 'error', 'success': False, 'confirmed': False, 'delivery': 'failed',
                        'error_code': 'unsupported_method', 'message': 'RPC method is required.',
                        'error': 'RPC method is required.'}
            raw_params = args.get('params')
            if raw_params is None:
                params = {}
            elif isinstance(raw_params, str):
                try:
                    params = json.loads(raw_params)
                except ValueError:
                    return {'status': 'error', 'success': False, 'confirmed': False, 'delivery': 'failed',
                            'error_code': 'invalid_params', 'message': 'RPC parameters must be valid JSON.',
                            'error': 'RPC parameters must be valid JSON.'}
            else:
                params = raw_params
            two_way = args.get('two_way', True)
            timeout_ms = args.get('timeout_ms', 5000)
            rpc_result = await execute(
                client, config, 'thingsboard_rpc',
                {'device_id': device_id, 'method': method, 'params': params,
                 'two_way': two_way, 'timeout_ms': timeout_ms},
                read_only=read_only, profile_id=profile_id,
            )
            if rpc_result.get('error_code') == 'device_not_found' and 'devices' not in rpc_result:
                try:
                    devices = await _all_devices(client, host, headers)
                    rpc_result['devices'] = [{'name': d.get('name'), 'label': d.get('label'),
                                              'id': d.get('id', {}).get('id')} for d in devices]
                except Exception:
                    pass
            return {'status': 'success' if rpc_result.get('success') else 'error',
                    'device': resolved_name, 'device_id': device_id, 'method': method, **rpc_result}

        if name == 'thingsboard_get':
            path = args.get('path', '')
            parsed = urlsplit(path)
            decoded = unquote(parsed.path)
            if (not path.startswith('/api/') or parsed.scheme or parsed.netloc or parsed.fragment
                    or any(part in ('.', '..') for part in decoded.split('/'))
                    or '\\' in decoded or '%' in decoded or any(ord(c) < 32 for c in decoded)
                    or re.search(r'credential|password|secret|api.?key|token', decoded, re.IGNORECASE)):
                return {'success': False, 'error': 'Invalid ThingsBoard API path.'}
            response = await client.get(host + path, params=args.get('query'), headers=headers)
        elif name == 'thingsboard_query':
            path = args.get('path', '')
            if path not in ('/api/entitiesQuery/find', '/api/entitiesQuery/count',
                            '/api/alarmsQuery/find', '/api/alarmsQuery/count', '/api/v2/entitiesQuery/find/keys') or not isinstance(args.get('body'), dict):
                return {'success': False, 'error': 'Invalid read-only ThingsBoard query.'}
            response = await client.post(host + path, json=args['body'], headers=headers)
        elif name == 'thingsboard_rpc':
            if read_only:
                return {'success': False, 'confirmed': False, 'delivery': 'failed',
                        'error_code': 'forbidden', 'error': 'RPC is disabled by this agent policy.'}
            device_id = args.get('device_id', '')
            method = args.get('method', '')
            if not UUID_RE.fullmatch(device_id) or not isinstance(method, str) or not method.strip():
                return {'success': False, 'confirmed': False, 'delivery': 'failed',
                        'error_code': 'invalid_params', 'error': 'A device UUID and RPC method are required.'}
            two_way = args.get('two_way', True)
            if not isinstance(two_way, bool):
                return {'success': False, 'confirmed': False, 'delivery': 'failed',
                        'error_code': 'invalid_params', 'error': 'RPC delivery mode must be boolean.'}
            mode = 'twoway' if two_way else 'oneway'
            timeout_ms = args.get('timeout_ms', 5000)
            if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int) or not 1 <= timeout_ms <= 120000:
                return {'success': False, 'confirmed': False, 'delivery': 'failed',
                        'error_code': 'invalid_params', 'error': 'RPC timeout must be between 1 and 120000 milliseconds.'}
            raw_params = args.get('params')
            payload = {'method': method, 'params': {} if raw_params is None else raw_params}
            error = await authorize_rpc(config, profile_id, device_id, method, payload['params'])
            if error:
                error_code = (
                    'invalid_params' if 'Invalid parameters' in error
                    else 'device_not_found' if 'not found' in error.lower()
                    else 'unsupported_method'
                )
                return {'success': False, 'confirmed': False, 'delivery': 'failed',
                        'error_code': error_code, 'error': error}
            if mode == 'twoway':
                payload['timeout'] = timeout_ms
            try:
                response = await client.post(host + f'/api/rpc/{mode}/{device_id}', headers=headers,
                                             json=payload, timeout=timeout_ms / 1000 + 5)
            except httpx.TimeoutException:
                return {'success': False, 'status': 504, 'confirmed': False, 'delivery': 'failed',
                        'error_code': 'timeout',
                        'error': f'RPC timeout: Device did not respond within {timeout_ms}ms.'}
        else:
            return {'success': False, 'error': 'Unknown tool.'}

        if response.status_code == 504 and name == 'thingsboard_rpc':
            return {'success': False, 'status': 504, 'confirmed': False, 'delivery': 'failed',
                    'error_code': 'timeout',
                    'error': f'RPC timeout: Device did not respond within {timeout_ms}ms.'}
        if response.status_code == 404 and name == 'thingsboard_rpc':
            return {'success': False, 'status': 404, 'confirmed': False, 'delivery': 'failed',
                    'error_code': 'device_not_found', 'error': 'Device not found in ThingsBoard.'}
        if not 200 <= response.status_code < 300:
            error_result = {'success': False, 'status': response.status_code, 'error': 'ThingsBoard request failed.'}
            if name == 'thingsboard_rpc':
                error_result.update({'confirmed': False, 'delivery': 'failed', 'error_code': 'rpc_failed'})
            return error_result
        try:
            data = response.json()
        except ValueError:
            data = response.text
        if name == 'thingsboard_rpc':
            data = redact_credentials(data, key)
            if mode == 'twoway' and isinstance(data, dict) and data.get('error'):
                err_str = str(data['error'])
                err_lower = err_str.lower()
                code = ('device_offline' if ('offline' in err_lower or 'disconnected' in err_lower)
                        else 'timeout' if 'timed out' in err_lower else 'device_error')
                return {'success': False, 'confirmed': False, 'delivery': 'failed',
                        'error_code': code, 'error': f'Device RPC failed: {err_str}', 'data': data}
            confirmed = bool(mode == 'twoway' and response.status_code != 204 and data not in (None, ''))
            delivery = 'device_response' if confirmed else 'submitted'
            return {'success': True, 'confirmed': confirmed, 'delivery': delivery, 'data': data, 'response': data}
        return {'success': True, 'data': redact_credentials(data, key)}
    except Exception:
        return {'success': False, 'error': 'Could not contact ThingsBoard.'}


MCP_TOOLS = [
    {
        'type': 'function',
        'function': {
            'name': 'list_devices',
            'description': 'List all IoT devices, sensors, and actuators connected to ThingsBoard.',
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'discover_capabilities',
            'description': 'Refresh and inspect the ThingsBoard RPC capability registry for all accessible devices (read-only).',
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'list_available_rpc',
            'description': 'List discovered RPC methods and parameter schemas for a specific ThingsBoard device.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'device_identifier': {'type': 'string', 'description': 'Exact ThingsBoard device name or UUID.'},
                },
                'required': ['device_identifier'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_platform_summary',
            'description': 'Summarize accessible ThingsBoard devices and their registered RPC actions.',
            'parameters': {'type': 'object', 'properties': {}},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_telemetry',
            'description': 'Query latest telemetry (temperature, humidity, POWER state, etc.) for a ThingsBoard device.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'device_name': {'type': 'string', 'description': 'Exact name or UUID of the target ThingsBoard device.'},
                    'keys': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Optional telemetry keys to fetch (e.g. ["temperature", "humidity", "POWER"]).'},
                },
                'required': ['device_name'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'execute_device_action',
            'description': 'Validate and execute a registered RPC action on a ThingsBoard device through the capability registry (two-way confirmation by default). Prefer exact device names over guessing UUIDs.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'device_identifier': {'type': 'string', 'description': 'Exact target device name (preferred) or verified UUID from list_devices.'},
                    'method': {'type': 'string', 'description': 'Registered RPC method name from list_available_rpc.'},
                    'params': {'description': 'JSON parameters matching the discovered parameter schema.'},
                    'two_way': {'type': 'boolean', 'description': 'Wait for confirmed device response (default true).'},
                    'timeout_ms': {'type': 'integer', 'description': 'Timeout in milliseconds (default 5000).'},
                },
                'required': ['device_identifier', 'method'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'send_rpc',
            'description': 'Send a capability-validated RPC command to a ThingsBoard device.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'device_name': {'type': 'string', 'description': 'Name or UUID of the target device'},
                    'method': {'type': 'string', 'description': 'Registered RPC method name'},
                    'params': {'description': 'Command parameters as JSON object/primitive or JSON string'},
                    'two_way': {'type': 'boolean', 'description': 'Wait for device confirmation (default true)'},
                    'timeout_ms': {'type': 'integer', 'description': 'Timeout in milliseconds (default 5000)'},
                },
                'required': ['device_name', 'method'],
            },
        },
    },
]

TOOLS = [
    {
        'type': 'function',
        'function': {
            'name': 'thingsboard_get',
            'description': 'Read data from the configured ThingsBoard REST API. Use the API key permissions. Examples: /api/tenant/devices?pageSize=100&page=0 to find device IDs, /api/plugins/telemetry/DEVICE/{deviceId}/values/timeseries for latest telemetry, and /api/plugins/telemetry/DEVICE/{deviceId}/values/attributes for attributes. Follow pagination when hasNext is true.',
            'parameters': {'type': 'object', 'properties': {'path': {'type': 'string', 'description': 'A relative ThingsBoard /api/ path including any query string.'}}, 'required': ['path']},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'thingsboard_query',
            'description': 'Search ThingsBoard entities or alarms using a read-only query. Supported paths: /api/entitiesQuery/find, /api/entitiesQuery/count, /api/alarmsQuery/find, /api/alarmsQuery/count, /api/v2/entitiesQuery/find/keys.',
            'parameters': {'type': 'object', 'properties': {'path': {'type': 'string'}, 'body': {'type': 'object', 'description': 'ThingsBoard entity or alarm query object.'}}, 'required': ['path', 'body']},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'thingsboard_rpc',
            'description': 'Send a registered RPC method to a ThingsBoard device after capability and parameter validation. Use one-way RPC when the device does not send a reply.',
            'parameters': {'type': 'object', 'properties': {'device_id': {'type': 'string', 'description': 'The exact ThingsBoard device UUID.'}, 'method': {'type': 'string'}, 'params': {'description': 'Any JSON RPC parameters.'}, 'two_way': {'type': 'boolean', 'description': 'Wait for the device response when true.'}, 'timeout_ms': {'type': 'integer', 'description': 'Timeout in milliseconds for a two-way RPC (default 5000, maximum 120000).'}}, 'required': ['device_id', 'method']},
        },
    },
]
