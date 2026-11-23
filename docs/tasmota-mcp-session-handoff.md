# Capability-aware ThingsBoard MCP: session handoff

For current simulator and RPC instructions, see the [ThingsBoard RPC guide](thingsboard-rpc-contract.md).

**Status: paused and incomplete.** The objective is the implementation prompt at
`/home/ydt/.codex/attachments/904b3152-0c54-4c3c-b0e4-94a166d384c1/Pasted text.txt`.
Read it before resuming: it requires a simulated Tasmota → MQTT → ThingsBoard →
capability discovery → MCP RPC → device-response pipeline, isolation, deployment,
tests, and documentation. Do not modify the upstream XiaoZhi runtime or redesign
the frontend.

## Current implementation

- `tools/virtual_tasmota.py` simulates relay state, Tasmota FullTopic, command
  replies, telemetry, retained availability, delay, and repeated disconnects.
  `docker-compose.tasmota.yml` starts two relays and an authenticated Mosquitto
  broker; its `thingsboard` profile adds `tools/tasmota_bridge.py`.
- The bridge uses the ThingsBoard MQTT gateway API to register/map devices,
  forward telemetry and availability, translate configured methods, and return
  replies. It serializes commands per relay. A persistent SQLite journal retains
  recent request IDs and quarantines ambiguous in-flight commands across
  restarts. See `docs/thingsboard-rpc-contract.md` for configuration, manual
  recovery, limitations, and migration to physical devices.
- `thingsboard-mcp/src/capabilities.py` and `src/tools/capabilities.py` implement
  the persistent registry and capability tools. Discovery reads accessible
  devices and attributes, dashboard widgets and supported alias filters, and
  rule-chain metadata. It recognizes explicit declarations and a narrow static
  fixed-originator/literal-request rule-chain pattern. Unknown schemas remain
  incomplete; execution refreshes and validates before RPC. The original
  `send_rpc` MCP tool uses the same checks.
- The existing platform bridge routes in `platform-bridge/app.py` call the
  shared registry through `platform-bridge/agent_api_tools.py`, scoped to the
  agent ID and ThingsBoard credentials. Missing discovery or invalid parameters
  blocks RPC. `docker-compose.deploy.yml` mounts the shared code and builds
  `platform-bridge/runtime.Dockerfile`; this image was built but not deployed.
- `thingsboard-mcp/README.md` and `docs/thingsboard-rpc-contract.md` describe
  the capability declaration, setup, and known limits. The legacy live-check
  script was changed to avoid sending an arbitrary RPC.

## Verification observed in this session

- The final live test, `tests.test_tasmota_thingsboard_e2e`, **passed** after the
  pause request: 1 test in 34.515 seconds. It used a local disposable ThingsBoard
  test tenant, created uniquely named devices, an API key and a rule chain, and
  cleaned up its Compose project and ThingsBoard entities. It covered direct
  one-way and two-way RPC, concurrent requests, live rule-chain discovery,
  capability-validated MCP stdio execution, malformed and unknown methods,
  profile-cache isolation, revoked API key, and an offline relay.
- The most recent full ThingsBoard MCP suite passed **55 tests**. The most
  recent focused platform/agent, simulator, and bridge run passed **42 tests**.
  A separate live MQTT timing test passed for delay and disconnect/reconnect.
- The deployment bridge image built and imported the bridge and registry code.
  The running platform deployment was not rebuilt or restarted with the changes.

Re-run with an appropriate Python environment and a disposable tenant:

```sh
cd thingsboard-mcp
python -m unittest discover -s tests -p 'test_*.py'
cd ..
python -m unittest tests.test_agent_api_tools tests.test_agent_thingsboard \
  tests.test_device_agent_chat tests.test_virtual_tasmota tests.test_tasmota_bridge
TB_TEST_HOST=... TB_TEST_USERNAME=... TB_TEST_PASSWORD=... \
  python -m unittest tests.test_tasmota_thingsboard_e2e
```

The live test creates and deletes resources. Use a disposable tenant and review
its prerequisites before running it. Do not put credentials in source or logs.

## Remaining work

1. Audit every requirement in the original prompt against the current files and
   actual behavior; the objective has not passed a completion audit.
2. Expand rule-chain and dashboard discovery where it can be proven safe.
   Arbitrary scripts and runtime-dependent targets cannot generally be inferred
   without executing code or inventing device mappings. Such rule nodes are
   reported in `discovery_gaps`; state-dependent widgets without an explicit
   default are listed with an unresolved target and cannot be executed.
3. Review the security boundary and profile isolation end to end. The standalone
   network MCP transport has no per-client authentication; Compose binds it to
   localhost. Remote multi-client use needs an authenticated gateway or another
   verified isolation design. Validate permissions, cache refresh/invalidation,
   and concurrent calls under realistic configuration changes.
4. Review the bridge's correlation and recovery limits. Native Tasmota replies
   have no request IDs, so the bridge assumes exclusive command publishing.
   Quarantine requires manual state verification and journal recovery. Recent
   request-ID deduplication is bounded to 4096 IDs per relay.
5. Extend integration coverage for unresolved cases and failures as needed,
   verify deployment and physical-device migration instructions, and report
   actual results and remaining limitations. Do not claim completion based only
   on the successful simulated path.

## Worktree caution

The repository already had substantial unrelated staged/unstaged or untracked
work before this task, including changes in firmware, frontend, platform data,
deployment files, and deletions. The task also touched some already-dirty files.
Inspect `git status` and each relevant diff before editing; preserve all existing
user changes. No commit or deployment was made in this session. The older
[gateway handoff](archive/legacy-gateway-handoff.md) is a separate record.
