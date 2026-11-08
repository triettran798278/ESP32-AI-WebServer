# Alpha 0.2 — ESP32 Firmware Integration & Device Provisioning Specification

## Problem Statement

Currently, adding hardware nodes to the platform requires manual MAC address entry in the administration console. There is no automated, cryptographically secure mechanism for physical ESP32 devices to discover, authenticate, and register themselves with the platform or bind to a specific AI Agent Profile upon boot. Furthermore, MAC addresses are transmitted in the clear and treated as implicit identities rather than authenticated credentials, presenting spoofing vulnerabilities and poor developer/user experience.

## Solution

A native device provisioning and activation subsystem mirroring the XiaoZhi hardware onboarding workflow:
1. Console generates a cryptographically random, single-use, 6-digit numeric activation code bound to a selected Agent Profile with a 5-minute expiration.
2. The user powers on an ESP32 device connected to Wi-Fi.
3. The device redeems the 6-digit code with the platform backend over HTTP/HTTPS.
4. The platform verifies the code, creates an authenticated device record, binds the device to the Agent Profile, and returns a high-entropy device token (stored hashed on the server).
5. The device persists its credentials in local NVS and begins sending periodic heartbeats.
6. The web console detects successful activation in real-time and displays the active device.
7. Legacy manual MAC address binding is retained for development and administrative flexibility.

## User Stories

1. As a platform user, I want to click "Add Device" and select an Agent Profile, so that my new hardware is immediately configured with the right AI persona and tools.
2. As a platform user, I want to see a clear 6-digit activation code and countdown timer, so that I know exactly what code to submit and how long it remains valid.
3. As a platform user, I want the web interface to automatically detect when the ESP32 redeems the code, so that I don't have to manually refresh the page.
4. As an IoT administrator, I want to continue registering devices manually using their MAC addresses, so that virtual testing nodes and administrative overrides still work seamlessly.
5. As a physical ESP32 device, I want to submit an activation code upon initial Wi-Fi connection, so that I can automatically acquire my platform identity and agent assignment.
6. As a physical ESP32 device, I want to receive and store an authentication token in non-volatile storage, so that I do not need to re-register on every reboot.
7. As a physical ESP32 device, I want to retrieve my runtime configuration (including WebSocket URI and active Agent settings) without exposing ThingsBoard master credentials, so that communication remains secure.
8. As a physical ESP32 device, I want to send periodic heartbeats to the platform, so that my online/offline status and last seen timestamp remain accurate in the console.
9. As a platform operator, I want activation codes to expire after 5 minutes and be strictly single-use, so that eavesdropped or brute-forced codes cannot be re-used.
10. As a platform operator, I want device authentication tokens to be hashed at rest using SHA-256, so that a database breach does not compromise active device fleet credentials.
11. As a platform operator, I want to be able to revoke a device credential or unbind a device immediately, so that rogue or retired hardware can no longer authenticate.
12. As a platform operator, I want rate limiting on registration attempts, so that malicious actors cannot brute force 6-digit codes.
13. As a platform operator, I want registered devices to be clearly distinguishable from legacy MAC-bound devices in the inventory table, so that security posture is transparent.

## Implementation Decisions

### Modules & Storage Architecture
- **Persistent Device Database**: Introduce SQLite database (`devices.db`) managed via Python standard library `sqlite3` inside the mounted platform data volume. This provides persistent, ACID-compliant storage for device identities, hashed authentication credentials, activation codes, and heartbeat records.
- **Backend API (`platform-bridge`)**:
  - `POST /api/devices/activation`: Generates cryptographically secure 6-digit code (`secrets.randbelow(1000000)`), binds it to an `agent_id`, stores hash & expiry (300s), and returns code and expiration.
  - `GET /api/devices/activation/status`: Polling endpoint returning activation status (`pending`, `activated`, `expired`) and device metadata upon completion.
  - `POST /api/devices/register`: Redeems activation code, generates UUID-based `device_id` and 256-bit cryptographically secure `device_token`, hashes token with SHA-256 for persistent storage, associates device to agent profile, and returns credentials and runtime endpoints.
  - `GET /api/devices/me`: Bearer-authenticated endpoint returning device profile and registration details.
  - `GET /api/devices/me/config`: Bearer-authenticated endpoint delivering runtime WebSocket and OTA configuration, strictly omitting external service API keys.
  - `POST /api/devices/heartbeat`: Bearer-authenticated endpoint updating device `last_seen` timestamp and marking device `online`.
  - `POST /api/devices/me/unbind`: Authenticated endpoint allowing a device to revoke its own credentials and unbind.
  - `POST /api/devices/unbind`: Management endpoint for administrator to revoke device credentials and unbind by MAC address or device ID.
  - Extended `GET /api/devices`: Returns unified inventory merging authenticated database devices with legacy JSON bindings.

### Device State Machine
The firmware provisioning module adheres to the explicit lifecycle:
`BOOT → WIFI_PROVISIONING → CONNECTING → UNREGISTERED → REGISTERING → REGISTERED → ONLINE`

State transitions:
- Missing Wi-Fi credentials -> `WIFI_PROVISIONING`.
- Wi-Fi connected but no token in NVS -> `UNREGISTERED`.
- Activation code provided -> `REGISTERING` -> `POST /api/devices/register`.
- On success: store token in NVS namespace `platform` -> `REGISTERED`.
- Fetch runtime config & start background heartbeat -> `ONLINE`.
- On 401 Unauthorized or unbind signal: clear NVS credentials -> transition to `UNREGISTERED`.

## Testing Decisions

- Tests must exercise external HTTP contracts and WebSocket behavior without mocking internal business logic.
- Automated test harness `tests/test_alpha02_provisioning.py` must test:
  1. Cryptographic 6-digit code generation and formatting (leading zeros preserved).
  2. Expiration enforcement after TTL window.
  3. Invalid code rejection with HTTP 400.
  4. Single-use enforcement (duplicate redemption attempt rejected).
  5. Successful end-to-end device registration and token issuance.
  6. Verified device-to-agent profile association.
  7. Token authentication for `/api/devices/me` and `/api/devices/me/config`.
  8. Security check: ThingsBoard API key absence from device configuration response.
  9. Heartbeat processing and `last_seen` timestamp tracking.
  10. Credential revocation upon unbinding (subsequent token requests return 401).
  11. Rate limiting on repeated invalid registration attempts.
  12. Non-regression of Alpha 0.1 (`test_alpha_console_integration.py`) and Phase 1B (`test_phase1b_dual_device.py`).

## Out of Scope

- Changes to XiaoZhi audio codec or hardware sound processing pipelines.
- Replacement of ThingsBoard MCP gateway.
- Redesigning the core React UI component hierarchy or CSS framework.
- Hardware redesign or pinout changes to the connected ESP32 YOLO UNO board.

## Further Notes

- The system maintains 100% backward compatibility with legacy MAC bindings and tests.
- Physical firmware implementation is modularly integrated into `firmware/main`, preserving wake-word, audio, and display components.
