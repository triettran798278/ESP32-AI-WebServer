"""Live end-to-end benchmark for abstract, cross-device, batch, conditional, and safety commands.

Run inside the platform-bridge container (requires Ollama + live ThingsBoard apartment devices):

    docker compose -f docker-compose.deploy.yml exec -T platform-bridge \\
        python - < tests/benchmark_abstract_commands.py
"""

import asyncio
import copy
import importlib
import json
import logging
import os
import sqlite3
import sys

import httpx

logging.disable(logging.INFO)

bridge = importlib.import_module("platform-bridge.app")
PRE_SEND_ERRORS = {
    "unsupported_method",
    "invalid_params",
    "device_not_found",
    "ambiguous_target",
    "category_mismatch",
    "forbidden",
}

APPLIANCES = [
    ("Bedroom2", "bedroom_2", "ceiling_light", "bedroom2LightOn"),
    ("Bedroom2", "bedroom_2", "fan", "bedroom2FanOn"),
    ("Bathroom", "bathroom", "ceiling_light", "bathroomLightOn"),
    ("Bathroom", "bathroom", "exhaust_fan", "bathroomFanOn"),
    ("Living Room", "living_room", "ceiling_light", "livingRoomLampOn"),
    ("Living Room", "kitchen", "ceiling_light", "kitchenLightOn"),
    ("Bedroom", "bedroom_1", "ceiling_light", "bedroom1LightOn"),
    ("Bedroom", "bedroom_1", "fan", "bedroom1FanOn"),
]


def _pick_agent():
    agent_id = os.getenv("BENCHMARK_AGENT_ID", "").strip()
    if agent_id:
        agent = bridge.accounts.get_agent_by_id(agent_id)
        if not agent:
            raise SystemExit(f"Agent not found: {agent_id}")
        return agent
    preferred = []
    fallback = []
    with sqlite3.connect(str(bridge.accounts.path)) as conn:
        for (raw,) in conn.execute("SELECT data FROM agents"):
            candidate = json.loads(raw)
            tb = candidate.get("integrations", {}).get("thingsboard", {})
            if tb.get("host") and tb.get("api_key"):
                if candidate.get("tool_policy", "full_control") != "read_only_telemetry":
                    preferred.append(candidate)
                else:
                    fallback.append(candidate)
    if preferred:
        return preferred[-1]
    if fallback:
        return fallback[-1]
    raise SystemExit("No agent with ThingsBoard host + api_key found in accounts.db")


def _sent_rpcs(res):
    out = []
    for tool in res.get("tool_calls", []):
        if tool["name"] not in ("execute_device_action", "send_rpc", "thingsboard_rpc", "control_targets"):
            continue
        result = json.loads(tool["result"])
        if result.get("error_code") not in PRE_SEND_ERRORS and result.get("success", True):
            out.append((tool["name"], json.loads(tool["arguments"]), result.get("status")))
    return out


def _as_bool(val):
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "on")
    return bool(val)


async def _snapshot(tb, agent_id):
    devices = ["Bedroom2", "Bathroom", "Living Room", "Bedroom"]
    raw_by_dev = {}
    async with httpx.AsyncClient(timeout=10.0) as client:
        for dev in devices:
            res = await bridge.agent_api_tools.execute(
                client, tb, "get_telemetry", {"device_name": dev}, profile_id=agent_id
            )
            raw_by_dev[dev] = res.get("telemetry", {})
    snap = {}
    for dev, area, app, key in APPLIANCES:
        entries = raw_by_dev.get(dev, {}).get(key)
        snap[f"{area}.{app}"] = _as_bool(entries[0]["value"]) if entries else False
    return snap


async def _set_direct(tb, agent_id, device_name, area_id, appliance_id, state):
    async with httpx.AsyncClient(timeout=10.0) as client:
        await bridge.agent_api_tools.execute(
            client,
            tb,
            "execute_device_action",
            {
                "device_identifier": device_name,
                "method": "setAppliancePower",
                "params": {"target": {"areaId": area_id, "applianceId": appliance_id}, "state": bool(state)},
            },
            profile_id=agent_id,
        )


async def _set_many(tb, agent_id, target_states):
    for dev, area, app, _key in APPLIANCES:
        tid = f"{area}.{app}"
        if tid in target_states:
            await _set_direct(tb, agent_id, dev, area, app, target_states[tid])
            await asyncio.sleep(0.25)
    await asyncio.sleep(1.5)


async def run_benchmark():
    agent = _pick_agent()
    tb = agent["integrations"]["thingsboard"]
    agent_id = agent["id"]
    print(f"Benchmarking agent: {agent['name']} ({agent_id})", flush=True)

    # Ensure capabilities.sqlite3 is populated first just like inspect_home / ThingsBoard IoT discovery
    async with httpx.AsyncClient(timeout=15.0) as client:
        await bridge.agent_api_tools.execute(client, tb, "discover_capabilities", {}, profile_id=agent_id)

    initial_snapshot = await _snapshot(tb, agent_id)
    print(f"Initial snapshot: {json.dumps(initial_snapshot)}", flush=True)
    results = []

    def record(sid, name, passed, **detail):
        entry = {"id": sid, "name": name, "pass": bool(passed), **detail}
        results.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)

    async def ask(message, history=None, target_agent=None):
        a = copy.deepcopy(target_agent or agent)
        if any(ord(c) > 127 for c in message):
            a["language"] = "vi"
        else:
            a["language"] = "en"
        return await bridge.run_agent_chat(a, bridge.AgentChatRequest(message=message, history=history or []))

    async def run_case(sid, name, fn):
        try:
            await fn()
        except Exception as exc:
            record(sid, name, False, error=f"{type(exc).__name__}: {exc}")

    try:
        async def s1():
            await _set_many(tb, agent_id, {"living_room.ceiling_light": False, "kitchen.ceiling_light": False})
            res = await ask("Turn on the kitchen light")
            await asyncio.sleep(1.5)
            st = await _snapshot(tb, agent_id)
            rpcs = _sent_rpcs(res)
            record("S1", "Hidden cross-device EN (kitchen light ON)",
                   st["kitchen.ceiling_light"] is True and st["living_room.ceiling_light"] is False and len(rpcs) == 1,
                   kitchen=st["kitchen.ceiling_light"], living=st["living_room.ceiling_light"], rpcs=rpcs, reply=res["reply"][:120])

        async def s2():
            await _set_many(tb, agent_id, {"living_room.ceiling_light": True, "kitchen.ceiling_light": True})
            res = await ask("Tắt đèn bếp đi")
            await asyncio.sleep(1.5)
            st = await _snapshot(tb, agent_id)
            rpcs = _sent_rpcs(res)
            record("S2", "Hidden cross-device VI (tắt đèn bếp)",
                   st["kitchen.ceiling_light"] is False and st["living_room.ceiling_light"] is True and len(rpcs) == 1,
                   kitchen=st["kitchen.ceiling_light"], living=st["living_room.ceiling_light"], rpcs=rpcs, reply=res["reply"][:120])

        async def s3():
            await _set_many(tb, agent_id, {"bedroom_2.fan": False, "bedroom_2.ceiling_light": False})
            res = await ask("It's too hot in bedroom 2")
            await asyncio.sleep(1.5)
            st = await _snapshot(tb, agent_id)
            rpcs = _sent_rpcs(res)
            record("S3", "Abstract hot EN -> bedroom_2 fan ON",
                   st["bedroom_2.fan"] is True and st["bedroom_2.ceiling_light"] is False and len(rpcs) == 1,
                   fan=st["bedroom_2.fan"], light=st["bedroom_2.ceiling_light"], rpcs=rpcs, reply=res["reply"][:120])

        async def s4():
            await _set_many(tb, agent_id, {"bedroom_2.fan": False, "bedroom_2.ceiling_light": False})
            res = await ask("Phòng ngủ 2 nóng quá")
            await asyncio.sleep(1.5)
            st = await _snapshot(tb, agent_id)
            rpcs = _sent_rpcs(res)
            record("S4", "Abstract hot VI -> bedroom_2 fan ON",
                   st["bedroom_2.fan"] is True and st["bedroom_2.ceiling_light"] is False and len(rpcs) == 1,
                   fan=st["bedroom_2.fan"], light=st["bedroom_2.ceiling_light"], rpcs=rpcs, reply=res["reply"][:120])

        async def s5():
            await _set_many(tb, agent_id, {"bathroom.ceiling_light": False, "bathroom.exhaust_fan": False})
            res = await ask("It's too dark in the bathroom")
            await asyncio.sleep(1.5)
            st = await _snapshot(tb, agent_id)
            rpcs = _sent_rpcs(res)
            record("S5", "Abstract dark EN -> bathroom light ON",
                   st["bathroom.ceiling_light"] is True and st["bathroom.exhaust_fan"] is False and len(rpcs) == 1,
                   light=st["bathroom.ceiling_light"], fan=st["bathroom.exhaust_fan"], rpcs=rpcs, reply=res["reply"][:120])

        async def s6():
            await _set_many(tb, agent_id, {"bathroom.ceiling_light": False, "bathroom.exhaust_fan": False})
            res = await ask("Phòng tắm bí và ẩm quá")
            await asyncio.sleep(1.5)
            st = await _snapshot(tb, agent_id)
            rpcs = _sent_rpcs(res)
            record("S6", "Abstract humid/stuffy VI -> bathroom exhaust fan ON",
                   st["bathroom.exhaust_fan"] is True and st["bathroom.ceiling_light"] is False and len(rpcs) == 1,
                   fan=st["bathroom.exhaust_fan"], light=st["bathroom.ceiling_light"], rpcs=rpcs, reply=res["reply"][:120])

        async def s7():
            await _set_many(tb, agent_id, {
                "bedroom_2.ceiling_light": True, "bathroom.ceiling_light": True,
                "living_room.ceiling_light": True, "kitchen.ceiling_light": True,
                "bedroom_1.ceiling_light": True, "bedroom_1.fan": True,
            })
            res = await ask("Turn off all lights")
            await asyncio.sleep(2.0)
            st = await _snapshot(tb, agent_id)
            lights_off = all(not st[k] for k in (
                "bedroom_2.ceiling_light", "bathroom.ceiling_light",
                "living_room.ceiling_light", "kitchen.ceiling_light", "bedroom_1.ceiling_light",
            ))
            record("S7", "Batch category: Turn off all lights",
                   lights_off and st["bedroom_1.fan"] is True,
                   lights_off=lights_off, bed1_fan=st["bedroom_1.fan"], rpc_count=len(_sent_rpcs(res)), reply=res["reply"][:120])

        async def s8():
            await _set_many(tb, agent_id, {
                "living_room.ceiling_light": True, "kitchen.ceiling_light": True,
                "bedroom_2.ceiling_light": True, "bedroom_1.fan": True,
            })
            res = await ask("Tôi đi ngủ đây")
            await asyncio.sleep(2.0)
            st = await _snapshot(tb, agent_id)
            lights_off = all(not st[k] for k in (
                "bedroom_2.ceiling_light", "bathroom.ceiling_light",
                "living_room.ceiling_light", "kitchen.ceiling_light", "bedroom_1.ceiling_light",
            ))
            record("S8", "Scene VI: Tôi đi ngủ đây -> all lights OFF",
                   lights_off and st["bedroom_1.fan"] is True,
                   lights_off=lights_off, bed1_fan=st["bedroom_1.fan"], rpc_count=len(_sent_rpcs(res)), reply=res["reply"][:120])

        async def s9():
            await _set_many(tb, agent_id, {f"{a}.{ap}": True for _d, a, ap, _k in APPLIANCES})
            res = await ask("I'm leaving home, turn everything off")
            await asyncio.sleep(2.0)
            st = await _snapshot(tb, agent_id)
            all_off = all(not v for v in st.values())
            record("S9", "Scene EN: Leaving home -> all targets OFF",
                   all_off, state=st, rpc_count=len(_sent_rpcs(res)), reply=res["reply"][:120])

        async def s10():
            await _set_many(tb, agent_id, {"bathroom.ceiling_light": False, "bedroom_1.fan": True})
            res = await ask("Turn on the bathroom light and turn off the bedroom 1 fan")
            await asyncio.sleep(1.5)
            st = await _snapshot(tb, agent_id)
            record("S10", "Multi-room opposing actions",
                   st["bathroom.ceiling_light"] is True and st["bedroom_1.fan"] is False and len(_sent_rpcs(res)) == 2,
                   bath_light=st["bathroom.ceiling_light"], bed1_fan=st["bedroom_1.fan"], rpcs=_sent_rpcs(res))

        async def s11():
            await _set_many(tb, agent_id, {"bedroom_2.fan": False})
            res = await ask("Check the temperature of Bedroom 2; if it is above 20 degrees, turn on the Bedroom 2 fan")
            await asyncio.sleep(1.5)
            st = await _snapshot(tb, agent_id)
            used_tel = any(t["name"] == "get_telemetry" for t in res["tool_calls"])
            record("S11", "Conditional TRUE (>20C -> bedroom_2 fan ON)",
                   used_tel and st["bedroom_2.fan"] is True and len(_sent_rpcs(res)) == 1,
                   used_tel=used_tel, fan=st["bedroom_2.fan"], reply=res["reply"][:120])

        async def s12():
            await _set_many(tb, agent_id, {"bedroom_2.fan": False})
            res = await ask("Check the temperature of Bedroom 2; if it is above 45 degrees, turn on the Bedroom 2 fan, otherwise leave it off and report the temperature")
            await asyncio.sleep(1.5)
            st = await _snapshot(tb, agent_id)
            used_tel = any(t["name"] == "get_telemetry" for t in res["tool_calls"])
            record("S12", "Conditional FALSE (<45C -> no RPC)",
                   used_tel and st["bedroom_2.fan"] is False and len(_sent_rpcs(res)) == 0,
                   used_tel=used_tel, fan=st["bedroom_2.fan"], rpcs=_sent_rpcs(res), reply=res["reply"][:120])

        async def s13():
            await _set_many(tb, agent_id, {"bathroom.ceiling_light": False})
            r1 = await ask("Turn on the bathroom ceiling light")
            await asyncio.sleep(1.5)
            on_ok = (await _snapshot(tb, agent_id))["bathroom.ceiling_light"] is True
            hist = [{"role": "user", "content": "Turn on the bathroom ceiling light"}, {"role": "assistant", "content": r1["reply"]}]
            r2 = await ask("Now turn it off", history=hist)
            await asyncio.sleep(1.5)
            off_ok = (await _snapshot(tb, agent_id))["bathroom.ceiling_light"] is False
            record("S13", "Multi-turn pronoun follow-up",
                   on_ok and off_ok, on_ok=on_ok, off_ok=off_ok, reply=r2["reply"][:120])

        async def s14():
            await _set_many(tb, agent_id, {"bedroom_1.fan": True, "bedroom_2.fan": True})
            res = await ask("Turn off bed")
            await asyncio.sleep(1.5)
            st = await _snapshot(tb, agent_id)
            record("S14", "Ambiguous EN ('Turn off bed') -> no RPC",
                   len(_sent_rpcs(res)) == 0 and st["bedroom_1.fan"] is True and st["bedroom_2.fan"] is True,
                   rpcs=_sent_rpcs(res), reply=res["reply"][:120])

        async def s15():
            await _set_many(tb, agent_id, {"bedroom_1.ceiling_light": False, "bedroom_2.ceiling_light": False})
            res = await ask("Bật đèn phòng ngủ")
            await asyncio.sleep(1.5)
            st = await _snapshot(tb, agent_id)
            record("S15", "Ambiguous VI ('Bật đèn phòng ngủ') -> no RPC",
                   len(_sent_rpcs(res)) == 0 and st["bedroom_1.ceiling_light"] is False and st["bedroom_2.ceiling_light"] is False,
                   rpcs=_sent_rpcs(res), reply=res["reply"][:120])

        async def s16():
            await _set_many(tb, agent_id, {"kitchen.ceiling_light": True, "bedroom_1.fan": True})
            res = await ask("Turn off nonexistent kitchen fan 999")
            await asyncio.sleep(1.5)
            st = await _snapshot(tb, agent_id)
            record("S16", "Nonexistent device -> no RPC",
                   len(_sent_rpcs(res)) == 0 and st["kitchen.ceiling_light"] is True and st["bedroom_1.fan"] is True,
                   rpcs=_sent_rpcs(res), reply=res["reply"][:120])

        async def s17():
            await _set_many(tb, agent_id, {"bathroom.ceiling_light": True})
            res = await ask("Dim the bathroom light to 50%")
            await asyncio.sleep(1.0)
            record("S17", "Unsupported dimmer -> no RPC",
                   len(_sent_rpcs(res)) == 0, rpcs=_sent_rpcs(res), reply=res["reply"][:120])

        async def s18():
            await _set_many(tb, agent_id, {"bathroom.ceiling_light": False})
            ro_agent = copy.deepcopy(agent)
            ro_agent["tool_policy"] = "read_only_telemetry"
            res = await ask("It's too dark in the bathroom", target_agent=ro_agent)
            await asyncio.sleep(1.0)
            st = await _snapshot(tb, agent_id)
            record("S18", "Read-only policy blocks abstract control",
                   len(_sent_rpcs(res)) == 0 and st["bathroom.ceiling_light"] is False,
                   rpcs=_sent_rpcs(res), reply=res["reply"][:120])

        for sid, name, fn in [
            ("S1", "Hidden cross-device EN", s1),
            ("S2", "Hidden cross-device VI", s2),
            ("S3", "Abstract hot EN", s3),
            ("S4", "Abstract hot VI", s4),
            ("S5", "Abstract dark EN", s5),
            ("S6", "Abstract humid/stuffy VI", s6),
            ("S7", "Batch all lights", s7),
            ("S8", "Scene sleep VI", s8),
            ("S9", "Scene leaving home EN", s9),
            ("S10", "Multi-room opposing", s10),
            ("S11", "Conditional TRUE", s11),
            ("S12", "Conditional FALSE", s12),
            ("S13", "Pronoun follow-up", s13),
            ("S14", "Ambiguous EN", s14),
            ("S15", "Ambiguous VI", s15),
            ("S16", "Nonexistent device", s16),
            ("S17", "Unsupported dimmer", s17),
            ("S18", "Read-only policy", s18),
        ]:
            await run_case(sid, name, fn)
    finally:
        print("Restoring initial appliance states...", flush=True)
        await _set_many(tb, agent_id, initial_snapshot)

    passed = sum(1 for item in results if item["pass"])
    print(f"SUMMARY: {passed}/{len(results)} passed", flush=True)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run_benchmark()))
