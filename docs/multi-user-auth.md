# Multi-user console and device setup

The console uses administrator-created accounts. Each account starts without agents or devices. Existing JSON profiles and device records are retained but are not assigned to a user. Legacy device credentials are rejected; re-enroll each device under its owner's account. An old SQLite device record is copied to `legacy_device_archive` before that MAC address is re-enrolled.

## Deployment

1. Back up the `iot_platform_data` Docker volume (`PLATFORM_DATA_VOLUME`, or legacy `deploy/platform-data/` before migrating) before upgrading. The bridge stores accounts and owned agents in `accounts.db`, and device enrollment in `devices.db`, under `PLATFORM_DATA_DIR` (the deployment mounts `iot_platform_data` at `/app/data`). Keep this volume private and back it up together.
2. Generate a long, random `BRIDGE_SECRET` and set it in your untracked deployment environment. The deployment passes the same secret to the XiaoZhi server through its environment. Do not commit the value. Changing the secret invalidates outstanding enrollment challenges.
3. Configure `PUBLIC_OTA_URL` and `PUBLIC_WS_URL` to the bridge's externally reachable OTA and WebSocket URLs. For deployments outside a trusted local test network, put the bridge behind TLS and use `https://.../xiaozhi/ota/` and `wss://.../xiaozhi/v1/`; credentials and device enrollment proofs must not travel over plaintext networks. Point each device's configured OTA URL at the bridge, not the upstream XiaoZhi server.
4. Start the core services and deployment stack using the commands in the repository README. The deployment no longer publishes upstream WebSocket port 8002 or the shared ThingsBoard MCP port 8009, and the core stack no longer publishes its shared gateway ports 8008 and 8080. Do not expose those services through another route: devices must connect through the authenticated bridge WebSocket. Stop any previously deployed `thingsboard-mcp` container; removing it from the Compose file does not stop an already-running container.
5. Rotate any ThingsBoard keys and CoreIoT device tokens previously committed to the repository. Set `THINGSBOARD_ALLOWED_ORIGINS` to a comma-separated list of approved ThingsBoard origins (scheme, hostname, and optional port, with no path or query), and configure a new key on the appropriate agent in the console. Only administrators should choose the allowed origins; include the LAN origin explicitly when needed. Shared dashboard and MCP integrations are disabled; console chat and telemetry use the selected agent's ThingsBoard settings.

## Accounts

Set `CONSOLE_USERNAME` and `CONSOLE_PASSWORD` (12+ characters) in `.env` to auto-bootstrap the initial account and starter ThingsBoard agent at bridge startup. Create additional accounts from the server terminal (the command prompts for the password without putting it in shell history):

```sh
docker compose -f docker-compose.deploy.yml exec platform-bridge python -m platform-bridge.accounts create alice
```

To reset a password and revoke all existing sessions:

```sh
docker compose -f docker-compose.deploy.yml exec platform-bridge python -m platform-bridge.accounts reset-password alice
```

Passwords must be 12–1024 characters. Sessions expire after 12 hours and can be revoked by signing out. Login attempts are limited per source address; configure a trusted proxy so distinct clients reach the bridge with distinct source addresses if per-client rate limiting is required.

## Re-enroll devices

Build and flash the updated firmware for the affected board. Set its OTA URL to `PUBLIC_OTA_URL`, connect it to Wi-Fi, and enter the six-digit code shown or spoken by the device in the signed-in owner's console. The device retains an enrollment secret and receives its device token only after the code is bound. Device tokens are separate from console sessions and the internal bridge secret. An active WebSocket stops forwarding within one second after a device is revoked. To move a currently owned device to another account, unbind it from its current account first and enroll it again.

The legacy browser device tester is unavailable in this multi-user configuration. The hardware and upstream runtime must be able to reach the configured bridge URLs. Agent-specific device chat and ThingsBoard access are routed through the bridge; MAC addresses alone do not authorize a WebSocket connection.

## Verification

The provisioning smoke test at `tests/test_alpha02_provisioning.py` targets a running **test** bridge and requires two existing test accounts. Set `PLATFORM_TEST_USER_A`, `PLATFORM_TEST_PASSWORD_A`, `PLATFORM_TEST_USER_B`, and `PLATFORM_TEST_PASSWORD_B`; optionally set `PLATFORM_TEST_BRIDGE_URL` (default `http://localhost:8005`). It creates a temporary agent and device and revokes them afterward, so do not use production accounts or a production data directory. The older Alpha console, virtual-PC, and Phase 1B integration scripts assume shared, unauthenticated profiles and are not compatible with this multi-user configuration.

For a standalone Python installation, the bridge also needs the `websockets` package version 14 or newer; the deployment bridge image includes it.
