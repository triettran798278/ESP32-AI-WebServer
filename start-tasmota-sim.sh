#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

TB_HOST="${TB_HOST:-${THINGSBOARD_HOST:-}}"
: "${TB_HOST:?Set TB_HOST or THINGSBOARD_HOST in the environment}"
TB_API_KEY="${TB_API_KEY:?Set TB_API_KEY in the environment}"
MQTT_HOST="${MQTT_HOST:?Set MQTT_HOST in the environment}"
MQTT_PORT="${MQTT_PORT:-1883}"
TASMOTA_FULL_TOPIC="${TASMOTA_FULL_TOPIC:-%prefix%/%topic%/}"
TB_DOWNLINK_CONVERTER_ID="${TB_DOWNLINK_CONVERTER_ID:?Set TB_DOWNLINK_CONVERTER_ID in the environment}"
SIM_IMAGE="${SIM_IMAGE:-iot-tasmota-sim:local}"
SIM_DEVICE_A="${SIM_DEVICE_A:-Simulated Tasmota A}"
SIM_DEVICE_B="${SIM_DEVICE_B:-Simulated Tasmota B}"

# Build and start two virtual Tasmota relays.
docker build -f tools/tasmota-simulator.Dockerfile -t "$SIM_IMAGE" tools

docker rm -f tasmota-a tasmota-b >/dev/null 2>&1 || true

docker run -d --name tasmota-a --restart unless-stopped \
  -e MQTT_HOST="$MQTT_HOST" \
  -e MQTT_PORT="$MQTT_PORT" \
  -e TASMOTA_TOPIC="$SIM_DEVICE_A" \
  -e TASMOTA_FULL_TOPIC="$TASMOTA_FULL_TOPIC" \
  "$SIM_IMAGE"

docker run -d --name tasmota-b --restart unless-stopped \
  -e MQTT_HOST="$MQTT_HOST" \
  -e MQTT_PORT="$MQTT_PORT" \
  -e TASMOTA_TOPIC="$SIM_DEVICE_B" \
  -e TASMOTA_FULL_TOPIC="$TASMOTA_FULL_TOPIC" \
  "$SIM_IMAGE"

# Sync downlink converter and register SERVER_SCOPE rpcCapabilities on ThingsBoard
TB_HOST="$TB_HOST" TB_API_KEY="$TB_API_KEY" TB_DOWNLINK_CONVERTER_ID="$TB_DOWNLINK_CONVERTER_ID" SIM_DEVICE_A="$SIM_DEVICE_A" SIM_DEVICE_B="$SIM_DEVICE_B" python3 - <<'PY'
import json, os, time, urllib.error, urllib.parse, urllib.request

host = os.environ["TB_HOST"].rstrip("/")
api_key = os.environ["TB_API_KEY"]
dev_a = os.environ["SIM_DEVICE_A"]
dev_b = os.environ["SIM_DEVICE_B"]
downlink_id = os.environ["TB_DOWNLINK_CONVERTER_ID"]

def req(method, path, data=None):
    headers = {
        "Content-Type": "application/json",
        "X-Authorization": f"ApiKey {api_key}",
        "User-Agent": "XiaoZhi-Tasmota-Setup/1.0",
    }
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(host + path, data=body, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=15) as resp:
        text = resp.read().decode()
        return json.loads(text) if text else None

encoder_script = """var tasmotaTopic = metadata['cs_tasmotaTopic'] || metadata['ss_tasmotaTopic'] || metadata['deviceName'];
var cmndName = null;
var cmndPayload = null;

function toTasmotaPower(val) {
    if (val === true || val === 1 || val === '1' || val === 'ON' || val === 'on' || val === 'true') return 'ON';
    if (val === false || val === 0 || val === '0' || val === 'OFF' || val === 'off' || val === 'false') return 'OFF';
    if (val === 'TOGGLE' || val === 'toggle') return 'TOGGLE';
    return String(val);
}

if (msgType === 'RPC_CALL_FROM_SERVER_TO_DEVICE') {
    var method = (msg.method || '').trim();
    var params = msg.params;
    if (typeof params === 'string') {
        try {
            params = JSON.parse(params);
        } catch (e) {}
    }
    var mLower = method.toLowerCase();
    if (mLower === 'setvalue' || mLower === 'setpower' || mLower === 'power') {
        cmndName = 'POWER';
        var pv = (params && typeof params === 'object') ? (params.state !== undefined ? params.state : params.value) : params;
        cmndPayload = toTasmotaPower(pv);
    } else if (mLower === 'getvalue' || mLower === 'getpower') {
        cmndName = 'POWER';
        cmndPayload = '';
    } else if (mLower === 'togglepower' || mLower === 'toggle') {
        cmndName = 'POWER';
        cmndPayload = 'TOGGLE';
    } else if (mLower === 'setgpio') {
        cmndName = 'POWER';
        var v = (params && typeof params === 'object') ? (params.value !== undefined ? params.value : params.state) : params;
        cmndPayload = toTasmotaPower(v);
    } else if (mLower === 'cmnd' && params && typeof params === 'object' && params.command) {
        cmndName = String(params.command);
        cmndPayload = params.value !== undefined ? String(params.value) : '';
    } else if (method) {
        cmndName = method;
        cmndPayload = (params === null || params === undefined) ? '' : (typeof params === 'object' ? JSON.stringify(params) : String(params));
    }
} else if (msgType === 'ATTRIBUTES_UPDATED' || msgType === 'POST_ATTRIBUTES_REQUEST') {
    if (msg.POWER !== undefined) {
        cmndName = 'POWER';
        cmndPayload = toTasmotaPower(msg.POWER);
    } else if (msg.power !== undefined) {
        cmndName = 'POWER';
        cmndPayload = toTasmotaPower(msg.power);
    }
}

if (!cmndName) {
    return null;
}

return {
    contentType: 'TEXT',
    data: cmndPayload,
    metadata: {
        topic: 'tbch_8x4k/cmnd/' + tasmotaTopic + '/' + cmndName
    }
};"""

try:
    conv = req("GET", f"/api/converter/{downlink_id}")
    if conv["configuration"].get("encoder") != encoder_script:
        conv["configuration"]["encoder"] = encoder_script
        req("POST", "/api/converter", conv)
        print("Updated Tasmota MQTT Downlink converter.")
except urllib.error.HTTPError as exc:
    print(f"Warning: could not update converter {downlink_id}: HTTP {exc.code}")

set_power = {
    "description": "Turn relay power on or off",
    "params": {
        "type": "object",
        "properties": {"state": {"type": "boolean"}},
        "required": ["state"],
        "additionalProperties": False,
    },
}
get_power = {
    "description": "Query current relay power state",
    "params": {"type": "object", "properties": {}, "additionalProperties": False},
}
toggle_power = {
    "description": "Toggle relay power state",
    "params": {"type": "object", "properties": {}, "additionalProperties": False},
}

caps_full = {"methods": {"setPower": set_power, "getPower": get_power, "togglePower": toggle_power}}
caps_basic = {"methods": {"setPower": set_power, "getPower": get_power}}

def ensure_device(name):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            return req("GET", f"/api/tenant/devices?deviceName={urllib.parse.quote(name)}")
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            time.sleep(1)
    dev = req("POST", "/api/device", {"name": name, "type": "default"})
    req("POST", f"/api/plugins/telemetry/DEVICE/{dev['id']['id']}/attributes/CLIENT_SCOPE", {"tasmotaTopic": name})
    return dev

for name, caps in [(dev_a, caps_full), (dev_b, caps_basic)]:
    dev = ensure_device(name)
    dev_id = dev["id"]["id"]
    req("POST", f"/api/plugins/telemetry/DEVICE/{dev_id}/attributes/SERVER_SCOPE", {"rpcCapabilities": caps})
    print(f"Registered rpcCapabilities on {name} ({dev_id})")

try:
    s1 = req("GET", "/api/tenant/devices?deviceName=sensor1")
    req("POST", f"/api/plugins/telemetry/DEVICE/{s1['id']['id']}/attributes/SERVER_SCOPE", {"rpcCapabilities": caps_full})
    print(f"Registered rpcCapabilities on sensor1 ({s1['id']['id']})")
except urllib.error.HTTPError as exc:
    if exc.code != 404:
        raise
PY

docker ps --filter "name=^tasmota-[ab]$"
echo "Simulated Tasmota devices running via $MQTT_HOST:$MQTT_PORT ($TASMOTA_FULL_TOPIC) -> $TB_HOST"
