# ThingsBoard MCP Server for XiaoZhi AI Platform

A minimal, modular **Model Context Protocol (MCP)** server enabling AI agents to monitor and control IoT devices via the **ThingsBoard REST API**.

---

## 1. Architecture & Design Principles

- **Independent Module**: Decoupled from the frontend console and the XiaoZhi voice runtime. Can be embedded or started as a standalone stdio/SSE server.
- **Dynamic Credential Resolution**: Never hardcodes API keys, tokens, or device IDs. Automatically resolves connection credentials from the active **Agent Profile** (`integrations.thingsboard`) or environment variables.
- **ThingsBoard REST API**: Interacts with ThingsBoard Community Edition (CE) endpoints for device inventory, timeseries telemetry, and server-side two-way / one-way RPC.
- **Structured LLM Output**: All tools return concise, machine-readable JSON with clear error handling for missing devices, network failures, and RPC timeouts.
- **Extensible**: Structured into modular tool handlers under `src/tools/` to allow seamless addition of attributes, historical analytics, and alarm management later.

```
┌─────────────────────────────────┐
│       AI Agent / LLM Client     │
│   (XiaoZhi / Gateway / Claude)  │
└────────────────┬────────────────┘
                 │ stdio / SSE (JSON-RPC)
                 ▼
┌─────────────────────────────────┐
│     ThingsBoard MCP Server      │
│  ┌───────────┐   ┌────────────┐ │
│  │list_device│   │get_telemetr│ │
│  └───────────┘   └────────────┘ │
│  ┌───────────┐   ┌────────────┐ │
│  │ send_rpc  │   │   Config   │ │
│  └───────────┘   └────────────┘ │
└────────────────┬────────────────┘
                 │ REST API (X-Authorization: ApiKey / Bearer)
                 ▼
┌─────────────────────────────────┐
│       ThingsBoard CE (8080)     │
└─────────────────────────────────┘
```

---

## 2. Configuration & Agent Profile Integration

The server dynamically resolves ThingsBoard settings using the following lookup order:

1. Active Agent Profile JSON (`--profile <path>` or environment variable `AGENT_PROFILE_PATH`)
2. Default `./agent_profile.json` in the current working directory
3. Environment variables: `TB_HOST` and `TB_API_KEY` (or `TB_USERNAME` / `TB_PASSWORD`)

### Agent Profile Format (`agent_profile.json`)

```json
{
  "id": "agent_smart_home",
  "name": "Smart Home Assistant",
  "role": "IoT Supervisor",
  "integrations": {
    "thingsboard": {
      "host": "http://localhost:8080",
      "api_key": "tb_963y36TYm3j5OwJjAbPiZIifTCHTMB0WBZVstE9DVa9pjN4dB-jK_7gfTAQtm_PczbuaCkqq-e-AuwXNW-kIyQ",
      "timeout_seconds": 10
    }
  }
}
```

*Alternatively, username and password can be specified instead of `api_key` for JWT-based tenant login.*

---

## 3. Tool Reference

### 1. `list_devices`
Retrieves devices accessible to the authenticated tenant.

- **Parameters:**
  - `page_size` *(int, default: 50, max: 100)*: Number of devices to return.
  - `page` *(int, default: 0)*: Zero-based page offset.
  - `device_type` *(string, optional)*: Filter by device type (e.g. `'default'`, `'environmental-sensor'`).
- **Example Response:**
  ```json
  {
    "total_devices": 1,
    "page": 0,
    "has_next": false,
    "devices": [
      {
        "id": "0db31590-da5d-11f1-9c26-21abd05992f6",
        "name": "Virtual-Environmental-Monitor",
        "type": "environmental-sensor",
        "label": "Virtual Office Environmental Monitor",
        "created_time": "2026-11-07T03:41:02.185000+00:00",
        "is_gateway": false
      }
    ]
  }
  ```

### 2. `get_telemetry`
Fetches the latest telemetry readings for a device. Supports both device UUIDs and device names.

- **Parameters:**
  - `device_identifier` *(string, required)*: Device display name (e.g. `'Virtual-Environmental-Monitor'`) or UUID.
  - `keys` *(array of strings, optional)*: Specific metrics to fetch (e.g. `["temperature", "humidity"]`). If omitted, all available metrics are returned.
- **Example Response:**
  ```json
  {
    "device_id": "0db31590-da5d-11f1-9c26-21abd05992f6",
    "device_name": "Virtual-Environmental-Monitor",
    "telemetry_keys": ["temperature", "humidity"],
    "telemetry": {
      "temperature": {
        "value": 25.35,
        "timestamp": "2026-11-07T03:41:06.406000+00:00",
        "epoch_ms": 1794022866406
      },
      "humidity": {
        "value": 56.8,
        "timestamp": "2026-11-07T03:41:06.406000+00:00",
        "epoch_ms": 1794022866406
      }
    }
  }
  ```

### 3. `send_rpc`
Sends a server-side Remote Procedure Call (RPC) to control an edge device (e.g., toggling GPIOs, rebooting, or changing operating parameters).

- **Parameters:**
  - `device_identifier` *(string, required)*: Device display name or UUID.
  - `method` *(string, required)*: RPC method name (e.g. `'setGpio'`, `'setValue'`).
  - `params` *(any, optional)*: Arguments for the RPC method (dict, list, or primitive).
  - `timeout_ms` *(int, default: 5000)*: Execution timeout in milliseconds.
  - `two_way` *(bool, default: true)*: `true` for synchronous two-way RPC, `false` for one-way RPC.
- **Example Response (Success):**
  ```json
  {
    "success": true,
    "device_id": "0db31590-da5d-11f1-9c26-21abd05992f6",
    "device_name": "Virtual-Environmental-Monitor",
    "method": "setGpio",
    "response": {"status": "ok", "pin": 2, "state": 1},
    "error": null
  }
  ```
- **Example Response (Timeout / Device Offline):**
  ```json
  {
    "success": false,
    "device_id": "0db31590-da5d-11f1-9c26-21abd05992f6",
    "device_name": "Virtual-Environmental-Monitor",
    "method": "getGpioStatus",
    "response": null,
    "error": "RPC timeout: Device 'Virtual-Environmental-Monitor' did not respond within 2000ms."
  }
  ```

---

## 4. Running the MCP Server

### Option A: Via Local Docker Container (Recommended)
Reuse the installed local Docker image (`iot_assignment-tools:latest`):

```bash
# Run over stdio transport
docker run -i --rm --network host \
  -v $(pwd):/app -w /app \
  iot_assignment-tools:latest \
  python -m src.server --profile agent_profile.example.json

# Run as SSE network service on port 8009
docker compose up -d
```

### Option B: Local Python Environment
```bash
pip install -r requirements.txt

# Start with stdio transport
python -m src.server --profile agent_profile.example.json

# Or start with SSE transport
python -m src.server --profile agent_profile.example.json --transport sse --port 8009
```

---

## 5. Testing & Verification

### 1. Run Unit & Mocked Protocol Tests
Runs 24 unit and protocol tests covering configuration resolution, API mocking, and stdio IPC lifecycle:

```bash
docker run --rm -v $(pwd):/app -w /app iot_assignment-tools:latest \
  python -m unittest discover -s tests -p "test_*.py" -v
```

### 2. Run Live End-to-End Test Against ThingsBoard
Connects an MCP client session over stdio, performs tool discovery, and calls all three tools against the running ThingsBoard instance:

```bash
docker run --rm --network host -v $(pwd):/app -w /app iot_assignment-tools:latest \
  python tests/test_live.py agent_profile.example.json
```
