# Reproduce the local deployment

The deployment builds the bridge and XiaoZhi server from the source in this
repository. The XiaoZhi source under `deploy/xiaozhi-runtime` was recovered from
the previous `iot-xiaozhi-baseline:local` image; its license is in that directory.
The Python dependency locks record the versions installed in the previous images.
The faster-whisper VAD model is included from the upstream v1.2.1 release.
Building requires internet access to Docker Hub, PyPI and the PyTorch CPU index.

## Prerequisites

- Linux x86-64, Docker Engine and Docker Compose, enough disk space for the
  images and models. The default core Compose file requests an NVIDIA GPU and
  NVIDIA Container Toolkit; use the CPU override below if they are unavailable.
- A LAN address reachable by the ESP32. Access to ThingsBoard at `https://codehelpers.tech`.
- The speech and language models must be downloaded on the new machine. Device
  records, console accounts and Ollama's volume are stored outside Git.

## First start

1. Clone this repository and enter its directory. Copy `.env.example` to `.env`,
   then edit `.env` for this machine. Set `HOST_IP` to the LAN address reachable
   by the ESP32, and set independent random values for `BRIDGE_SECRET` and
   `API_KEY` (generate each with `openssl rand -hex 32`). Set `THINGSBOARD_HOST` and
   `THINGSBOARD_ALLOWED_ORIGINS` to `https://codehelpers.tech`.
   Configure `CONSOLE_USERNAME` (e.g. `admin`) and `CONSOLE_PASSWORD`
   (at least 12 characters) in `.env` so `platform-bridge` automatically
   creates the initial console account and a starter ThingsBoard agent on
   startup. Configure a ThingsBoard API key in the console or set
   `THINGSBOARD_API_KEY` in `.env` for the starter agent and separate native
   dashboard.

   ```sh
   test -e .env || cp .env.example .env
   chmod 600 .env
   ```

   On an existing installation, retain its current `BRIDGE_SECRET` when moving
   settings into `.env`; do not generate a replacement unnecessarily.
   Docker Compose reads `.env` automatically. Keep it private and never commit it;
   the same bridge secret is passed to the XiaoZhi server automatically.
   To run Python scripts directly, export their settings first with
   `set -a; . ./.env; set +a`. Existing agent profiles retain their saved
   ThingsBoard addresses; update those profiles when moving data to a new host.
   For the standalone Tasmota simulator, also set `TB_HOST`, `TB_API_KEY`,
   `MQTT_HOST` and `TB_DOWNLINK_CONVERTER_ID` before running it.

2. Start the AI stack with the fixed project name so it creates the network used
   by the deployment, then install the models:

   ```sh
   docker compose -p iot_assignment up -d --build
   ./scripts/init_models.sh
   ```

   For CPU-only Ollama, replace the first command with:

   ```sh
   docker compose -p iot_assignment -f docker-compose.yml -f docker-compose.cpu.yml up -d --build
   ```

   CPU inference will be slower.

3. Start the bridge and XiaoZhi server:

   ```sh
   docker compose -f docker-compose.deploy.yml up -d --build
   docker compose -f docker-compose.deploy.yml ps
   ```

   If `CONSOLE_USERNAME` and `CONSOLE_PASSWORD` (12+ characters) are set in
   `.env`, `platform-bridge` creates that account and a starter ThingsBoard
   agent automatically on startup (without overwriting an existing account or
   its agents). To add extra console accounts manually (prompts for password):

   ```sh
   docker compose -f docker-compose.deploy.yml exec platform-bridge python -m platform-bridge.accounts create alice
   ```

   See [multi-user setup](multi-user-auth.md) for additional accounts and
   password resets.

   Open `http://<HOST_IP>:8005` for the console. The OTA URL for devices is
   `http://<HOST_IP>:8005/xiaozhi/ota/`. The address must be reachable from the
   device, not `localhost`. Set `PUBLIC_WS_URL` and `PUBLIC_OTA_URL` in
   `.env` if a proxy or different external port is used.

4. Check service logs and test the device flow:

   ```sh
   docker compose -f docker-compose.deploy.yml logs --tail=100 platform-bridge xiaozhi-server
   ```

   For the multi-user provisioning smoke test, create two test accounts and set
   the four `PLATFORM_TEST_USER_*` and `PLATFORM_TEST_PASSWORD_*` variables
   described in `tests/test_alpha02_provisioning.py`, then run that script. It
   creates and deletes test records; use a test deployment.
   Verify audio and ThingsBoard control with the actual device and service.

   The YOLO UNO firmware has a machine-specific OTA fallback: configure and
   build the firmware with ESP-IDF for the target host, then verify on hardware.
   The firmware cannot read the host's `.env` at runtime.

## Native ThingsBoard dashboards

The ThingsBoard IoT page includes a native device view separate from the
multi-user console login. Configure `CONSOLE_USERNAME` and a strong
`CONSOLE_PASSWORD` in `.env` (passed into `platform-bridge` by
`docker-compose.deploy.yml`), then restart `platform-bridge`. Do not commit
credentials. Native dashboard sessions expire after eight hours and are cleared
when the bridge restarts.

The native dashboard uses `THINGSBOARD_HOST` and `THINGSBOARD_API_KEY` from
`.env`; saved `agent_101` credentials apply when configured for the same host.
Device telemetry and server attributes refresh every 15 seconds. Thermostat
alarm flags and thresholds can be updated from the console and are saved to
ThingsBoard. The dashboard list is read from ThingsBoard; other
dashboard-specific widgets are not yet reproduced. Use HTTPS or a trusted local
network because the native dashboard password is sent to the bridge at sign-in.

## State, data, and backups

- **Compose state**: `platform-bridge` stores `accounts.db`, `devices.db`,
  `capabilities.sqlite3`, and `agents.json` in the persistent Docker named
  volume `iot_platform_data` (override via `PLATFORM_DATA_VOLUME`, mounted at
  `/app/data`), which survives repository re-clones and `docker compose down`
  on the same machine (removed only by `down -v` or `docker volume rm`).
  `deploy/xiaozhi-data` (mounted at `/app/data` in `xiaozhi-server` for
  `.config.yaml` and `.mcp_server_settings.json`) stays a bind mount alongside
  the `ollama-data` Docker volume (plus optional `tasmota-bridge-data` and
  `capability-data` volumes).
- **Host data**: `data/` is the default `PLATFORM_DATA_DIR` when running
  `platform-bridge` directly on the host outside `/app`. Keep host-run data
  separate from the `iot_platform_data` Compose volume (and any legacy
  `deploy/platform-data/` backup).
- **MCP profile export**: `PlatformStore.sync_to_agent_profile_json()` writes
  `agent_profile.json` in the bridge working directory on agent updates so
  standalone `thingsboard-mcp` can read it by default. That file is not
  bind-mounted into the deployed `platform-bridge` container, which resolves
  per-agent ThingsBoard credentials in-process.

Keep backups of the `iot_platform_data` volume, `deploy/xiaozhi-data`, and the Ollama
volume before moving a live installation. Do not commit those backups, secrets,
or API keys.
