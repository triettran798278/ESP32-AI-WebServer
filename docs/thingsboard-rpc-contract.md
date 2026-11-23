# ThingsBoard RPC contracts and apartment demo

ThingsBoard is the source of truth for registered devices and their declared
RPC capabilities. Resolve the target device in ThingsBoard, then use the
parameter schema for that device and integration.

| Integration | Example method | Example `params` | How to verify the result |
| --- | --- | --- | --- |
| [Apartment control contract](#apartment-control-contract) | `setAppliancePower` | `{"target":{"areaId":"kitchen","applianceId":"ceiling_light"},"state":true}` | Check fresh telemetry for the selected appliance. |
| [Direct Tasmota relay commands](#direct-relay-rpcs) | `POWER2` | `1` | Check relay telemetry or observe the appliance. |
| [Smart-home devices and Device Workbench](#smart-home-devices-on-codehelpers) | `setFan` | `{"state":true}` | Read the two-way reply and check `fanOn` telemetry. |
| [Virtual switch](#virtual-switch) | `setPower` | `{"state":true}` | Read `power` in the two-way reply. |
| [Tasmota MQTT gateway](#mqtt-simulator-and-thingsboard-gateway) | `setPower` | `{"state":true}` in the sample configuration | Read the gateway reply and relay telemetry. |

## Apartment demo with Tasmota

### Presentation plan

The walkthrough demonstrates independent control of appliances within an area
and selective control across areas. The planned layout uses eight channels
across four ThingsBoard devices.

| Area | ThingsBoard device | Tasmota topic | `POWER1` | `POWER2` |
| --- | --- | --- | --- | --- |
| Living room and kitchen | `Living Room` | `living_room` | Living room lamp | Kitchen light |
| Bathroom | `Bathroom` | `bathroom` | Bathroom light | Exhaust fan |
| Bedroom 1 | `Bedroom` | `bedroom` | Bedroom 1 light | Bedroom 1 fan |
| Bedroom 2 | `Bedroom2` | `bedroom2` | Bedroom 2 light | Bedroom 2 fan |

Before rehearsal, verify each channel against the connected appliance and match
each controller's MQTT topic to the ThingsBoard `tasmotaTopic` attribute.
Start with all demo appliances off. Confirm each action by observing the
appliance or its ThingsBoard telemetry.

The [CodeHelpers check below](#verified-demo-records) covers the four demo
records. Verify the relay mappings before enabling dashboard and MCP controls
through the apartment contract.

| Scene | Presenter command | Expected result |
| --- | --- | --- |
| 1. Arrive home | “Turn on the living room lamp and the kitchen light.” | Both lights turn on through separate channels on the same controller. |
| 2. Ventilate the bathroom | “Turn on the bathroom fan and leave the light as it is.” | The fan turns on while the bathroom light stays off. |
| 3. Control the bedrooms independently | “Turn on the fans in bedrooms 1 and 2.” Then say “Turn off the fan in bedroom 2.” | Both fans turn on. Then the bedroom 2 fan stops while the bedroom 1 fan keeps running. |
| 4. Change fan speed, optional | “Set the bedroom 1 fan to speed 1.” Then say “Increase it to speed 3.” | The fan changes speed. Show the change from 1 to 3 in telemetry if available. |
| 5. Leave home | “Turn off all the lights and fans.” | All demo appliances are off. |

Include scene 4 only after verifying that the bedroom 1 controller supports
speed control and that both levels work during rehearsal. Relay commands
`POWER1` and `POWER2` switch power. A compatible speed controller uses a
separate command, such as Tasmota's
[`FanSpeed`](https://tasmota.github.io/docs/Commands/#fanspeed). If speed
control is unavailable, go directly from scene 3 to scene 5.

### Apartment control contract

This is the approved contract for the apartment dashboard and XiaoZhi/MCP.
The CodeHelpers inventory below records the currently observed declarations.

Send the RPC to the ThingsBoard device that owns the controller. Inside that
device, `target.areaId` selects the logical area and `target.applianceId`
selects the appliance within that area. Keep both IDs stable when display
labels change. For example, send this to `Living Room` to turn on the kitchen
ceiling light.

```json
{
  "method": "setAppliancePower",
  "params": {
    "target": {
      "areaId": "kitchen",
      "applianceId": "ceiling_light"
    },
    "state": true
  }
}
```

Use `true` for on and `false` for off. The authorized request path must
validate the exact `areaId` and `applianceId` pair against the target device,
require a boolean `state`, and reject missing or extra fields before emitting
a relay command. For example, `kitchen / ceiling_light` is valid on
`Living Room`; the same target on `Bedroom2` must be rejected. Declare the
allowed pairs in the device's `rpcCapabilities.methods.setAppliancePower.params`
JSON Schema. Where areas expose different appliances, use a schema that
checks valid pairs together.

#### Appliance mapping

Store a single mapping per ThingsBoard device as the `applianceMappings`
server attribute. Each entry identifies a pair of `areaId` and `applianceId`,
its `relayCommand`, and its `telemetryKey`. Derive the dashboard tree and
the capability schema from these entries. Use the same entries to translate
outbound commands and normalize inbound relay telemetry.

| ThingsBoard device | `areaId` | `applianceId` | Relay command | Boolean telemetry key |
| --- | --- | --- | --- | --- |
| `Living Room` | `living_room` | `ceiling_light` | `POWER1` | `livingRoomLampOn` |
| `Living Room` | `kitchen` | `ceiling_light` | `POWER2` | `kitchenLightOn` |
| `Bathroom` | `bathroom` | `ceiling_light` | `POWER1` | `bathroomLightOn` |
| `Bathroom` | `bathroom` | `exhaust_fan` | `POWER2` | `bathroomFanOn` |
| `Bedroom` | `bedroom_1` | `ceiling_light` | `POWER1` | `bedroom1LightOn` |
| `Bedroom` | `bedroom_1` | `fan` | `POWER2` | `bedroom1FanOn` |
| `Bedroom2` | `bedroom_2` | `ceiling_light` | `POWER1` | `bedroom2LightOn` |
| `Bedroom2` | `bedroom_2` | `fan` | `POWER2` | `bedroom2FanOn` |

The table is the demo configuration. Verify the wiring before publishing it to
ThingsBoard. A relay reassignment changes the mapping entry. Both callers
continue to use the same logical target.

#### Command and feedback

The dashboard and XiaoZhi/MCP send `setAppliancePower` as a one-way RPC for
this integration. The adapter resolves the exact pair and sends the mapped
Tasmota command with `1` for on or `0` for off. For the kitchen example,
`POWER2 = ON` is normalized to `{"kitchenLightOn":true}` on `Living Room`.

Show **Pending** after ThingsBoard accepts a command. Confirm the observed
state when telemetry from the same ThingsBoard device and appliance key is
newer than submission and matches the requested value. A report for another
appliance updates only that appliance. On timeout, show **Unconfirmed** and
retain the last observed state. A fresh matching reading observes state;
one-way RPC provides no per-command correlation.

The apartment rollout must update the dashboard, XiaoZhi/MCP, the apartment
helper, and the downlink and uplink together. Verify independent control of
both loads on `Living Room`, rejection of an invalid target pair, and the
pending and timeout cases before enabling controls. Fan speed remains a
separate optional capability for a controller with verified speed support.

### Direct relay RPCs

For this downlink, send an uppercase relay method and an integer parameter to
`POST /api/rpc/oneway/<deviceId>`. Use `0` for off and `1` for on. The
converter forwards the command to the controller's Tasmota MQTT topic.

```json
{"method":"POWER2","params":1}
```

A successful submission records that ThingsBoard accepted the RPC. Check relay
telemetry or the appliance to confirm execution. The normalized apartment
contract uses direct relay commands inside the adapter.

The [apartment helper script](../scripts/apartment_demo.sh) uses its own
five-channel mapping.

## Smart-home devices on CodeHelpers

Find devices under **Entities → Devices** in the
[CodeHelpers ThingsBoard tenant](https://codehelpers.tech/). Use the exact
device name and ID from the record. Check **Latest telemetry** for reported
fields and **Attributes** for the device's `rpcCapabilities` or
`rpc_contract`. The [MCP registry](#capability-aware-mcp) reads these
declarations when resolving executable actions. Device names, telemetry keys,
and method names are case-sensitive.

### Verified demo records

The November 22, 2026 read-only tenant check found these four demo records.
Telemetry keys are the keys returned by ThingsBoard. The RPC column lists the
methods declared in structured device attributes at the time of the check.

| Exact device name | Reported telemetry keys | Declared RPC methods |
| --- | --- | --- |
| `Living Room` | `temperature`, `humidity`, `lightOn` | `getState`, `setLight` |
| `Bathroom` | `humidity`, `fanOn` | `getState`, `setFan` |
| `Bedroom` | `temperature`, `humidity`, `fanOn` | `getState`, `setFan` |
| `Bedroom2` | `temperature`, `humidity`, `lightOn` | No structured declaration found |

Verify current device attributes before rehearsal. Telemetry keys can remain
in ThingsBoard after a device stops reporting, so check the latest timestamps
when confirming device connectivity.

### Telemetry and credentials

Publish to `v1/devices/me/telemetry` over MQTT with the device's own ThingsBoard
access token as the MQTT username. Use the MQTT TLS endpoint configured for the
tenant. The tenant API key is an administrative credential and belongs on the
server. The equivalent device HTTPS endpoint is
`POST /api/v1/<device-access-token>/telemetry`. See the ThingsBoard
[MQTT connection](https://thingsboard.io/docs/reference/mqtt-api/getting-connected/)
and [telemetry](https://thingsboard.io/docs/reference/mqtt-api/telemetry/) references.

For example, publish `{"temperature":24.5,"humidity":56,"lightOn":false}`.
Report temperature in degrees Celsius and humidity as a number from 0 to 100
percent relative humidity. State fields such as `lightOn` and `fanOn` are
booleans. Gas and smoke flags reflect the thresholds in the sensor or detector.

Publish available readings at startup, periodically, and when alarms, motion,
contact switches, or actuator states change. Omit unavailable measurements.
ThingsBoard timestamps a flat payload on receipt. A device with a synchronized
clock can send its own timestamp in Unix milliseconds, for example
`{"ts":1760000000000,"values":{"temperature":24.5}}`.

Devices can declare location, simulation status, and expected telemetry keys
through `location`, `simulated`, and `telemetryKeys` server attributes.
For executable methods, use a structured capability declaration with a JSON
Schema for each method's `params`.

### Two-way RPC

The following payloads define smart-home device methods. Use the subset
declared for the selected ThingsBoard device.

Subscribe to `v1/devices/me/rpc/request/+` after each MQTT connection. For a
command on `v1/devices/me/rpc/request/<requestId>`, publish the reply on
`v1/devices/me/rpc/response/<requestId>` with the same ID. A management client
calls `POST /api/rpc/twoway/<deviceId>` with the method and parameters. See the
[ThingsBoard MQTT RPC reference](https://thingsboard.io/docs/reference/mqtt-api/rpc/).

| Method | Exact `params` shape | Result |
| --- | --- | --- |
| `getState` | `{}` | Return the current available readings and actuator state. |
| `setLight` | `{"state":true}` or `{"state":false}` | Set the light to the requested state and report `lightOn`. |
| `setFan` | `{"state":true}` or `{"state":false}` | Set the fan to the requested state and report `fanOn`. |
| `setLock` | `{"locked":true}` or `{"locked":false}` | Request lock or unlock and report the observed `locked` state. `doorOpen` reports the contact sensor independently. Firmware must apply local authorization and lock interlocks. |
| `setAutoLight` | `{"enabled":true}` or `{"enabled":false}` | Enable or disable local Hallway motion-based lighting. While enabled, `setLight` returns `REJECTED`. Disable automatic mode before a manual light command. |

Example request and successful reply for `LivingRoom`.

```json
{"method":"setLight","params":{"state":true}}
```

```json
{"ok":true,"state":{"temperature":24.5,"humidity":56,"lightOn":true}}
```

Publish changed actuator state as telemetry after applying the command. Setting
an actuator to its current value is safe to repeat. Return
`{"ok":false,"error":"INVALID_PARAMS"}` for missing, extra, or wrongly typed
parameters, `UNKNOWN_METHOD` for a command the device does not implement, and
`REJECTED` for a command blocked by mode, interlocks, or an actuator fault. On
failure, report the actual state through telemetry and avoid claiming success.

### Device Workbench

Open the [local Device Workbench](http://127.0.0.1:8011/) on the project host.
The Workbench can simulate registered devices using matching profiles from
[`tools/device_simulator/devices.py`](../tools/device_simulator/devices.py)
and their ThingsBoard device tokens. Match each token to its exact device
record. The `simulated` server attribute can identify software devices
during a firmware handoff.

Select a device to operate its controls, edit sensor fields, preview the JSON,
and send telemetry. The workbench also publishes a snapshot every 30 seconds.
Pause a device to suspend publishing and RPC polling. Resume to send a fresh
snapshot. ThingsBoard applies its own inactivity timeout after a device pauses.
After a restart, the Workbench applies profile defaults and any configured
`initialValues` overrides.

The browser talks to the local Workbench API. The Workbench publishes telemetry
and polls for RPCs with a separate access token for each configured device via the
[ThingsBoard HTTP device API](https://thingsboard.io/docs/reference/http-api/rpc/).

To run it on another project host, prepare a private JSON file containing
the HTTPS `host` and a `tokens` object mapping registered device names to their
individual ThingsBoard access tokens. Use file mode 600 and set
`DEVICE_WORKBENCH_CONFIG` to its absolute path when running Compose.

```sh
docker compose -f docker-compose.simulator.yml up -d --build
```

Pause a workbench device or stop the workbench before handing that device's
credentials to physical firmware. This gives telemetry and RPC a single device
process for that token.

## Virtual switch

The virtual switch publishes a `rpc_contract` client attribute as a JSON object.
Version 1 contains a `methods` object keyed by RPC method name. Each method has
a description and a JSON Schema describing its `params`. The virtual switch
supports `setPower` with `{"state": true}` or `{"state": false}`, and
`getState` and `togglePower` with `{}`. Its responses report `power` and
`simulated`; invalid arguments return an error without changing the state.

The device also publishes the legacy `rpc_methods` text attribute. Read the
structured `rpc_contract` on the target device to validate arguments and use
two-way RPC to receive its reply. For native Tasmota MQTT testing, use the
virtual relay or gateway described below.

## Virtual Tasmota relay

`tools/virtual_tasmota.py` provides a separate MQTT-based virtual relay for
testing a Tasmota integration. Install `tools/requirements.txt` and start it with
`MQTT_HOST`, `TASMOTA_PREFIX`, and `TASMOTA_TOPIC` set for the integration.
`MQTT_PORT` defaults to 1883; `MQTT_USERNAME` and `MQTT_PASSWORD` are optional.
Without a prefix, it uses the usual `cmnd/<topic>/POWER`, `stat/<topic>/RESULT`,
`stat/<topic>/POWER`, and `tele/<topic>/LWT` topic layout. A prefix is placed
before those paths for integrations that namespace their topics.
Set `TASMOTA_FULL_TOPIC` to override that layout, using `%prefix%` and `%topic%`
once each, for example `site/%topic%/%prefix%/`. When set, it replaces the
layout generated from `TASMOTA_PREFIX`.

The relay accepts `ON`, `OFF`, `TOGGLE`, `1`, `0`, `2`, `true`, `false`,
and an empty or `?` query on its `POWER` command topic. It publishes
Tasmota-style status messages and periodic `STATE` data. The simulated relay
starts in the off state after a restart.

The [repository downlink encoder](../start-tasmota-sim.sh) maps `setPower`
and `setGpio` to `POWER`. It accepts direct values such as `true` or
`"ON"` and objects with a `state` or `value` field. Use the mapping and
schema declared for the target device and check power telemetry after a
one-way RPC. The gateway below provides its own mapping for the local stack.

## Capability-aware MCP

The standalone MCP server and the platform bridge read `rpcCapabilities` or
`rpc_contract` from accessible device attributes. Each structured attribute
contains a `methods` map with a JSON Schema in each executable method's
`params` field. Method entries may also include a description. Migrate
devices that expose only the legacy `rpc_methods` text attribute to a structured
contract so the registry can validate arguments.

### Discovery sources

| Source | What the registry can resolve |
| --- | --- |
| Device attributes | Methods and parameter schemas from the structured contract. |
| Dashboard widgets | Method names for direct targets and supported aliases. Alias filters use ThingsBoard's read-only entity query and the dashboard's default sort order. State-dependent aliases need an explicit default device to resolve. Supply parameter schemas through a structured declaration. |
| Rule chains | A node can declare `deviceId` and `rpcCapabilities`. The registry also recognizes a fixed originator followed directly by a literal JSON RPC transformation and an RPC request node. These literal transformations supply method and node references and need a schema from a declaration. |

Discovery is read-only. The platform summary and discovery tools report
unresolved rule nodes in `discovery_gaps`. A result with `available: true`
indicates a discovered method declaration. The separate `availability` field
reflects the device's server-side `active` attribute when present and is
`unknown` otherwise.

### Execution and deployment

`send_rpc` and `execute_device_action` refresh discovery before execution
and apply the same validation. Execution requires a resolved device and a
complete, valid, supported, and unambiguous parameter schema. ThingsBoard
checks the caller's RPC permission at dispatch. The platform bridge uses
the agent's credentials and profile ID. A missing registry or failed refresh
blocks RPC execution while the read-only tools remain available.

The SQLite cache is scoped to the profile and connection credentials. For
standalone MCP, set `TB_CAPABILITY_DB` to a persistent writable path. The
standalone Compose file mounts one. The platform bridge stores its cache in
`capabilities.sqlite3` under `PLATFORM_DATA_DIR`. For a local platform bridge, install
[`thingsboard-mcp/requirements.txt`](../thingsboard-mcp/requirements.txt)
and make both the bridge and sibling MCP source available on `PYTHONPATH`.
Rebuild the deployment image when upgrading its schema validation dependencies.

## MQTT simulator and ThingsBoard gateway

Set `MQTT_USERNAME` and `MQTT_PASSWORD` in the environment, then run
`docker compose -f docker-compose.tasmota.yml up -d --build`. The authenticated
broker and two independent relays communicate on the Compose network. Set
`TASMOTA_FULL_TOPIC` to change both simulators' topic layout. Optional
`TASMOTA_RESPONSE_DELAY` delays each command, in seconds. Set both
`TASMOTA_DISCONNECT_AFTER` and `TASMOTA_DISCONNECT_DURATION` to positive seconds
to repeatedly take each simulator offline and reconnect it. Relay state persists
through simulated disconnects but resets on container restart.

To enable the gateway, create a ThingsBoard device with **Is gateway** enabled,
set its access token in `TB_GATEWAY_TOKEN`, and set `TB_MQTT_HOST` and optionally
`TB_MQTT_PORT` for the ThingsBoard MQTT listener. The default host is
`host.docker.internal`; Docker Compose maps that name to the Linux host gateway.
Run `docker compose -f docker-compose.tasmota.yml --profile thingsboard up -d
--build`. The bridge connects downstream devices when their retained LWT says
`Online`, automatically registering missing device names with ThingsBoard, and
forwards STATE and RESULT telemetry. It forwards disconnects and reconnects.

Copy [`tools/tasmota-bridge.example.json`](../tools/tasmota-bridge.example.json)
and set `TASMOTA_BRIDGE_CONFIG` to its
absolute path to customize device names, FullTopic and RPC-to-command mappings.
The ThingsBoard device names must be unique. The gateway publishes a
`rpcCapabilities` attribute from its configured method mappings or from an
explicit contract in the device configuration. MCP reads the published
attribute. The sample configuration maps `setPower` with
`{"state":true}` or `{"state":false}` to `POWER` and generates this schema.

```json
{"methods":{"setPower":{"description":"setPower via Tasmota POWER","params":{"type":"object","properties":{"state":{"type":"boolean"}},"required":["state"],"additionalProperties":false}}}}
```

### Request correlation and recovery

The bridge serializes commands per device and correlates each ThingsBoard request
with the next matching Tasmota `RESULT`. Tasmota responses have no request ID, so
the bridge must be the only command publisher for those devices. A timeout, a
disconnect with a command in flight, or a restart with outstanding commands
quarantines the device in the persistent bridge volume. Verify the relay state
and drain any delayed messages before manually clearing that device's journal
entry. The journal remembers the most recent 4096 request IDs per device;
reused IDs are rejected because Tasmota cannot distinguish a retry from a new
request. Broker and ThingsBoard MQTT connections in this development stack are
unencrypted; use a trusted network or configure TLS before remote deployment.
For physical Tasmota devices, keep the same MQTT topic and method mappings and
replace the simulator containers with real devices connected to the broker.

After verifying the physical state and draining delayed MQTT messages, clear a
quarantined relay's journal entry with the bridge stopped. Substitute the relay
topic and ThingsBoard device name from your bridge configuration:

```sh
docker compose -f docker-compose.tasmota.yml stop thingsboard-bridge
docker compose -f docker-compose.tasmota.yml run --rm --no-deps --entrypoint python thingsboard-bridge \
  -c 'import json,sqlite3,sys; db=sqlite3.connect("/data/bridge.sqlite3"); db.execute("DELETE FROM relay_state WHERE device = ?", (json.dumps(sys.argv[1:3]),)); db.commit()' \
  relay-a 'Simulated Tasmota A'
docker compose -f docker-compose.tasmota.yml --profile thingsboard up -d thingsboard-bridge
```

Clearing an entry also clears its remembered request IDs. Do not replay an
earlier command when its outcome is unknown.

### End-to-end test

The opt-in [`tests/test_tasmota_thingsboard_e2e.py`](../tests/test_tasmota_thingsboard_e2e.py)
creates uniquely named devices
in a disposable ThingsBoard tenant and removes them afterward. Set
`TB_TEST_HOST`, `TB_TEST_USERNAME` and `TB_TEST_PASSWORD`; optionally set
`TB_TEST_MQTT_HOST` and `TB_TEST_MQTT_PORT` as visible inside Docker. Install
`thingsboard-mcp/requirements.txt`, then run
`python -m unittest tests.test_tasmota_thingsboard_e2e`. It exercises direct
one-way and two-way RPC and MCP stdio execution using real MQTT relays.
