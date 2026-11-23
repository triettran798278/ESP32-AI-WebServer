import asyncio
import hashlib
import importlib
import importlib.util
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

bridge = importlib.import_module("platform-bridge.app")
api_tools = importlib.import_module("platform-bridge.agent_api_tools")
pipeline = importlib.import_module("platform-bridge.tool_pipeline")


def _apartment_capabilities():
    def appliance_schema(area_a, app_a, area_b, app_b):
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["target", "state"],
            "properties": {
                "target": {
                    "oneOf": [
                        {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["areaId", "applianceId"],
                            "properties": {"areaId": {"const": area_a}, "applianceId": {"const": app_a}},
                        },
                        {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["areaId", "applianceId"],
                            "properties": {"areaId": {"const": area_b}, "applianceId": {"const": app_b}},
                        },
                    ]
                },
                "state": {"type": "boolean"},
            },
        }

    relay_schema = {"type": "integer", "enum": [0, 1]}
    return [
        {
            "device_id": "dev-bed2", "device_name": "Bedroom2", "device_type": "default",
            "method": "setAppliancePower", "description": "Control Bedroom2",
            "parameter_schema": appliance_schema("bedroom_2", "ceiling_light", "bedroom_2", "fan"),
            "schema_complete": True, "availability": "online",
        },
        {
            "device_id": "dev-bed2", "device_name": "Bedroom2", "device_type": "default",
            "method": "POWER1", "description": "Direct Tasmota relay 1 (Đèn phòng ngủ 2)",
            "parameter_schema": relay_schema, "schema_complete": True, "availability": "online",
        },
        {
            "device_id": "dev-bed2", "device_name": "Bedroom2", "device_type": "default",
            "method": "POWER2", "description": "Direct Tasmota relay 2 (Quạt phòng ngủ 2)",
            "parameter_schema": relay_schema, "schema_complete": True, "availability": "online",
        },
        {
            "device_id": "dev-bath", "device_name": "Bathroom", "device_type": "default",
            "method": "setAppliancePower", "description": "Control Bathroom",
            "parameter_schema": appliance_schema("bathroom", "ceiling_light", "bathroom", "exhaust_fan"),
            "schema_complete": True, "availability": "online",
        },
        {
            "device_id": "dev-bath", "device_name": "Bathroom", "device_type": "default",
            "method": "POWER1", "description": "Direct Tasmota relay 1 (Đèn phòng tắm)",
            "parameter_schema": relay_schema, "schema_complete": True, "availability": "online",
        },
        {
            "device_id": "dev-bath", "device_name": "Bathroom", "device_type": "default",
            "method": "POWER2", "description": "Direct Tasmota relay 2 (Quạt hút phòng tắm)",
            "parameter_schema": relay_schema, "schema_complete": True, "availability": "online",
        },
        {
            "device_id": "dev-living", "device_name": "Living Room", "device_type": "default",
            "method": "setAppliancePower", "description": "Control Living Room",
            "parameter_schema": appliance_schema("living_room", "ceiling_light", "kitchen", "ceiling_light"),
            "schema_complete": True, "availability": "online",
        },
        {
            "device_id": "dev-living", "device_name": "Living Room", "device_type": "default",
            "method": "POWER1", "description": "Direct Tasmota relay 1 (Đèn phòng khách)",
            "parameter_schema": relay_schema, "schema_complete": True, "availability": "online",
        },
        {
            "device_id": "dev-living", "device_name": "Living Room", "device_type": "default",
            "method": "POWER2", "description": "Direct Tasmota relay 2 (Đèn bếp)",
            "parameter_schema": relay_schema, "schema_complete": True, "availability": "online",
        },
        {
            "device_id": "dev-bed1", "device_name": "Bedroom", "device_type": "default",
            "method": "setAppliancePower", "description": "Control Bedroom",
            "parameter_schema": appliance_schema("bedroom_1", "ceiling_light", "bedroom_1", "fan"),
            "schema_complete": True, "availability": "online",
        },
        {
            "device_id": "dev-bed1", "device_name": "Bedroom", "device_type": "default",
            "method": "POWER1", "description": "Direct Tasmota relay 1 (Đèn phòng ngủ 1)",
            "parameter_schema": relay_schema, "schema_complete": True, "availability": "online",
        },
        {
            "device_id": "dev-bed1", "device_name": "Bedroom", "device_type": "default",
            "method": "POWER2", "description": "Direct Tasmota relay 2 (Quạt phòng ngủ 1)",
            "parameter_schema": relay_schema, "schema_complete": True, "availability": "online",
        },
    ]


def _seed_capabilities_db(data_dir: str, host: str, api_key: str, profile_id: str, capabilities: list):
    db_path = Path(data_dir) / "capabilities.sqlite3"
    integration_id = hashlib.sha256(
        json.dumps([host.rstrip("/"), api_key, None, None, None, profile_id]).encode()
    ).hexdigest()
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS capabilities (integration TEXT PRIMARY KEY, data TEXT NOT NULL)")
        conn.execute("INSERT OR REPLACE INTO capabilities VALUES (?, ?)", (integration_id, json.dumps(capabilities)))


class ToolPipelineUnitTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.allowed = patch.dict("os.environ", {"THINGSBOARD_ALLOWED_ORIGINS": "http://tb.test"})
        self.allowed.start()
        self.addCleanup(self.allowed.stop)

    def test_compile_apartment_catalog_flattens_and_pairs_bilingual_labels(self):
        catalog = pipeline.compile_action_catalog(_apartment_capabilities())
        self.assertEqual(len(catalog.targets), 8)
        self.assertEqual(catalog.custom_methods, [])

        kitchen = catalog.get("kitchen.ceiling_light")
        self.assertIsNotNone(kitchen)
        self.assertEqual(kitchen.device_name, "Living Room")
        self.assertEqual(kitchen.device_id, "dev-living")
        self.assertEqual(kitchen.category, "light")
        self.assertIn("Đèn bếp", kitchen.label)
        self.assertEqual(
            kitchen.actions["on"],
            ("setAppliancePower", {"target": {"areaId": "kitchen", "applianceId": "ceiling_light"}, "state": True}),
        )

        bath_fan = catalog.get("bathroom.exhaust_fan")
        self.assertEqual(bath_fan.category, "fan")
        self.assertIn("Quạt hút phòng tắm", bath_fan.label)

    def test_compile_tasmota_workbench_and_custom_schemas(self):
        caps = [
            {
                "device_id": "id-a", "device_name": "Simulated Tasmota A", "device_type": "default",
                "method": "setPower", "schema_complete": True, "availability": "online",
                "parameter_schema": {"type": "object", "properties": {"state": {"type": "boolean"}}, "required": ["state"]},
            },
            {
                "device_id": "id-a", "device_name": "Simulated Tasmota A", "device_type": "default",
                "method": "togglePower", "schema_complete": True, "availability": "online",
                "parameter_schema": {"type": "object", "properties": {}},
            },
            {
                "device_id": "id-b", "device_name": "Simulated Tasmota B", "device_type": "default",
                "method": "setPower", "schema_complete": True, "availability": "online",
                "parameter_schema": {"type": "object", "properties": {"state": {"type": "boolean"}}, "required": ["state"]},
            },
            {
                "device_id": "id-hall", "device_name": "Hallway", "device_type": "default",
                "method": "getState", "schema_complete": True, "availability": "online",
                "parameter_schema": {"type": "object", "properties": {}},
            },
            {
                "device_id": "id-hall", "device_name": "Hallway", "device_type": "default",
                "method": "setLight", "schema_complete": True, "availability": "online",
                "parameter_schema": {"type": "object", "properties": {"state": {"type": "boolean"}}},
            },
            {
                "device_id": "id-hall", "device_name": "Hallway", "device_type": "default",
                "method": "setAutoLight", "schema_complete": True, "availability": "online",
                "parameter_schema": {"type": "object", "properties": {"enabled": {"type": "boolean"}}},
            },
            {
                "device_id": "id-ent", "device_name": "Entrance", "device_type": "default",
                "method": "setLock", "schema_complete": True, "availability": "online",
                "parameter_schema": {"type": "object", "properties": {"locked": {"type": "boolean"}}},
            },
            {
                "device_id": "id-cal", "device_name": "Sensor1", "device_type": "default",
                "method": "calibrate", "description": "Calibrate sensor", "schema_complete": True, "availability": "online",
                "parameter_schema": {"type": "object", "properties": {"offset": {"type": "integer"}}},
            },
            {
                "device_id": "id-inc", "device_name": "Broken", "device_type": "default",
                "method": "setPower", "schema_complete": False, "availability": "online",
                "parameter_schema": None,
            },
        ]
        catalog = pipeline.compile_action_catalog(caps)
        t_a = catalog.get("simulated_tasmota_a.power")
        t_b = catalog.get("simulated_tasmota_b.power")
        self.assertIn("toggle", t_a.actions)
        self.assertNotIn("toggle", t_b.actions)
        self.assertEqual(catalog.get("hallway.light").category, "light")
        self.assertEqual(catalog.get("hallway.auto_light").category, "other")
        self.assertEqual(catalog.get("entrance.lock").category, "lock")
        self.assertEqual([cm["method"] for cm in catalog.custom_methods], ["calibrate"])
        self.assertIsNone(catalog.get("broken.power"))

    def test_load_cached_catalog_reads_sqlite_without_http(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"PLATFORM_DATA_DIR": tmp}):
            _seed_capabilities_db(tmp, "http://tb.test", "secret-key", "agent-1", _apartment_capabilities())
            catalog = pipeline.load_cached_catalog({"host": "http://tb.test", "api_key": "secret-key"}, "agent-1")
        self.assertIsNotNone(catalog)
        self.assertEqual(len(catalog.targets), 8)

    def test_resolve_and_ambiguity_safety_gate(self):
        catalog = pipeline.compile_action_catalog(_apartment_capabilities())

        # Positive alias & exact resolution
        t, err = pipeline.resolve_catalog_target(catalog, "Đèn bếp")
        self.assertIsNone(err)
        self.assertEqual(t.target_id, "kitchen.ceiling_light")

        # Multi-appliance bare device name fails safely
        t_bare, err_bare = pipeline.resolve_catalog_target(catalog, "Bathroom")
        self.assertIsNone(t_bare)
        self.assertEqual(err_bare["error_code"], "ambiguous_target")

        # Ambiguous natural language blocked (including dual-room hedging on a singular prompt)
        for bad_prompt, proposed in [
            ("Turn off bed", [catalog.get("bedroom_1.fan")]),
            ("Bật đèn phòng ngủ", [catalog.get("bedroom_1.ceiling_light")]),
            ("Bật đèn phòng ngủ", [catalog.get("bedroom_1.ceiling_light"), catalog.get("bedroom_2.ceiling_light")]),
            ("Turn off room", [catalog.get("living_room.ceiling_light")]),
            ("Turn on the fan", [catalog.get("bedroom_1.fan")]),
            ("Turn off bathroom", [catalog.get("bathroom.ceiling_light")]),
        ]:
            blocked = pipeline.check_user_ambiguity(bad_prompt, [], proposed, catalog)
            self.assertIsNotNone(blocked, f"Expected ambiguity block for {bad_prompt!r}")
            self.assertEqual(blocked["error_code"], "ambiguous_target")

        no_custom_names = [t["function"]["name"] for t in pipeline.build_pipeline_tools(True, include_custom_rpc=False)]
        self.assertIn("control_targets", no_custom_names)
        self.assertNotIn("execute_device_action", no_custom_names)

        # Category mismatch blocked
        cat_err = pipeline.check_user_ambiguity(
            "Turn on the bathroom fan", [], [catalog.get("bathroom.ceiling_light")], catalog
        )
        self.assertIsNotNone(cat_err)
        self.assertEqual(cat_err["error_code"], "category_mismatch")

        # Wrong location ("kitchen fan 999" -> bedroom_1.fan) blocked
        loc_err = pipeline.check_user_ambiguity(
            "Turn off nonexistent kitchen fan 999", [], [catalog.get("bedroom_1.fan")], catalog
        )
        self.assertIsNotNone(loc_err)
        self.assertEqual(loc_err["error_code"], "device_not_found")

        # Valid abstract, disambiguated, scene, plural, multi-clause, pronoun, and telemetry-filter prompts allowed
        all_lights = [t for t in catalog.targets if t.category == "light"]
        all_targets = list(catalog.targets)
        for good_prompt, hist, tel_checked, proposed in [
            ("It's too hot in bedroom 2", [], False, [catalog.get("bedroom_2.fan")]),
            ("Phòng ngủ 2 nóng quá", [], False, [catalog.get("bedroom_2.fan")]),
            ("It's too dark in the bathroom", [], False, [catalog.get("bathroom.ceiling_light")]),
            ("Phòng tắm bí và ẩm quá", [], False, [catalog.get("bathroom.exhaust_fan")]),
            ("Turn off the kitchen light", [], False, [catalog.get("kitchen.ceiling_light")]),
            ("Turn off all lights", [], False, all_lights),
            ("Tôi đi ngủ đây", [], False, all_lights),
            ("I'm leaving home, turn everything off", [], False, all_targets),
            ("Turn on bathroom light and bedroom 2 fan", [], False, [catalog.get("bathroom.ceiling_light"), catalog.get("bedroom_2.fan")]),
            ("Turn it off", [{"role": "user", "content": "check bathroom light"}], False, [catalog.get("bathroom.ceiling_light")]),
            ("Turn off the hottest room fan", [], True, [catalog.get("bedroom_2.fan")]),
        ]:
            res = pipeline.check_user_ambiguity(good_prompt, hist, proposed, catalog, telemetry_checked=tel_checked)
            self.assertIsNone(res, f"Unexpected ambiguity block for {good_prompt!r}: {res}")

    def test_tasmota_pair_ambiguity_vs_distinguishing_suffix(self):
        caps = [
            {
                "device_id": "id-a", "device_name": "Simulated Tasmota A", "device_type": "default",
                "method": "setPower", "schema_complete": True, "availability": "online",
                "parameter_schema": {"type": "object", "properties": {"state": {"type": "boolean"}}},
            },
            {
                "device_id": "id-b", "device_name": "Simulated Tasmota B", "device_type": "default",
                "method": "setPower", "schema_complete": True, "availability": "online",
                "parameter_schema": {"type": "object", "properties": {"state": {"type": "boolean"}}},
            },
        ]
        catalog = pipeline.compile_action_catalog(caps)
        self.assertIsNotNone(pipeline.check_user_ambiguity(
            "bật nguồn simulated tasmota", [], [catalog.get("simulated_tasmota_a.power")], catalog
        ))
        self.assertIsNone(pipeline.check_user_ambiguity(
            "bật nguồn simulated_tasmota_a", [], [catalog.get("simulated_tasmota_a.power")], catalog
        ))

    async def test_run_agent_chat_abstract_batch_and_same_device_ordering(self):
        caps = _apartment_capabilities()
        catalog = pipeline.compile_action_catalog(caps)
        agent = {
            "id": "agent-1", "name": "QA", "language": "en", "tool_policy": "full_control",
            "integrations": {"thingsboard": {"host": "http://tb.test", "api_key": "private"}},
        }

        rpc_calls = []

        @asynccontextmanager
        async def fake_scoped(cfg, pid):
            reg = MagicMock()
            reg.fresh = True
            reg.list.return_value = caps
            yield reg

        async def fake_execute(client, cfg, name, args, read_only=False, profile_id=None):
            if name == "execute_device_action":
                rpc_calls.append((args["device_identifier"], args["method"], args["params"]))
                return {"status": "success", "success": True, "confirmed": False, "delivery": "submitted"}
            return {"status": "error", "success": False}

        # Batch turns off both Living Room appliances (living_room.ceiling_light and kitchen.ceiling_light) + bathroom.ceiling_light
        # Also includes a duplicate bathroom.ceiling_light to verify deduplication.
        model_replies = [
            {"choices": [{"message": {"role": "assistant", "tool_calls": [{
                "id": "c1",
                "function": {
                    "name": "control_targets",
                    "arguments": json.dumps({
                        "actions": [
                            {"target_id": "living_room.ceiling_light", "action": "off"},
                            {"target_id": "kitchen.ceiling_light", "action": "off"},
                            {"target_id": "bathroom.ceiling_light", "action": "off"},
                            {"target_id": "bathroom.ceiling_light", "action": "off"},
                        ]
                    }),
                },
            }]}}]},
            {"choices": [{"message": {"content": "Turned off those lights."}}]},
        ]

        def resp(data):
            r = MagicMock(status_code=200)
            r.json.return_value = data
            r.raise_for_status = lambda: None
            return r

        client = AsyncMock()
        client.post.side_effect = [resp(d) for d in model_replies]
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {"PLATFORM_DATA_DIR": tmp}), \
                patch("httpx.AsyncClient", return_value=ctx), \
                patch.object(api_tools, "scoped_registry", side_effect=fake_scoped), \
                patch.object(api_tools, "execute", side_effect=fake_execute):
            _seed_capabilities_db(tmp, "http://tb.test", "private", "agent-1", caps)
            res = await bridge.run_agent_chat(agent, bridge.AgentChatRequest(message="Turn off all living room, kitchen, and bathroom lights"))

        self.assertEqual(res["reply"], "Turned off those lights.")
        self.assertEqual(len(rpc_calls), 3)
        self.assertEqual(len(res["tool_calls"]), 3)
        self.assertTrue(all(tc["name"] == "execute_device_action" for tc in res["tool_calls"]))
        # Same-device calls for dev-living stay in exact order
        living_calls = [c for c in rpc_calls if c[0] == "dev-living"]
        self.assertEqual(len(living_calls), 2)
        self.assertEqual(living_calls[0][2]["target"]["areaId"], "living_room")
        self.assertEqual(living_calls[1][2]["target"]["areaId"], "kitchen")

    async def test_run_agent_chat_blocks_ambiguous_guess_and_nudges_hallucinated_abstract_reply(self):
        caps = _apartment_capabilities()
        agent = {
            "id": "agent-1", "name": "QA", "language": "en", "tool_policy": "full_control",
            "integrations": {"thingsboard": {"host": "http://tb.test", "api_key": "private"}},
        }

        @asynccontextmanager
        async def fake_scoped(cfg, pid):
            reg = MagicMock()
            reg.fresh = True
            reg.list.return_value = caps
            yield reg

        rpc_executed = []

        async def fake_execute(client, cfg, name, args, read_only=False, profile_id=None):
            rpc_executed.append(args)
            return {"status": "success", "success": True}

        def resp(data):
            r = MagicMock(status_code=200)
            r.json.return_value = data
            r.raise_for_status = lambda: None
            return r

        # 1. Ambiguous prompt "Turn off bed": model guesses bedroom_1.fan -> pipeline blocks -> model asks user.
        model_ambig = [
            {"choices": [{"message": {"role": "assistant", "tool_calls": [{
                "id": "bad1",
                "function": {"name": "control_targets", "arguments": json.dumps({"actions": [{"target_id": "bedroom_1.fan", "action": "off"}]})},
            }]}}]},
            {"choices": [{"message": {"content": "Did you mean Bedroom 1 or Bedroom 2, and the light or the fan?"}}]},
        ]
        client1 = AsyncMock()
        client1.post.side_effect = [resp(d) for d in model_ambig]
        ctx1 = MagicMock()
        ctx1.__aenter__ = AsyncMock(return_value=client1)
        ctx1.__aexit__ = AsyncMock(return_value=False)

        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {"PLATFORM_DATA_DIR": tmp}), \
                patch("httpx.AsyncClient", return_value=ctx1), \
                patch.object(api_tools, "scoped_registry", side_effect=fake_scoped), \
                patch.object(api_tools, "execute", side_effect=fake_execute):
            _seed_capabilities_db(tmp, "http://tb.test", "private", "agent-1", caps)
            res1 = await bridge.run_agent_chat(agent, bridge.AgentChatRequest(message="Turn off bed"))

        self.assertEqual(rpc_executed, [])
        self.assertIn("Bedroom 1", res1["reply"])
        self.assertEqual(json.loads(res1["tool_calls"][0]["result"])["error_code"], "ambiguous_target")

        # 2. Abstract prompt "It's too dark in the bathroom": LLM first hallucinates -> nudged -> executes control_targets!
        model_nudge = [
            {"choices": [{"message": {"content": "The bathroom ceiling light has been turned on."}}]},
            {"choices": [{"message": {"role": "assistant", "tool_calls": [{
                "id": "ok1",
                "function": {"name": "control_targets", "arguments": json.dumps({"actions": [{"target_id": "bathroom.ceiling_light", "action": "on"}]})},
            }]}}]},
            {"choices": [{"message": {"content": "Bathroom ceiling light is now on."}}]},
        ]
        client2 = AsyncMock()
        client2.post.side_effect = [resp(d) for d in model_nudge]
        ctx2 = MagicMock()
        ctx2.__aenter__ = AsyncMock(return_value=client2)
        ctx2.__aexit__ = AsyncMock(return_value=False)

        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {"PLATFORM_DATA_DIR": tmp}), \
                patch("httpx.AsyncClient", return_value=ctx2), \
                patch.object(api_tools, "scoped_registry", side_effect=fake_scoped), \
                patch.object(api_tools, "execute", side_effect=fake_execute):
            _seed_capabilities_db(tmp, "http://tb.test", "private", "agent-1", caps)
            res2 = await bridge.run_agent_chat(agent, bridge.AgentChatRequest(message="It's too dark in the bathroom"))

        self.assertEqual(len(rpc_executed), 1)
        self.assertEqual(rpc_executed[0]["device_identifier"], "dev-bath")
        self.assertEqual(res2["reply"], "Bathroom ceiling light is now on.")

    async def test_get_telemetry_all_devices_and_area_resolution(self):
        caps = _apartment_capabilities()
        agent = {
            "id": "agent-1", "name": "QA", "language": "en", "tool_policy": "read_only_telemetry",
            "integrations": {"thingsboard": {"host": "http://tb.test", "api_key": "private"}},
        }

        def resp(data):
            r = MagicMock(status_code=200)
            r.json.return_value = data
            r.raise_for_status = lambda: None
            return r

        async def mock_get(url, **kwargs):
            if "/api/tenant/devices" in url:
                return resp({"data": [
                    {"id": {"id": "dev-bed2"}, "name": "Bedroom2"},
                    {"id": {"id": "dev-living"}, "name": "Living Room"},
                ], "hasNext": False})
            if "/dev-bed2/values/timeseries" in url:
                return resp({"temperature": [{"ts": 1, "value": "32.2"}]})
            if "/dev-living/values/timeseries" in url:
                return resp({"kitchenLightOn": [{"ts": 1, "value": "true"}]})
            return resp({})

        model_replies = [
            {"choices": [{"message": {"role": "assistant", "tool_calls": [{"id": "t1", "function": {"name": "get_telemetry", "arguments": "{}"}}]}}]},
            {"choices": [{"message": {"role": "assistant", "tool_calls": [{"id": "t2", "function": {"name": "get_telemetry", "arguments": '{"device_name":"kitchen.ceiling_light"}'}}]}}]},
            {"choices": [{"message": {"content": "Bedroom2 is 32.2C and kitchen light is on."}}]},
        ]
        client = AsyncMock()
        client.get.side_effect = mock_get
        client.post.side_effect = [resp(d) for d in model_replies]
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=client)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {"PLATFORM_DATA_DIR": tmp}), \
                patch("httpx.AsyncClient", return_value=ctx):
            _seed_capabilities_db(tmp, "http://tb.test", "private", "agent-1", caps)
            res = await bridge.run_agent_chat(agent, bridge.AgentChatRequest(message="Check kitchen light and bedroom 2 temp"))

        self.assertEqual(len(res["tool_calls"]), 2)
        all_tel = json.loads(res["tool_calls"][0]["result"])
        self.assertEqual(all_tel["devices"][0]["telemetry"]["temperature"], "32.2")
        kitchen_tel = json.loads(res["tool_calls"][1]["result"])
        self.assertEqual(kitchen_tel["device"], "Living Room")
        # Read-only policy must not expose control_targets or execute_device_action
        tools_sent = [t["function"]["name"] for t in client.post.call_args_list[0].kwargs["json"]["tools"]]
        self.assertNotIn("control_targets", tools_sent)
        self.assertNotIn("execute_device_action", tools_sent)

    @unittest.skipUnless(importlib.util.find_spec("jsonschema"), "requires jsonschema")
    async def test_scoped_registry_refreshes_once_per_batch_with_real_registry(self):
        dev_a = "11111111-2222-3333-4444-555555555551"
        dev_b = "11111111-2222-3333-4444-555555555552"
        caps_a = {"methods": {"setPower": {"params": {"type": "object", "properties": {"state": {"type": "boolean"}}, "required": ["state"]}}}}
        caps_b = {"methods": {"setPower": {"params": {"type": "object", "properties": {"state": {"type": "boolean"}}, "required": ["state"]}}}}
        device_list_calls = 0

        def resp(data, status=200):
            r = MagicMock(status_code=status, content=json.dumps(data).encode(), text=json.dumps(data))
            r.json.return_value = data
            r.raise_for_status = lambda: None
            return r

        async def mock_get(url, **kwargs):
            nonlocal device_list_calls
            if "/api/tenant/devices" in url:
                device_list_calls += 1
                return resp({"data": [
                    {"id": {"id": dev_a}, "name": "Simulated Tasmota A", "type": "default"},
                    {"id": {"id": dev_b}, "name": "Simulated Tasmota B", "type": "default"},
                ], "hasNext": False})
            if f"/{dev_a}/values/attributes/CLIENT_SCOPE" in url:
                return resp([{"key": "rpcCapabilities", "value": caps_a}])
            if f"/{dev_b}/values/attributes/CLIENT_SCOPE" in url:
                return resp([{"key": "rpcCapabilities", "value": caps_b}])
            if "/values/attributes/" in url:
                return resp([])
            if "/api/tenant/dashboards" in url or "/api/ruleChains" in url:
                return resp({"data": [], "hasNext": False})
            return resp({})

        http = AsyncMock()
        http.get.side_effect = mock_get
        http.post.return_value = resp({"POWER": "ON"}, 200)
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=http)
        ctx.__aexit__ = AsyncMock(return_value=False)
        config = {"host": "http://tb.test", "api_key": "key-a"}

        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {"PLATFORM_DATA_DIR": tmp}), \
                patch("httpx.AsyncClient", return_value=ctx):
            async with api_tools.scoped_registry(config, "agent-batch"):
                self.assertEqual(device_list_calls, 1)
                err1 = await api_tools.authorize_rpc(config, "agent-batch", dev_a, "setPower", {"state": True})
                err2 = await api_tools.authorize_rpc(config, "agent-batch", dev_b, "setPower", {"state": False})
                err3 = await api_tools.authorize_rpc(config, "agent-batch", dev_a, "badMethod", {})
                self.assertIsNone(err1)
                self.assertIsNone(err2)
                self.assertIn("RPC not sent", err3)
                self.assertEqual(device_list_calls, 1)

    def test_evaluate_telemetry_condition_and_group_selector_expansion(self):
        catalog = pipeline.compile_action_catalog(_apartment_capabilities())

        # Group selector expands cleanly for plural/scene prompts and blocks on non-plural prompts
        ids_lights, err_lights = pipeline._expand_selector("all_lights", catalog, "Turn off all lights")
        self.assertIsNone(err_lights)
        self.assertEqual(len(ids_lights), 5)

        ids_all, err_all = pipeline._expand_selector("all", catalog, "I'm leaving home, turn everything off")
        self.assertIsNone(err_all)
        self.assertEqual(len(ids_all), 8)

        ids_bad, err_bad = pipeline._expand_selector("all", catalog, "Turn off bed")
        self.assertIsNone(ids_bad)
        self.assertEqual(err_bad["error_code"], "ambiguous_target")

        # Numeric condition gate (TRUE vs FALSE in EN & VI, plus else-branch handling)
        t_vals = {"temperature": 32.2}
        t_by_dev = {"bedroom 2": {"temperature": 32.2}}
        self.assertIsNone(pipeline.evaluate_telemetry_condition(
            "Check the temperature of Bedroom 2; if it is above 20 degrees, turn on the Bedroom 2 fan",
            t_vals, ["on"], t_by_dev,
        ))
        cond_false = pipeline.evaluate_telemetry_condition(
            "Check the temperature of Bedroom 2; if it is above 45 degrees, turn on the Bedroom 2 fan, otherwise leave it off",
            t_vals, ["on"], t_by_dev,
        )
        self.assertIsNotNone(cond_false)
        self.assertEqual(cond_false["error_code"], "condition_not_met")
        cond_vi = pipeline.evaluate_telemetry_condition(
            "kiểm tra nhiệt độ sensor1, nếu trên 35 độ thì bật Simulated Tasmota B, còn không thì giữ nguyên",
            t_vals, ["on"],
        )
        self.assertIsNotNone(cond_vi)
        self.assertEqual(cond_vi["error_code"], "condition_not_met")
        self.assertIsNone(pipeline.evaluate_telemetry_condition(
            "if temperature > 40 turn on A, else turn off A",
            t_vals, ["off"],
        ))
        self.assertIsNone(pipeline.evaluate_telemetry_condition("Turn on the bathroom light", t_vals, ["on"]))

    async def test_flat_control_schema_group_selectors_condition_gate_and_now_off_nudge(self):
        caps = _apartment_capabilities()
        agent = {
            "id": "agent-1", "name": "QA", "language": "en", "tool_policy": "full_control",
            "integrations": {"thingsboard": {"host": "http://tb.test", "api_key": "private"}},
        }

        @asynccontextmanager
        async def fake_scoped(cfg, pid):
            reg = MagicMock()
            reg.fresh = True
            reg.list.return_value = caps
            yield reg

        rpc_calls = []

        async def fake_execute(client, cfg, name, args, read_only=False, profile_id=None):
            if name == "execute_device_action":
                rpc_calls.append(args)
                return {"status": "success", "success": True, "delivery": "submitted"}
            if name == "get_telemetry":
                return {
                    "status": "success", "success": True, "device": "Bedroom2",
                    "telemetry": {"temperature": [{"ts": 1, "value": "32.2"}]},
                }
            return {"status": "error", "success": False}

        def resp(data):
            r = MagicMock(status_code=200)
            r.json.return_value = data
            r.raise_for_status = lambda: None
            return r

        # 1. Flat turn_off=["all_lights"] turns off all 5 lights, plus verifies "is now off" triggers nudge on pronoun follow-up.
        replies1 = [
            {"choices": [{"message": {"role": "assistant", "tool_calls": [{
                "id": "b1", "function": {"name": "control_targets", "arguments": json.dumps({"turn_off": ["all_lights"]})},
            }]}}]},
            {"choices": [{"message": {"content": "All 5 lights are now off."}}]},
        ]
        c1 = AsyncMock()
        c1.post.side_effect = [resp(d) for d in replies1]
        ctx1 = MagicMock()
        ctx1.__aenter__ = AsyncMock(return_value=c1)
        ctx1.__aexit__ = AsyncMock(return_value=False)

        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"PLATFORM_DATA_DIR": tmp}), \
                patch("httpx.AsyncClient", return_value=ctx1), \
                patch.object(api_tools, "scoped_registry", side_effect=fake_scoped), \
                patch.object(api_tools, "execute", side_effect=fake_execute):
            _seed_capabilities_db(tmp, "http://tb.test", "private", "agent-1", caps)
            res1 = await bridge.run_agent_chat(agent, bridge.AgentChatRequest(message="Turn off all lights"))

        self.assertEqual(len(rpc_calls), 5)
        self.assertEqual(res1["reply"], "All 5 lights are now off.")

        # 2. Pronoun follow-up where LLM emits "The bathroom ceiling light is now off." without calling tool -> nudged -> calls turn_off!
        rpc_calls.clear()
        replies2 = [
            {"choices": [{"message": {"content": "The bathroom ceiling light is now off."}}]},
            {"choices": [{"message": {"role": "assistant", "tool_calls": [{
                "id": "p1", "function": {"name": "control_targets", "arguments": json.dumps({"turn_off": ["bathroom.ceiling_light"]})},
            }]}}]},
            {"choices": [{"message": {"content": "Bathroom ceiling light has been turned off."}}]},
        ]
        c2 = AsyncMock()
        c2.post.side_effect = [resp(d) for d in replies2]
        ctx2 = MagicMock()
        ctx2.__aenter__ = AsyncMock(return_value=c2)
        ctx2.__aexit__ = AsyncMock(return_value=False)

        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"PLATFORM_DATA_DIR": tmp}), \
                patch("httpx.AsyncClient", return_value=ctx2), \
                patch.object(api_tools, "scoped_registry", side_effect=fake_scoped), \
                patch.object(api_tools, "execute", side_effect=fake_execute):
            _seed_capabilities_db(tmp, "http://tb.test", "private", "agent-1", caps)
            res2 = await bridge.run_agent_chat(agent, bridge.AgentChatRequest(
                message="Now turn it off",
                history=[{"role": "user", "content": "Turn on bathroom light"}, {"role": "assistant", "content": "Turned on."}],
            ))

        self.assertEqual(len(rpc_calls), 1)
        self.assertEqual(rpc_calls[0]["device_identifier"], "dev-bath")

        # 3. False conditional: LLM calls get_telemetry (32.2) then falsely calls control_targets -> condition gate blocks RPC!
        rpc_calls.clear()
        replies3 = [
            {"choices": [{"message": {"role": "assistant", "tool_calls": [{
                "id": "t1", "function": {"name": "get_telemetry", "arguments": '{"device_name":"Bedroom2"}'},
            }]}}]},
            {"choices": [{"message": {"role": "assistant", "tool_calls": [{
                "id": "bad_cond", "function": {"name": "control_targets", "arguments": json.dumps({"turn_on": ["bedroom_2.fan"]})},
            }]}}]},
            {"choices": [{"message": {"content": "Temperature is 32.2C (below 45C), so the fan stays off."}}]},
        ]
        c3 = AsyncMock()
        c3.post.side_effect = [resp(d) for d in replies3]
        ctx3 = MagicMock()
        ctx3.__aenter__ = AsyncMock(return_value=c3)
        ctx3.__aexit__ = AsyncMock(return_value=False)

        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"PLATFORM_DATA_DIR": tmp}), \
                patch("httpx.AsyncClient", return_value=ctx3), \
                patch.object(api_tools, "scoped_registry", side_effect=fake_scoped), \
                patch.object(api_tools, "execute", side_effect=fake_execute):
            _seed_capabilities_db(tmp, "http://tb.test", "private", "agent-1", caps)
            res3 = await bridge.run_agent_chat(agent, bridge.AgentChatRequest(
                message="Check Bedroom 2 temperature; if above 45 degrees turn on Bedroom 2 fan, otherwise leave it off"
            ))

        self.assertEqual(rpc_calls, [])
        self.assertEqual(json.loads(res3["tool_calls"][1]["result"])["error_code"], "condition_not_met")
        self.assertIn("32.2", res3["reply"])


if __name__ == "__main__":
    unittest.main()
