"""Multi-stage ThingsBoard tool-calling pipeline for abstract and precise commands."""

import asyncio
from dataclasses import dataclass, field
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
import unicodedata

from . import agent_api_tools

logger = logging.getLogger("platform_bridge.tool_pipeline")

MAX_TOOL_ROUNDS = 6

PRE_SEND_ERRORS = frozenset({
    "unsupported_method",
    "invalid_params",
    "device_not_found",
    "ambiguous_target",
    "category_mismatch",
    "condition_not_met",
    "forbidden",
})

_GETTER_METHOD_RE = re.compile(r"^(?:get|read|fetch|query|list|status|ping|health|info)(?:[A-Z_]|$)", re.IGNORECASE)
_RAW_RELAY_METHOD_RE = re.compile(r"^POWER\d*$", re.IGNORECASE)
_SETTER_PREFIX_RE = re.compile(r"^(?:set|enable|disable|switch|turn|control|update)_?", re.IGNORECASE)
_TOGGLE_PREFIX_RE = re.compile(r"^toggle_?", re.IGNORECASE)

_CATEGORY_HINTS = (
    ("other", ("auto_light", "autolight", "automatic_lighting", "automatic lighting", "tự động")),
    ("light", ("light", "lamp", "bulb", "ceiling_light", "đèn", "chùm", "bóng")),
    ("fan", ("fan", "exhaust", "ventilator", "quạt", "hút")),
    ("lock", ("lock", "door_lock", "khóa")),
    ("switch", ("power", "switch", "relay", "outlet", "plug", "socket", "công tắc", "ổ cắm")),
)

_BILINGUAL_EQUIV = (
    ({"light", "lamp", "ceiling"}, {"den", "bong"}),
    ({"fan", "exhaust"}, {"quat", "hut"}),
    ({"lock"}, {"khoa"}),
    ({"kitchen"}, {"bep"}),
    ({"living", "living_room"}, {"khach"}),
    ({"bathroom", "bath"}, {"tam"}),
    ({"bedroom"}, {"ngu"}),
    ({"hallway", "corridor"}, {"hanh", "lang"}),
    ({"garage"}, {"gara", "xe"}),
    ({"balcony"}, {"ban", "cong"}),
    ({"entrance", "door"}, {"cua"}),
)

_STOPWORDS = frozenset({
    "a", "an", "the", "turn", "switch", "power", "set", "toggle", "on", "off",
    "in", "at", "to", "for", "of", "and", "or", "with", "from", "by", "my",
    "please", "can", "you", "could", "would", "make", "is", "are", "too",
    "very", "so", "this", "that", "it", "here", "there", "all", "every",
    "everything", "both", "light", "lights", "lamp", "lamps", "fan", "fans",
    "lock", "locks", "ceiling", "exhaust", "device", "devices", "appliance",
    "appliances", "relay", "channel", "check", "status", "currently",
    "bat", "tat", "mo", "dong", "ngat", "dao", "trang", "thai", "nguon",
    "den", "quat", "khoa", "hut", "tran", "qua", "nhe", "giup", "toi", "cho",
    "trong", "o", "cua", "cai", "thiet", "bi", "hay", "vui", "long", "di",
    "len", "xuong", "voi", "va", "hoac", "het", "tat", "ca", "phong", "room",
})

_PLURAL_OR_SCENE_RE = re.compile(
    r"\b(?:all|every|everything|both|entire|whole|lights|lamps|fans|locks|switches|devices|rooms"
    r"|sleep|bedtime|good\s*night|night\s*mode|leaving|leave\s+home|going\s+out|away|goodbye|bye)\b"
    r"|(?<!phòng\s)(?<!phong\s)\b(?:tất cả|tat ca|hết|het|toàn bộ|toan bo|cả hai|ca hai"
    r"|đi ngủ|di ngu|ngủ thôi|ngu thoi|ngủ đây|ngu day|chúc ngủ ngon|chuc ngu ngon"
    r"|ra ngoài|ra ngoai|ra khỏi nhà|ra khoi nha|rời nhà|roi nha|vắng nhà|vang nha|cả nhà|ca nha)\b",
    re.IGNORECASE,
)
_PRONOUN_RE = re.compile(
    r"\b(?:it|them|those|same|one)\b"
    r"|\b(?:nó|no|cái đó|cai do|thiết bị đó|thiet bi do|cái này|cai nay|đèn đó|den do|quạt đó|quat do)\b",
    re.IGNORECASE,
)
_CONDITIONAL_OR_FILTER_RE = re.compile(
    r"\b(?:if|when|unless|while|currently|active|running|turned\s+(?:on|off)|hottest|coldest|warmest|humid|highest|lowest)\b"
    r"|\b(?:nếu|khi|đang|bật sẵn|đang bật|đang tắt|nóng nhất|lạnh nhất|ẩm nhất|cao nhất|thấp nhất|nốt)\b",
    re.IGNORECASE,
)
_QUESTION_OR_READ_RE = re.compile(
    r"\?|\b(?:what|which|how|status|check|read|show|list|tell|report|measure|is|are)\b"
    r"|\b(?:là gì|bao nhiêu|như thế nào|kiểm tra|xem|đo|liệt kê|danh sách|hỗ trợ|có những)\b",
    re.IGNORECASE,
)
_CONTROL_REQUEST_RE = re.compile(
    r"^(?!.*\?)(?:(?:(?:hãy|vui lòng)\s+)?(?:bật|tắt|mở|đóng|ngắt|khóa|mở khóa|đảo\s+trạng\s+thái)\b"
    r"|(?!.*\b(?:đang|là gì|bao nhiêu|như thế nào|status|what|which|is|are|check|kiểm tra|xem)\b)"
    r".*(?:\b(?:bật|tắt|ngắt|khóa|mở khóa|đảo trạng thái)\b|\b(?:turn|switch|power)\s+(?:on|off)\b|\b(?:toggle|set\s+power|lock|unlock)\b))",
    re.IGNORECASE,
)
_ABSTRACT_CONTROL_RE = re.compile(
    r"^(?!.*\?)(?!.*\b(?:if|when|nếu|khi|what|which|how|check|status|kiểm tra|xem|bao nhiêu|là gì)\b)"
    r".*(?:\b(?:too\s+(?:hot|warm|dark|humid|stuffy)|it(?:'s|\s+is)\s+(?:hot|warm|dark|humid|stuffy)|going\s+to\s+(?:sleep|bed)|good\s*night|leaving\s+home)\b"
    r"|(?:nóng\s+quá|tối\s+quá|tối\s+thui|tối\s+om|ẩm\s+quá|bí\s+quá|ngộp\s+quá|đi\s+ngủ|ra\s+khỏi\s+nhà|tắt\s+hết|mở\s+đèn))",
    re.IGNORECASE,
)
_DESCRIBED_ACTION_RE = re.compile(
    r"<\s*/?\s*(?:tools?|tool_call)\b"
    r"|`(?:control_targets|inspect_home|get_telemetry|execute_device_action|send_rpc|thingsboard_rpc|list_available_rpc|discover_capabilities)`"
    r"|(?:sẽ|sẽ tiến hành)\s+(?:gọi|gửi|thực hiện|dùng|sử dụng|bật|tắt|điều khiển)\b"
    r"|(?:i will|i'll|we will|we'll|let's|let me)\s+(?:call|send|execute|use|proceed|turn|set|toggle|control)\b",
    re.IGNORECASE,
)
_UNVERIFIED_ACTION_RE = re.compile(
    r"\b(?:has|have)\s+been\s+(?:\w+\s+)?(?:sent|submitted|executed|dispatched|triggered|set|updated|changed|turned\s+(?:on|off)|switched\s+(?:on|off)|powered\s+(?:on|off)|toggled|locked|unlocked|applied)\b"
    r"|\b(?:is|are)\s+now\s+(?:on|off|turned\s+(?:on|off)|switched\s+(?:on|off)|powered\s+(?:on|off)|locked|unlocked)\b"
    r"|\b(?:device|relay|switch|light|lamp|fan|lock|appliance)\s+has\s+(?:\w+\s+)?(?:received|processed|executed|acknowledged|been\s+turned)\b"
    r"|\b(?:i|we)\s+(?:have\s+)?(?:\w+\s+)?(?:sent|submitted|executed|set|turned\s+(?:on|off)|switched\s+(?:on|off)|powered\s+(?:on|off)|toggled|locked|unlocked)\b.*\b(?:command|rpc|power|device|relay|switch|tasmota|light|lamp|fan|lock|appliance|room)\b"
    r"|\bđã\s+(?:được\s+)?(?:bật|tắt|đặt|cập\s+nhật|gửi|gọi|thực\s+hiện|chuyển|kích\s+hoạt|điều\s+khiển|khóa|mở khóa)\b",
    re.IGNORECASE,
)
_WAITING_RE = re.compile(
    r"please wait|hold on|one moment|(?:i will|i'll) (?:get|fetch|retrieve|check)"
    r"|(?:hãy|vui lòng) (?:đợi|chờ)|đợi một chút|(?:đang|sẽ) (?:lấy|tìm|truy xuất|kiểm tra)",
    re.IGNORECASE,
)
_NOT_FOUND_REPLY_RE = re.compile(
    r"\b(?:not found|cannot find|could not find|does not exist|no (?:such )?device|ambiguous|specify|clarify|which\s+(?:device|one|room|light|fan|target|appliance)|please provide|cannot|unable|unsupported)\b"
    r"|\b(?:không tìm thấy|không có thiết bị|không tồn tại|không hỗ trợ|mơ hồ|chọn|cụ thể|thiết bị nào|phòng nào|cái nào|muốn\s+(?:bật|tắt)\s+(?:đèn|quạt|thiết bị|phòng)\s+nào)\b",
    re.IGNORECASE,
)


@dataclass
class ActionTarget:
    """Single atomic controllable endpoint compiled from a ThingsBoard capability schema."""

    target_id: str
    device_id: str
    device_name: str
    area: str
    appliance: str
    category: str
    label: str
    availability: str
    actions: Dict[str, Tuple[str, Any]] = field(default_factory=dict)
    aliases: Tuple[str, ...] = ()


@dataclass
class ActionCatalog:
    """Compiled view of controllable targets, custom RPC methods, and devices."""

    targets: List[ActionTarget] = field(default_factory=list)
    custom_methods: List[Dict[str, Any]] = field(default_factory=list)
    devices: List[Dict[str, Any]] = field(default_factory=list)
    _by_id: Dict[str, ActionTarget] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._by_id = {target.target_id: target for target in self.targets}

    def get(self, target_id: str) -> Optional[ActionTarget]:
        return self._by_id.get(target_id)


def _strip_accents(text: str) -> str:
    text = (text or "").replace("đ", "d").replace("Đ", "D")
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))


def _slug(text: str) -> str:
    clean = _strip_accents(text)
    clean = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", clean)
    clean = re.sub(r"([A-Za-z])([0-9])", r"\1_\2", clean)
    return re.sub(r"[^a-zA-Z0-9]+", "_", clean).strip("_").lower()


def _tokens(text: str) -> List[str]:
    return [tok for tok in re.split(r"[^a-z0-9]+", _strip_accents(text).lower()) if tok]


def _infer_category(text: str) -> str:
    lower = (text or "").lower()
    slug = _slug(text)
    for category, words in _CATEGORY_HINTS:
        if any(word in lower or word in slug for word in words):
            return category
    return "other"


def _infer_user_categories(user_text: str) -> set:
    """Infer explicit or environmental appliance categories from user phrasing."""
    raw = (user_text or "").lower()
    cats = set()
    if re.search(r"\b(?:lights?|lamps?|bulbs?|dark|dim|bright)\b|đèn|tối\s*(?:quá|thui|om|mù)?|sáng\s+lên", raw):
        cats.add("light")
    if re.search(r"\b(?:fans?|exhaust|ventilator|hot|warm|humid|stuffy)\b|quạt|hút|nóng|ẩm|bí|ngộp", raw):
        cats.add("fan")
    if re.search(r"\b(?:locks?|unlock|locked)\b|khóa", raw):
        cats.add("lock")
    return cats


def _humanize_label(area: str, appliance: str, extra: str = "") -> str:
    area_title = area.replace("_", " ").title()
    app_title = appliance.replace("_", " ").title()
    base = f"{area_title} {app_title}".strip() if area_title != app_title else area_title
    return f"{base} ({extra})" if extra and extra.lower() not in base.lower() else base


def _extract_const(schema: Any) -> Tuple[bool, Any]:
    if not isinstance(schema, dict):
        return False, None
    if "const" in schema:
        return True, schema["const"]
    enum = schema.get("enum")
    if isinstance(enum, list) and len(enum) == 1:
        return True, enum[0]
    return False, None


def _match_sibling_relay(target: ActionTarget, relay_items: List[Dict[str, Any]]) -> str:
    """Pair a raw POWER relay description like '(Đèn bếp)' to its matching semantic target."""
    if not relay_items:
        return ""
    target_id_tokens = set(_tokens(f"{target.area} {target.appliance}"))
    best_score = 0
    best_label = ""
    tied = False
    for relay in relay_items:
        desc = (relay.get("description") or "").strip()
        if not desc:
            continue
        paren = re.search(r"\(([^()]+)\)\s*$", desc)
        label_text = paren.group(1).strip() if paren else desc
        relay_cat = _infer_category(label_text)
        relay_tokens = set(_tokens(label_text))
        score = 0
        if relay_cat != "other":
            score += 3 if relay_cat == target.category else -3
        score += 2 * len(target_id_tokens & relay_tokens)
        for left, right in _BILINGUAL_EQUIV:
            if (target_id_tokens & left and relay_tokens & right) or (target_id_tokens & right and relay_tokens & left):
                score += 2
        if score > best_score:
            best_score = score
            best_label = label_text
            tied = False
        elif score == best_score and score > 0:
            tied = True
    return best_label if best_score > 0 and not tied else ""


def _compile_discriminated_method(
    item: Dict[str, Any],
    sibling_relays: List[Dict[str, Any]],
) -> Optional[List[ActionTarget]]:
    schema = item.get("parameter_schema")
    if not isinstance(schema, dict) or schema.get("type") != "object":
        return None
    props = schema.get("properties")
    if not isinstance(props, dict) or len(props) < 2:
        return None

    bool_keys = [k for k, v in props.items() if isinstance(v, dict) and v.get("type") == "boolean"]
    if len(bool_keys) != 1:
        return None
    bool_key = bool_keys[0]
    other_keys = [k for k in props if k != bool_key]
    if len(other_keys) != 1:
        return None
    disc_key = other_keys[0]
    disc_schema = props[disc_key]
    if not isinstance(disc_schema, dict):
        return None

    branches: List[Tuple[str, str, Any]] = []
    dev_name = item.get("device_name") or item.get("device_id") or "device"
    if isinstance(disc_schema.get("oneOf") or disc_schema.get("anyOf"), list):
        for branch in disc_schema.get("oneOf") or disc_schema.get("anyOf"):
            if not isinstance(branch, dict) or branch.get("type") != "object":
                continue
            b_props = branch.get("properties")
            if not isinstance(b_props, dict) or not b_props:
                continue
            const_map: Dict[str, Any] = {}
            for k, v in b_props.items():
                ok, val = _extract_const(v)
                if ok:
                    const_map[k] = val
            if len(const_map) != len(b_props):
                continue
            area = str(const_map.get("areaId") or const_map.get("area") or const_map.get("room") or "")
            app = str(const_map.get("applianceId") or const_map.get("appliance") or const_map.get("target") or "")
            if not area or not app:
                vals = [str(v) for v in const_map.values()]
                area = area or (_slug(vals[0]) if len(vals) >= 2 else _slug(dev_name))
                app = app or (_slug(vals[1]) if len(vals) >= 2 else _slug(vals[0]))
            branches.append((_slug(area), _slug(app), const_map))
    elif disc_schema.get("type") == "string" and isinstance(disc_schema.get("enum"), list) and disc_schema["enum"]:
        for val in disc_schema["enum"]:
            branches.append((_slug(dev_name), _slug(str(val)), str(val)))
    else:
        return None

    if not branches:
        return None

    device_id = item["device_id"]
    availability = item.get("availability", "unknown")
    method = item["method"]
    targets: List[ActionTarget] = []
    for area, appliance, disc_val in branches:
        target_id = f"{area}.{appliance}"
        category = _infer_category(f"{appliance} {method}")
        prelim = ActionTarget(
            target_id=target_id,
            device_id=device_id,
            device_name=dev_name,
            area=area,
            appliance=appliance,
            category=category,
            label="",
            availability=availability,
            actions={
                "on": (method, {disc_key: disc_val, bool_key: True}),
                "off": (method, {disc_key: disc_val, bool_key: False}),
            },
        )
        extra = _match_sibling_relay(prelim, sibling_relays)
        if extra:
            category = _infer_category(f"{appliance} {extra}")
            prelim.category = category
        prelim.label = _humanize_label(area, appliance, extra)
        aliases = [
            target_id,
            f"{area} {appliance}",
            f"{_slug(dev_name)} {appliance}",
            _slug(dev_name.replace(" ", "")) + f" {appliance}",
            _humanize_label(area, appliance),
        ]
        if extra:
            aliases.append(extra)
        prelim.aliases = tuple(dict.fromkeys(a for a in aliases if a))
        targets.append(prelim)
    return targets


def _compile_simple_bool_method(item: Dict[str, Any]) -> Optional[ActionTarget]:
    schema = item.get("parameter_schema")
    if not isinstance(schema, dict) or schema.get("type") != "object":
        return None
    props = schema.get("properties")
    if not isinstance(props, dict) or len(props) != 1:
        return None
    bool_key, prop_schema = next(iter(props.items()))
    if not isinstance(prop_schema, dict) or prop_schema.get("type") != "boolean":
        return None
    method = item["method"]
    if _GETTER_METHOD_RE.match(method):
        return None
    dev_name = item.get("device_name") or item.get("device_id") or "device"
    area = _slug(dev_name)
    noun = _slug(_SETTER_PREFIX_RE.sub("", method)) or _slug(method)
    target_id = f"{area}.{noun}"
    category = _infer_category(f"{noun} {item.get('description', '')} {dev_name}")
    aliases = [target_id, f"{area} {noun}", f"{dev_name} {noun}", _slug(dev_name).replace("_", "") + f" {noun}"]
    return ActionTarget(
        target_id=target_id,
        device_id=item["device_id"],
        device_name=dev_name,
        area=area,
        appliance=noun,
        category=category,
        label=_humanize_label(area, noun, item.get("description", "") if category == "other" else ""),
        availability=item.get("availability", "unknown"),
        actions={
            "on": (method, {bool_key: True}),
            "off": (method, {bool_key: False}),
        },
        aliases=tuple(dict.fromkeys(aliases)),
    )


def _compile_primitive_binary(item: Dict[str, Any]) -> Optional[ActionTarget]:
    schema = item.get("parameter_schema")
    method = item["method"]
    if not isinstance(schema, dict) or _GETTER_METHOD_RE.match(method):
        return None
    on_off: Optional[Tuple[Any, Any]] = None
    if schema.get("type") == "boolean":
        on_off = (True, False)
    elif schema.get("type") == "integer" and set(schema.get("enum") or ()) == {0, 1}:
        on_off = (1, 0)
    elif schema.get("type") == "string" and {str(v).upper() for v in (schema.get("enum") or ())} == {"ON", "OFF"}:
        enum_map = {str(v).upper(): v for v in schema["enum"]}
        on_off = (enum_map["ON"], enum_map["OFF"])
    if not on_off:
        return None
    dev_name = item.get("device_name") or item.get("device_id") or "device"
    area = _slug(dev_name)
    desc = (item.get("description") or "").strip()
    paren = re.search(r"\(([^()]+)\)\s*$", desc)
    extra = paren.group(1).strip() if paren else desc
    noun = _slug(_SETTER_PREFIX_RE.sub("", method)) or _slug(method)
    category = _infer_category(f"{noun} {extra} {dev_name}")
    return ActionTarget(
        target_id=f"{area}.{noun}",
        device_id=item["device_id"],
        device_name=dev_name,
        area=area,
        appliance=noun,
        category=category,
        label=_humanize_label(area, noun, extra),
        availability=item.get("availability", "unknown"),
        actions={"on": (method, on_off[0]), "off": (method, on_off[1])},
        aliases=tuple(dict.fromkeys(a for a in (f"{area}.{noun}", f"{area} {noun}", extra) if a)),
    )


def _is_zero_arg_schema(schema: Any) -> bool:
    if schema is None:
        return True
    return isinstance(schema, dict) and schema.get("type") == "object" and not (schema.get("properties") or {})


def compile_action_catalog(capabilities: Sequence[Dict[str, Any]]) -> ActionCatalog:
    """Compile raw ThingsBoard capabilities into atomic controllable targets."""
    by_device: Dict[str, List[Dict[str, Any]]] = {}
    devices_meta: Dict[str, Dict[str, Any]] = {}
    for item in capabilities:
        dev_id = item.get("device_id")
        if not dev_id:
            continue
        devices_meta.setdefault(dev_id, {
            "id": dev_id,
            "name": item.get("device_name") or dev_id,
            "type": item.get("device_type") or "default",
            "availability": item.get("availability", "unknown"),
        })
        if item.get("schema_complete") and item.get("method"):
            by_device.setdefault(dev_id, []).append(item)

    targets: List[ActionTarget] = []
    custom_methods: List[Dict[str, Any]] = []

    for dev_id, items in by_device.items():
        sibling_relays = [it for it in items if _RAW_RELAY_METHOD_RE.match(it["method"])]
        device_targets: List[ActionTarget] = []
        consumed_methods = set()

        for it in items:
            compiled = _compile_discriminated_method(it, sibling_relays)
            if compiled:
                device_targets.extend(compiled)
                consumed_methods.add(it["method"])

        has_semantic_multi = bool(device_targets)
        for it in items:
            method = it["method"]
            if method in consumed_methods:
                continue
            simple = _compile_simple_bool_method(it)
            if simple:
                device_targets.append(simple)
                consumed_methods.add(method)
                continue
            if has_semantic_multi and _RAW_RELAY_METHOD_RE.match(method):
                consumed_methods.add(method)
                continue
            prim = _compile_primitive_binary(it)
            if prim:
                device_targets.append(prim)
                consumed_methods.add(method)

        # Pair zero-arg toggle* methods onto matching targets on the same device.
        for it in items:
            method = it["method"]
            if method in consumed_methods or not _TOGGLE_PREFIX_RE.match(method) or not _is_zero_arg_schema(it.get("parameter_schema")):
                continue
            noun = _slug(_TOGGLE_PREFIX_RE.sub("", method))
            matched_target = next((t for t in device_targets if t.appliance == noun), None)
            if matched_target is None and len(device_targets) == 1:
                matched_target = device_targets[0]
            if matched_target is not None:
                matched_target.actions["toggle"] = (method, {})
            else:
                dev_name = devices_meta[dev_id]["name"]
                area = _slug(dev_name)
                device_targets.append(ActionTarget(
                    target_id=f"{area}.{noun or _slug(method)}",
                    device_id=dev_id,
                    device_name=dev_name,
                    area=area,
                    appliance=noun or _slug(method),
                    category=_infer_category(f"{noun} {it.get('description', '')}"),
                    label=_humanize_label(area, noun or _slug(method)),
                    availability=it.get("availability", "unknown"),
                    actions={"toggle": (method, {})},
                    aliases=(f"{area}.{noun or _slug(method)}", f"{area} {noun or _slug(method)}"),
                ))
            consumed_methods.add(method)

        for it in items:
            method = it["method"]
            if method in consumed_methods:
                continue
            if _GETTER_METHOD_RE.match(method) and _is_zero_arg_schema(it.get("parameter_schema")):
                continue
            custom_methods.append({
                "device_id": dev_id,
                "device_name": devices_meta[dev_id]["name"],
                "method": method,
                "description": it.get("description", ""),
                "parameter_schema": it.get("parameter_schema"),
            })

        targets.extend(device_targets)

    # Guarantee globally unique target_id values across devices.
    seen_ids: Dict[str, int] = {}
    for t in targets:
        count = seen_ids.get(t.target_id, 0) + 1
        seen_ids[t.target_id] = count
        if count > 1:
            t.target_id = f"{t.target_id}_{count}"
            t.aliases = tuple(dict.fromkeys((t.target_id, *t.aliases)))

    return ActionCatalog(
        targets=targets,
        custom_methods=custom_methods,
        devices=list(devices_meta.values()),
    )


def _data_dir() -> Path:
    return Path(os.getenv("PLATFORM_DATA_DIR", "/app/data" if os.path.exists("/app") else "./data"))


def load_cached_catalog(config: Dict[str, Any], profile_id: Optional[str]) -> Optional[ActionCatalog]:
    """Load the previously discovered ActionCatalog from capabilities.sqlite3 with zero HTTP calls."""
    host = (config.get("host") or "").rstrip("/")
    api_key = config.get("api_key") or ""
    if not host or not api_key or not profile_id:
        return None
    db_path = _data_dir() / "capabilities.sqlite3"
    if not db_path.exists():
        return None
    integration_id = hashlib.sha256(
        json.dumps([host, api_key, None, None, None, profile_id]).encode()
    ).hexdigest()
    try:
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        try:
            row = conn.execute(
                "SELECT data FROM capabilities WHERE integration = ?",
                (integration_id,),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        capabilities = json.loads(row[0])
        if not isinstance(capabilities, list):
            return None
        return compile_action_catalog(capabilities)
    except Exception as exc:
        logger.debug("Could not load cached capability catalog: %s", exc)
        return None


def format_catalog_for_prompt(catalog: Optional[ActionCatalog], read_only: bool = False) -> str:
    """Format compiled targets cleanly so small LLMs ground onto exact target_ids."""
    if not catalog or (not catalog.targets and not catalog.devices):
        return ""
    lines = ["Discovered ThingsBoard targets (use exact target_id with control_targets):"]
    if not catalog.targets:
        for dev in catalog.devices:
            lines.append(f"- {dev['name']} (id: {dev['id']}, {dev.get('availability', 'unknown')}): no controllable RPC actions advertised")
    else:
        for t in catalog.targets:
            acts = "read-only" if read_only else ", ".join(t.actions.keys())
            lines.append(f"- {t.target_id} [{t.category}] (device: {t.device_name}, {t.availability}): {t.label} | actions: {acts}")
        if not read_only:
            lines.append("Group shortcuts for control_targets: 'all_lights' (all [light]), 'all_fans' (all [fan]), 'all' (every target).")
    if catalog.custom_methods and not read_only:
        lines.append("Custom RPC methods (use execute_device_action):")
        for cm in catalog.custom_methods:
            lines.append(f"- {cm['device_name']}.{cm['method']}: {cm.get('description', '')} schema={json.dumps(cm.get('parameter_schema'), ensure_ascii=False)}")
    return "\n".join(lines)


def _norm_key(value: str) -> str:
    return re.sub(r"[\s._-]+", " ", _strip_accents(value or "")).strip().lower()


def resolve_catalog_target(catalog: ActionCatalog, raw_id: str) -> Tuple[Optional[ActionTarget], Optional[Dict[str, Any]]]:
    """Resolve a target_id, alias, or unambiguous single-appliance device name."""
    raw = (raw_id or "").strip()
    if not raw:
        return None, {
            "status": "error", "success": False, "error_code": "device_not_found",
            "message": "Target identifier is required.",
            "available_targets": [t.target_id for t in catalog.targets],
        }

    exact = catalog.get(raw)
    if exact:
        return exact, None

    norm = _norm_key(raw)
    norm_matches = [t for t in catalog.targets if _norm_key(t.target_id) == norm]
    if len(norm_matches) == 1:
        return norm_matches[0], None

    alias_matches = [
        t for t in catalog.targets
        if any(_norm_key(alias) == norm for alias in t.aliases)
        or _norm_key(f"{t.area} {t.appliance}") == norm
    ]
    if len(alias_matches) == 1:
        return alias_matches[0], None
    if len(alias_matches) > 1:
        return None, {
            "status": "error", "success": False, "error_code": "ambiguous_target",
            "message": f"Target '{raw}' matches multiple appliances. Specify one exact target_id and ask the user if needed.",
            "candidates": [{"target_id": t.target_id, "label": t.label} for t in alias_matches],
        }

    dev_matches = [
        t for t in catalog.targets
        if _norm_key(t.device_name) == norm or t.device_id.casefold() == raw.casefold()
    ]
    if len(dev_matches) == 1:
        return dev_matches[0], None
    if len(dev_matches) > 1:
        return None, {
            "status": "error", "success": False, "error_code": "ambiguous_target",
            "message": f"Device '{raw}' has multiple controllable appliances. Specify the exact target_id (or ask the user to clarify).",
            "candidates": [{"target_id": t.target_id, "label": t.label} for t in dev_matches],
        }

    return None, {
        "status": "error", "success": False, "error_code": "device_not_found",
        "message": f"Target '{raw}' not found or name is ambiguous.",
        "available_targets": [{"target_id": t.target_id, "label": t.label} for t in catalog.targets],
    }


def _target_identity_tokens(target: ActionTarget) -> List[str]:
    raw_parts = f"{target.area} {target.device_name} {target.label} {' '.join(target.aliases)}"
    out = []
    for tok in _tokens(raw_parts):
        if tok in _STOPWORDS and not (len(tok) == 1 and tok.isalpha()):
            continue
        if tok not in out:
            out.append(tok)
    return out


def _effective_user_tokens(clause_text: str, catalog_tokens: set) -> List[str]:
    raw = _tokens(clause_text)
    out = []
    for idx, tok in enumerate(raw):
        if len(tok) == 1 and tok.isalpha():
            prev_tok = raw[idx - 1] if idx > 0 else ""
            if prev_tok in catalog_tokens or (idx == len(raw) - 1 and tok in catalog_tokens):
                out.append(tok)
            continue
        if tok in _STOPWORDS:
            continue
        out.append(tok)
    return out


def _score_clause_for_target(user_tokens: Sequence[str], target: ActionTarget) -> int:
    t_tokens = _target_identity_tokens(target)
    score = 0
    for u in user_tokens:
        if u in t_tokens:
            score += 1
        elif len(u) >= 3 and any(tt.startswith(u) for tt in t_tokens):
            score += 1
        elif u.isdigit() and u in t_tokens:
            score += 1
    return score


def _matching_clause(user_text: str, target: ActionTarget) -> str:
    clauses = [c.strip() for c in re.split(r"[,;]+|\b(?:and|và|then|rồi)\b", user_text, flags=re.IGNORECASE) if c.strip()]
    if len(clauses) <= 1:
        return user_text
    all_cat_tokens = set(_target_identity_tokens(target))
    best_clause = user_text
    best_score = -1
    for clause in clauses:
        u_toks = _effective_user_tokens(clause, all_cat_tokens)
        sc = _score_clause_for_target(u_toks, target)
        if sc > best_score:
            best_score = sc
            best_clause = clause
    return best_clause if best_score > 0 else user_text


def check_user_ambiguity(
    user_text: str,
    history: Sequence[Dict[str, Any]],
    resolved_targets: Sequence[ActionTarget],
    catalog: Optional[ActionCatalog],
    telemetry_checked: bool = False,
) -> Optional[Dict[str, Any]]:
    """Block ambiguous or wrong-category single-target guesses before sending any RPC."""
    if not catalog or not catalog.targets or not resolved_targets:
        return None

    targeted_ids = {t.target_id for t in resolved_targets}
    targeted_areas = {t.area for t in resolved_targets}
    is_plural_scene = bool(_PLURAL_OR_SCENE_RE.search(user_text))
    is_pronoun = bool(history and _PRONOUN_RE.search(user_text))
    is_conditional_filter = bool(telemetry_checked and _CONDITIONAL_OR_FILTER_RE.search(user_text))

    # Category mismatch gate (single explicit/environmental category vs opposite typed appliance)
    clause_cats_global = _infer_user_categories(user_text)
    if len(clause_cats_global) == 1 and len(targeted_ids) == 1 and not is_plural_scene:
        wanted_cat = next(iter(clause_cats_global))
        target = resolved_targets[0]
        if target.category in ("light", "fan", "lock") and target.category != wanted_cat:
            same_area = [t for t in catalog.targets if t.category == wanted_cat and t.area == target.area]
            cands = same_area or [t for t in catalog.targets if t.category == wanted_cat]
            msg = (
                f"Wrong category: '{target.target_id}' is a {target.category}, not a {wanted_cat}. "
                f"Retry control_targets IMMEDIATELY using target_id='{same_area[0].target_id}' (do NOT ask the user)."
                if len(same_area) == 1
                else f"User requested a {wanted_cat} action, but '{target.target_id}' is a {target.category}. Pick a matching target or inform the user if none exists."
            )
            return {
                "status": "error", "success": False, "error_code": "category_mismatch",
                "retryable": len(same_area) == 1,
                "message": msg,
                "candidates": [{"target_id": t.target_id, "label": t.label, "category": t.category} for t in cands],
            }

    if is_plural_scene or is_pronoun or is_conditional_filter:
        return None

    # A single-clause, non-plural request (e.g. "Bật đèn phòng ngủ") must not hedge across multiple areas.
    clauses = [c.strip() for c in re.split(r"[,;]+|\b(?:and|và|then|rồi)\b", user_text, flags=re.IGNORECASE) if c.strip()]
    if len(targeted_areas) > 1 and len(clauses) <= 1:
        return {
            "status": "error", "success": False, "error_code": "ambiguous_target",
            "message": (
                f"Request '{user_text}' is ambiguous across multiple locations/devices. "
                "Do NOT turn on/off multiple rooms at once — ask the user to clarify which specific one they want."
            ),
            "candidates": [{"target_id": t.target_id, "label": t.label, "device": t.device_name} for t in resolved_targets],
        }

    all_cat_tokens = {tok for t in catalog.targets for tok in _target_identity_tokens(t)}

    for target in resolved_targets:
        clause = _matching_clause(user_text, target)
        clause_cats = _infer_user_categories(clause)
        if len(clause_cats) == 1:
            wanted = next(iter(clause_cats))
            if target.category in ("light", "fan", "lock") and target.category != wanted:
                return {
                    "status": "error", "success": False, "error_code": "category_mismatch",
                    "message": f"Requested a {wanted} in '{clause}', but '{target.target_id}' is a {target.category}.",
                    "candidates": [{"target_id": t.target_id, "label": t.label} for t in catalog.targets if t.category == wanted],
                }
            pool = [t for t in catalog.targets if t.category == wanted] or list(catalog.targets)
        else:
            pool = list(catalog.targets)

        u_toks = _effective_user_tokens(clause, all_cat_tokens)
        my_score = _score_clause_for_target(u_toks, target)
        # Only exclude another targeted area if it matched a different clause; never let two targets tie on the same clause.
        peers = [
            p for p in pool
            if p.area != target.area and (p.target_id not in targeted_ids or _matching_clause(user_text, p) == clause)
        ]
        peer_scores = [(p, _score_clause_for_target(u_toks, p)) for p in peers]
        max_peer = max((sc for _, sc in peer_scores), default=-1)
        tied_peers = [p for p, sc in peer_scores if sc == max_peer and sc >= my_score]

        # Block if user's clause matched a different area/device in the catalog more strongly than the chosen target
        # (e.g. "kitchen fan 999" matches area "kitchen", not "bedroom_1").
        stronger_other = [
            p for p in catalog.targets
            if p.area != target.area and _score_clause_for_target(u_toks, p) > my_score
        ]
        if stronger_other and my_score == 0:
            return {
                "status": "error", "success": False, "error_code": "device_not_found",
                "message": (
                    f"Request '{clause}' refers to '{stronger_other[0].area}', which has no matching "
                    f"{target.category} target (or target '{target.target_id}' is in a different location '{target.area}')."
                ),
            }

        # Block cross-area tie (either partial shared prefix/keyword tie or 0-token generic request across multiple areas)
        distinct_areas = {p.area for p in pool}
        if tied_peers and (max_peer > 0 or (len(distinct_areas) >= 2 and my_score == 0)):
            candidates = [target, *tied_peers]
            return {
                "status": "error", "success": False, "error_code": "ambiguous_target",
                "message": (
                    f"Request '{clause}' is ambiguous across multiple locations/devices. "
                    "Do NOT guess — ask the user to clarify which specific device or room they want."
                ),
                "candidates": [{"target_id": c.target_id, "label": c.label, "device": c.device_name} for c in candidates],
            }

        # Block intra-area ambiguity when user gave no category, multiple appliances exist in the area, and LLM guessed only 1.
        same_area_peers = [
            p for p in pool
            if p.area == target.area and p.target_id not in targeted_ids
        ]
        if same_area_peers and not clause_cats and len(targeted_areas) == 1:
            return {
                "status": "error", "success": False, "error_code": "ambiguous_target",
                "message": (
                    f"Area '{target.area}' has multiple appliances and '{clause}' did not specify which one. "
                    "Ask the user to clarify which appliance (or confirm all) before sending RPC."
                ),
                "candidates": [{"target_id": c.target_id, "label": c.label} for c in (target, *same_area_peers)],
            }

    return None


def build_pipeline_tools(can_control: bool, include_custom_rpc: bool = True) -> List[Dict[str, Any]]:
    """Build minimal focused OpenAI tool definitions for the LLM."""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "inspect_home",
                "description": "Refresh and list all ThingsBoard IoT devices, availability, and controllable target_ids with their supported actions.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_telemetry",
                "description": "Read latest live sensor telemetry and appliance states (temperature, humidity, power, fan/light state). Pass device_name for one device, or omit device_name to read all devices.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "device_name": {"type": "string", "description": "Optional device name, UUID, or target_id; omit or pass 'all' to read all devices."},
                        "keys": {"type": "array", "items": {"type": "string"}, "description": "Optional specific telemetry keys."},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_current_time",
                "description": "Get the current local date and time.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]
    if can_control:
        tools.append({
            "type": "function",
            "function": {
                "name": "control_targets",
                "description": (
                    "Turn on, turn off, or toggle discovered target_ids. "
                    "Use turn_off=['all_lights'] for 'all lights' or bedtime ('going to sleep'/'đi ngủ', keeping fans ON); "
                    "use turn_off=['all'] only for 'leaving home'/'turn everything off'/'ra khỏi nhà'/'tắt hết'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "turn_on": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Exact target_ids (or group selector like 'all_lights', 'all_fans', 'all') to turn ON.",
                        },
                        "turn_off": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Exact target_ids (or group selector like 'all_lights', 'all_fans', 'all') to turn OFF.",
                        },
                        "toggle": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Exact target_ids to toggle.",
                        },
                    },
                },
            },
        })
        if include_custom_rpc:
            tools.append({
                "type": "function",
                "function": {
                    "name": "execute_device_action",
                    "description": "Execute a custom parameterized RPC method listed under Custom RPC methods (do not use for standard on/off/toggle targets — use control_targets).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "device_identifier": {"type": "string", "description": "Exact device name or UUID."},
                            "method": {"type": "string", "description": "Registered RPC method name."},
                            "params": {"description": "JSON parameters matching the method schema."},
                            "two_way": {"type": "boolean"},
                            "timeout_ms": {"type": "integer"},
                        },
                        "required": ["device_identifier", "method"],
                    },
                },
            })
    return tools


def build_system_prompt(base_prompt: str, catalog: Optional[ActionCatalog], can_control: bool) -> str:
    """Ground the LLM on live capabilities and abstract-intent rules without hardcoding devices."""
    catalog_text = format_catalog_for_prompt(catalog, read_only=not can_control)
    parts = [base_prompt]
    if catalog_text:
        parts.append(catalog_text)
    else:
        parts.append("No cached IoT target catalog is loaded yet. Call inspect_home first when the user asks about or wants to control devices.")

    if can_control:
        parts.append(
            "Tool-calling rules (strictly follow):\n"
            "1. Never invent device data, state changes, or RPC success. Only report actions returned by executed tool calls.\n"
            "2. Call control_targets with turn_on=[...], turn_off=[...], or toggle=[...] using exact target_ids (or group selectors 'all_lights', 'all_fans', 'all').\n"
            "3. Map abstract, environmental, and scene requests directly to control_targets (do NOT read telemetry or ask permission first):\n"
            "   - Hot / warm / nóng -> turn_on=[<room>.fan] (pick the [fan], NEVER the [light]).\n"
            "   - Dark / tối -> turn_on=[<room>.light] (pick the [light]).\n"
            "   - Humid / stuffy / ẩm / bí / ngộp -> turn_on=[<room>.exhaust_fan / fan].\n"
            "   - 'all lights' / 'tắt hết đèn' / bedtime ('going to sleep' / 'good night' / 'đi ngủ') -> turn_off=['all_lights'] ONLY (keep fans ON, NEVER turn off [fan] targets for bedtime; e.g. 'Tôi đi ngủ đây' -> control_targets(turn_off=['all_lights'])).\n"
            "   - 'leaving home' / 'turn everything off' / 'ra khỏi nhà' / 'tắt hết' -> turn_off=['all'].\n"
            "4. For sensor questions or conditionals ('if temp > ...' / 'nếu ...'), call get_telemetry first. On conditionals, evaluate the numbers carefully: if the condition is FALSE, do NOT call control_targets — just report the reading.\n"
            "5. Ambiguity & safety: If a request is ambiguous across multiple rooms/devices (e.g. 'turn off bed' or 'bật đèn phòng ngủ' when Bedroom 1 and Bedroom 2 both exist, or a bare room name with both light and fan), DO NOT guess and DO NOT call control_targets — ask the user to clarify.\n"
            "6. If a requested device or capability does not exist (e.g. brightness/dimmer, timer, AC, or an unknown device), refuse directly without calling control_targets on unrelated devices.\n"
            "7. Never repeat an RPC that already succeeded in this turn."
        )
    else:
        parts.append(
            "Tool policy is READ-ONLY: you can call inspect_home and get_telemetry to inspect sensors and devices, "
            "but you must refuse any device control or RPC requests because control is disabled."
        )
    return "\n\n".join(parts)


_GROUP_SELECTOR_CATEGORIES = {
    "all_lights": "light",
    "all lights": "light",
    "lights": "light",
    "all_fans": "fan",
    "all fans": "fan",
    "fans": "fan",
    "all_locks": "lock",
    "all locks": "lock",
    "locks": "lock",
}
_ALL_SELECTOR_KEYS = frozenset({"all", "all_targets", "all targets", "all_devices", "all devices", "everything"})


def _as_str_list(value: Any) -> List[str]:
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    value = parsed
            except ValueError:
                pass
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _compact_telemetry(raw_telemetry: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, entries in (raw_telemetry or {}).items():
        if isinstance(entries, list) and entries:
            out[key] = entries[0].get("value")
        else:
            out[key] = entries
    return out


def _extract_numeric_telemetry(raw_telemetry: Dict[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for key, val in _compact_telemetry(raw_telemetry).items():
        if isinstance(val, bool):
            continue
        try:
            out[str(key).lower()] = float(val)
        except (TypeError, ValueError):
            continue
    return out


_COND_CLAUSE_RE = re.compile(
    r"\b(?:if|when|nếu)\b[^.;?!\n]*?"
    r"(?:(>=|at\s+least|greater\s+than\s+or\s+equal|ít\s+nhất)"
    r"|(<=|at\s+most|less\s+than\s+or\s+equal|tối\s+đa|không\s+quá)"
    r"|(>|above|over|greater\s+than|more\s+than|higher\s+than|exceeds?|trên|lớn\s+hơn|cao\s+hơn|vượt)"
    r"|(<|below|under|less\s+than|lower\s+than|dưới|nhỏ\s+hơn|thấp\s+hơn))"
    r"\s*(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_ELSE_SPLIT_RE = re.compile(r"\b(?:else|otherwise|if\s+not|ngược\s+lại|còn\s+không|nếu\s+không)\b", re.IGNORECASE)
_ELSE_KEEP_RE = re.compile(r"\b(?:leave|keep|stay|remain|don't|do\s+not|giữ\s+nguyên|không\s+(?:bật|tắt|làm))\b", re.IGNORECASE)


def _clause_action_intent(text: str) -> Optional[str]:
    if not text:
        return None
    if re.search(r"\b(?:turn\s+on|switch\s+on|power\s+on|bật|mở)\b", text, re.IGNORECASE):
        return "on"
    if re.search(r"\b(?:turn\s+off|switch\s+off|power\s+off|tắt|ngắt)\b", text, re.IGNORECASE):
        return "off"
    if re.search(r"\b(?:toggle|đảo)\b", text, re.IGNORECASE):
        return "toggle"
    return None


def evaluate_telemetry_condition(
    user_text: str,
    telemetry_values: Dict[str, float],
    proposed_actions: Sequence[str],
    telemetry_by_device: Optional[Dict[str, Dict[str, float]]] = None,
) -> Optional[Dict[str, Any]]:
    """Verify numeric conditional requests against live fetched telemetry before sending RPC."""
    if not telemetry_values or not proposed_actions:
        return None
    match = _COND_CLAUSE_RE.search(user_text or "")
    if not match:
        return None

    op = ">=" if match.group(1) else "<=" if match.group(2) else ">" if match.group(3) else "<"
    threshold = float(match.group(5))

    # Pick device-specific telemetry if a fetched device name/area is mentioned in user_text.
    scoped_vals = telemetry_values
    if telemetry_by_device:
        norm_user = _norm_key(user_text)
        for dev_key, vals in telemetry_by_device.items():
            if dev_key and dev_key in norm_user and vals:
                scoped_vals = vals
                break

    cond_text = match.group(0).lower()
    metric_key = None
    if re.search(r"humid|ẩm", cond_text):
        metric_key = next((k for k in scoped_vals if "humid" in k), None)
    elif re.search(r"temp|nhiệt|độ|degrees|°", cond_text):
        metric_key = next((k for k in scoped_vals if "temp" in k), None)
    if metric_key is None:
        metric_key = next((k for k in scoped_vals if k in user_text.lower()), None)
    if metric_key is None and len(scoped_vals) == 1:
        metric_key = next(iter(scoped_vals))
    if metric_key is None or metric_key not in scoped_vals:
        return None

    actual = scoped_vals[metric_key]
    cond_met = (
        actual >= threshold if op == ">=" else
        actual <= threshold if op == "<=" else
        actual > threshold if op == ">" else
        actual < threshold
    )

    parts = _ELSE_SPLIT_RE.split(user_text, maxsplit=1)
    if_part = parts[0]
    else_part = parts[1] if len(parts) > 1 else ""
    else_action = None if (not else_part or _ELSE_KEEP_RE.search(else_part)) else _clause_action_intent(else_part)
    if_action = _clause_action_intent(if_part[match.end():]) or _clause_action_intent(if_part)

    if not cond_met:
        if else_action and all(act == else_action for act in proposed_actions):
            return None
        return {
            "status": "error",
            "success": False,
            "error_code": "condition_not_met",
            "message": (
                f"Condition is FALSE ({metric_key}={actual}, NOT {op} {threshold}). "
                "Do NOT call control_targets — report the telemetry reading and leave the device unchanged."
            ),
            "metric": metric_key,
            "actual": actual,
            "operator": op,
            "threshold": threshold,
        }

    if else_action and if_action and else_action != if_action and any(act == else_action for act in proposed_actions):
        return {
            "status": "error",
            "success": False,
            "error_code": "condition_not_met",
            "message": f"Condition IS TRUE ({metric_key}={actual} {op} {threshold}); execute the '{if_action}' branch instead of '{else_action}'.",
        }
    return None


def _expand_selector(
    raw_id: str,
    catalog: Optional[ActionCatalog],
    user_text: str,
) -> Tuple[Optional[List[str]], Optional[Dict[str, Any]]]:
    key = re.sub(r"[\s_-]+", "_", _strip_accents(raw_id or "").strip().lower()).strip("_")
    space_key = key.replace("_", " ")
    if key in _GROUP_SELECTOR_CATEGORIES or space_key in _GROUP_SELECTOR_CATEGORIES:
        if not _PLURAL_OR_SCENE_RE.search(user_text or ""):
            return None, {
                "status": "error", "success": False, "error_code": "ambiguous_target",
                "message": "Group selector cannot be used for a non-plural or ambiguous request. Ask the user to clarify.",
            }
        cat = _GROUP_SELECTOR_CATEGORIES.get(key) or _GROUP_SELECTOR_CATEGORIES[space_key]
        if not catalog:
            return None, {"status": "error", "success": False, "error_code": "device_not_found", "message": "No capability catalog available."}
        ids = [t.target_id for t in catalog.targets if t.category == cat]
        if not ids:
            return None, {"status": "error", "success": False, "error_code": "device_not_found", "message": f"No {cat} targets found."}
        return ids, None
    if key in _ALL_SELECTOR_KEYS or space_key in _ALL_SELECTOR_KEYS:
        if not _PLURAL_OR_SCENE_RE.search(user_text or ""):
            return None, {
                "status": "error", "success": False, "error_code": "ambiguous_target",
                "message": "Group selector 'all' cannot be used for a non-plural or ambiguous request. Ask the user to clarify.",
            }
        if not catalog or not catalog.targets:
            return None, {"status": "error", "success": False, "error_code": "device_not_found", "message": "No controllable targets found."}
        return [t.target_id for t in catalog.targets], None
    return [raw_id], None


def _normalize_batch_actions(args: Dict[str, Any]) -> Optional[List[Dict[str, str]]]:
    # Prefer flat turn_on / turn_off / toggle arrays (Ollama-reliable schema).
    flat_items: List[Dict[str, str]] = []
    for key, act in (("turn_on", "on"), ("turn_off", "off"), ("toggle", "toggle")):
        for tid in _as_str_list(args.get(key)):
            flat_items.append({"target_id": tid, "action": act})
    if flat_items:
        return flat_items

    raw_actions = args.get("actions")
    if isinstance(raw_actions, dict):
        raw_actions = [raw_actions]
    elif isinstance(raw_actions, str):
        try:
            raw_actions = json.loads(raw_actions)
        except ValueError:
            raw_actions = None
    if not isinstance(raw_actions, list) and (args.get("target_id") or args.get("target")):
        raw_actions = [args]
    if not isinstance(raw_actions, list) or not raw_actions:
        return None

    normalized = []
    for item in raw_actions:
        if not isinstance(item, dict):
            continue
        target_id = str(item.get("target_id") or item.get("target") or item.get("device_identifier") or "").strip()
        action = item.get("action")
        if action is None and isinstance(item.get("state"), bool):
            action = "on" if item["state"] else "off"
        action_str = str(action or "").strip().lower()
        if action_str in ("true", "1"):
            action_str = "on"
        elif action_str in ("false", "0"):
            action_str = "off"
        normalized.append({"target_id": target_id, "action": action_str})
    return normalized or None


def _rpc_dispatched(tool_entry: Dict[str, Any]) -> bool:
    if tool_entry["name"] not in ("send_rpc", "thingsboard_rpc", "execute_device_action", "control_targets"):
        return False
    try:
        res = json.loads(tool_entry["result"])
    except (ValueError, TypeError):
        return True
    return res.get("error_code") not in PRE_SEND_ERRORS and bool(res.get("success", True))


def _resolve_device_name_from_catalog(catalog: Optional[ActionCatalog], identifier: str) -> str:
    if not catalog or not identifier:
        return identifier
    norm = _norm_key(identifier)
    for dev in catalog.devices:
        if _norm_key(dev.get("name", "")) == norm or dev.get("id", "").casefold() == identifier.casefold():
            return dev["name"]
    target, err = resolve_catalog_target(catalog, identifier)
    if target:
        return target.device_name
    area_devs = {t.device_name for t in catalog.targets if _norm_key(t.area) == norm}
    if len(area_devs) == 1:
        return next(iter(area_devs))
    return identifier


async def run_tool_pipeline(
    agent: Dict[str, Any],
    user_text: str,
    history: Sequence[Dict[str, Any]],
    base_prompt: str,
    tb_conf: Dict[str, Any],
    validate_origin: Callable[[str], str],
    ollama_url: str,
    model_name: str,
) -> Dict[str, Any]:
    """Run the 5-stage LLM + ThingsBoard tool-calling pipeline for one user turn."""
    import httpx

    tb_host = (tb_conf.get("host") or "").rstrip("/")
    tb_key = tb_conf.get("api_key") or ""
    if tb_host and tb_key:
        tb_host = validate_origin(tb_host)
    validated_tb_conf = {**tb_conf, "host": tb_host, "api_key": tb_key}
    tb_headers = {"User-Agent": "XiaoZhi-Platform/1.0", "X-Authorization": f"ApiKey {tb_key}"}

    read_only = agent.get("tool_policy") == "read_only_telemetry"
    can_control = bool(tb_host and tb_key and not read_only)
    profile_id = agent.get("id")

    # Stage 1: Load cached catalog locally (zero HTTP calls).
    catalog: Optional[ActionCatalog] = load_cached_catalog(validated_tb_conf, profile_id) if tb_host and tb_key else None

    # Stage 2: Build focused tool surface & grounded prompt.
    pipeline_tools = build_pipeline_tools(
        can_control=can_control,
        include_custom_rpc=(catalog is None or bool(catalog.custom_methods)),
    )
    system_prompt = build_system_prompt(base_prompt, catalog, can_control=can_control)
    messages: List[Dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for h in (history or [])[-6:]:
        r = h.get("role")
        c = h.get("content")
        if r in ("user", "assistant") and c:
            messages.append({"role": r, "content": c})
    messages.append({"role": "user", "content": user_text})

    executed_tools: List[Dict[str, Any]] = []
    dispatched_actions: set = set()
    telemetry_checked = False
    latest_numeric_telemetry: Dict[str, float] = {}
    telemetry_by_device: Dict[str, Dict[str, float]] = {}
    legacy_tb_tools = {t["function"]["name"] for t in agent_api_tools.MCP_TOOLS + agent_api_tools.TOOLS}

    def record_telemetry(dev_name: str, raw_telemetry: Dict[str, Any]) -> None:
        nums = _extract_numeric_telemetry(raw_telemetry)
        if not nums:
            return
        latest_numeric_telemetry.update(nums)
        for key in (_norm_key(dev_name), _slug(dev_name).replace("_", " ")):
            if key:
                telemetry_by_device.setdefault(key, {}).update(nums)
        if catalog:
            for t in catalog.targets:
                if _norm_key(t.device_name) == _norm_key(dev_name):
                    telemetry_by_device.setdefault(_norm_key(t.area), {}).update(nums)

    async def refresh_catalog(http_client: httpx.AsyncClient) -> Dict[str, Any]:
        nonlocal catalog
        if not tb_host or not tb_key:
            return {"status": "error", "success": False, "message": "ThingsBoard host or API key is not configured."}
        res = await agent_api_tools.execute(
            http_client, validated_tb_conf, "discover_capabilities", {}, read_only=read_only, profile_id=profile_id
        )
        if res.get("success"):
            catalog = compile_action_catalog(res.get("capabilities") or [])
            return {
                "status": "success",
                "success": True,
                "devices": catalog.devices,
                "targets": [
                    {
                        "target_id": t.target_id,
                        "category": t.category,
                        "device": t.device_name,
                        "label": t.label,
                        "availability": t.availability,
                        "actions": list(t.actions.keys()),
                    }
                    for t in catalog.targets
                ],
                "custom_methods": [
                    {"device": cm["device_name"], "method": cm["method"], "description": cm.get("description", "")}
                    for cm in catalog.custom_methods
                ],
            }
        return res

    async def run_all_telemetry(http_client: httpx.AsyncClient, keys: Any) -> Dict[str, Any]:
        devices = await agent_api_tools._all_devices(http_client, tb_host, tb_headers)
        params: Dict[str, str] = {}
        if isinstance(keys, list) and keys:
            clean_keys = [str(k).strip() for k in keys if str(k).strip()]
            if clean_keys:
                params["keys"] = ",".join(clean_keys)

        async def fetch_one(dev: Dict[str, Any]) -> Dict[str, Any]:
            dev_id = dev["id"]["id"]
            resp = await http_client.get(
                f"{tb_host}/api/plugins/telemetry/DEVICE/{dev_id}/values/timeseries",
                params=params or None,
                headers=tb_headers,
            )
            resp.raise_for_status()
            redacted = agent_api_tools.redact_credentials(resp.json(), tb_key)
            record_telemetry(dev.get("name") or dev_id, redacted)
            compact = _compact_telemetry(redacted)
            return {"device": dev.get("name"), "device_id": dev_id, "telemetry": compact}

        results = await asyncio.gather(*(fetch_one(d) for d in devices))
        return {"status": "success", "success": True, "devices": list(results)}

    async def execute_control_batch(
        http_client: httpx.AsyncClient,
        tc_id: str,
        args_dict: Dict[str, Any],
    ) -> Tuple[str, List[Dict[str, Any]]]:
        nonlocal catalog
        if read_only:
            err = json.dumps({
                "status": "forbidden", "success": False, "confirmed": False, "delivery": "failed",
                "error_code": "forbidden", "message": "Agent policy does not allow RPC.",
            }, ensure_ascii=False)
            return err, [{"id": tc_id, "name": "control_targets", "arguments": json.dumps(args_dict, ensure_ascii=False), "result": err}]

        actions = _normalize_batch_actions(args_dict)
        if not actions:
            err = json.dumps({
                "status": "error", "success": False, "error_code": "invalid_params",
                "message": "Provide turn_on=['target_id'], turn_off=['target_id'], or toggle=['target_id'].",
            }, ensure_ascii=False)
            return err, [{"id": tc_id, "name": "control_targets", "arguments": json.dumps(args_dict, ensure_ascii=False), "result": err}]

        if not tb_host or not tb_key:
            err = json.dumps({"status": "error", "success": False, "message": "ThingsBoard host or API key is not configured."}, ensure_ascii=False)
            return err, [{"id": tc_id, "name": "control_targets", "arguments": json.dumps(args_dict, ensure_ascii=False), "result": err}]

        async with agent_api_tools.scoped_registry(validated_tb_conf, profile_id) as registry:
            if registry is not None:
                catalog = compile_action_catalog(registry.list())
            elif catalog is None:
                err = json.dumps({"status": "error", "success": False, "error_code": "device_not_found", "message": "No capability catalog available."}, ensure_ascii=False)
                return err, [{"id": tc_id, "name": "control_targets", "arguments": json.dumps(args_dict, ensure_ascii=False), "result": err}]

            expanded_actions: List[Dict[str, str]] = []
            for item in actions:
                expanded_ids, sel_err = _expand_selector(item["target_id"], catalog, user_text)
                if sel_err:
                    err = json.dumps(sel_err, ensure_ascii=False)
                    return err, [{"id": tc_id, "name": "control_targets", "arguments": json.dumps(args_dict, ensure_ascii=False), "result": err}]
                for tid in expanded_ids:
                    expanded_actions.append({"target_id": tid, "action": item["action"]})

            resolved_items: List[Tuple[Dict[str, str], ActionTarget]] = []
            for item in expanded_actions:
                target, err_obj = resolve_catalog_target(catalog, item["target_id"])
                if err_obj:
                    err = json.dumps(err_obj, ensure_ascii=False)
                    return err, [{"id": tc_id, "name": "control_targets", "arguments": json.dumps(args_dict, ensure_ascii=False), "result": err}]
                if item["action"] not in target.actions:
                    err = json.dumps({
                        "status": "error", "success": False, "error_code": "unsupported_method",
                        "device": target.device_name, "target_id": target.target_id,
                        "message": f"Target '{target.target_id}' does not support action '{item['action']}'. Supported: {list(target.actions.keys())}.",
                    }, ensure_ascii=False)
                    return err, [{"id": tc_id, "name": "control_targets", "arguments": json.dumps(args_dict, ensure_ascii=False), "result": err}]
                resolved_items.append((item, target))

            ambiguity_err = check_user_ambiguity(
                user_text, history, [target for _, target in resolved_items], catalog, telemetry_checked=telemetry_checked
            )
            if ambiguity_err:
                err = json.dumps(ambiguity_err, ensure_ascii=False)
                return err, [{"id": tc_id, "name": "control_targets", "arguments": json.dumps(args_dict, ensure_ascii=False), "result": err}]

            if telemetry_checked:
                cond_err = evaluate_telemetry_condition(
                    user_text,
                    latest_numeric_telemetry,
                    [item["action"] for item, _ in resolved_items],
                    telemetry_by_device=telemetry_by_device,
                )
                if cond_err:
                    err = json.dumps(cond_err, ensure_ascii=False)
                    return err, [{"id": tc_id, "name": "control_targets", "arguments": json.dumps(args_dict, ensure_ascii=False), "result": err}]

            # Deduplicate identical RPC calls within the batch and current turn, preserving order per device.
            per_device: Dict[str, List[Tuple[ActionTarget, str, str, Any]]] = {}
            for item, target in resolved_items:
                method, params = target.actions[item["action"]]
                sig = (target.device_id, method, json.dumps(params, sort_keys=True, ensure_ascii=False))
                if sig in dispatched_actions:
                    continue
                dispatched_actions.add(sig)
                per_device.setdefault(target.device_id, []).append((target, item["action"], method, params))

            if not per_device:
                summary = json.dumps({"status": "success", "success": True, "deduplicated": True, "results": []}, ensure_ascii=False)
                return summary, []

            async def run_device_queue(queue: List[Tuple[ActionTarget, str, str, Any]]) -> List[Tuple[ActionTarget, str, str, Any, Dict[str, Any]]]:
                out = []
                for q_idx, (target, action_name, method, params) in enumerate(queue):
                    if q_idx > 0:
                        await asyncio.sleep(0.3)
                    exec_args = {"device_identifier": target.device_id, "method": method, "params": params}
                    res = await agent_api_tools.execute(
                        http_client, validated_tb_conf, "execute_device_action",
                        exec_args, read_only=read_only, profile_id=profile_id,
                    )
                    res["device"] = target.device_name
                    res["target_id"] = target.target_id
                    res["action"] = action_name
                    if not res.get("success"):
                        sig = (target.device_id, method, json.dumps(params, sort_keys=True, ensure_ascii=False))
                        dispatched_actions.discard(sig)
                    out.append((target, action_name, method, params, res))
                return out

            grouped_results = await asyncio.gather(*(run_device_queue(q) for q in per_device.values()))
            tool_entries: List[Dict[str, Any]] = []
            batch_results: List[Dict[str, Any]] = []
            for group in grouped_results:
                for idx, (target, _action_name, method, params, res) in enumerate(group):
                    batch_results.append(res)
                    tool_entries.append({
                        "id": f"{tc_id}_{len(tool_entries)}",
                        "name": "execute_device_action",
                        "arguments": json.dumps({
                            "device_identifier": target.device_name,
                            "target_id": target.target_id,
                            "method": method,
                            "params": params,
                        }, ensure_ascii=False),
                        "result": json.dumps(res, ensure_ascii=False),
                    })

            all_ok = all(r.get("success") for r in batch_results)
            summary = json.dumps({"status": "success" if all_ok else "error", "success": all_ok, "results": batch_results}, ensure_ascii=False)
            return summary, tool_entries

    async def execute_single_tool(tc_id: str, tool_name: str, args_dict: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
        nonlocal catalog, telemetry_checked
        args_json = json.dumps(args_dict, ensure_ascii=False)
        if tool_name == "get_current_time":
            res_str = json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S %Z")})
            return res_str, [{"id": tc_id, "name": tool_name, "arguments": args_json, "result": res_str}]

        if tool_name == "control_targets":
            async with httpx.AsyncClient(timeout=20.0) as tb_client:
                return await execute_control_batch(tb_client, tc_id, args_dict)

        if tool_name == "inspect_home":
            async with httpx.AsyncClient(timeout=15.0) as tb_client:
                res_str = json.dumps(await refresh_catalog(tb_client), ensure_ascii=False)
                return res_str, [{"id": tc_id, "name": tool_name, "arguments": args_json, "result": res_str}]

        if tool_name not in legacy_tb_tools:
            res_str = json.dumps({"status": "error", "message": f"Unknown tool: {tool_name}"})
            return res_str, [{"id": tc_id, "name": tool_name, "arguments": args_json, "result": res_str}]

        if not tb_host or not tb_key:
            res_str = json.dumps({"status": "error", "message": "ThingsBoard host or API key is not configured."})
            return res_str, [{"id": tc_id, "name": tool_name, "arguments": args_json, "result": res_str}]

        async with httpx.AsyncClient(timeout=8.0) as tb_client:
            if tool_name == "get_telemetry":
                telemetry_checked = True
                raw_name = (args_dict.get("device_name") or args_dict.get("device_identifier") or "").strip()
                if not raw_name or raw_name.lower() in ("all", "*"):
                    res_str = json.dumps(await run_all_telemetry(tb_client, args_dict.get("keys")), ensure_ascii=False)
                    return res_str, [{"id": tc_id, "name": tool_name, "arguments": args_json, "result": res_str}]
                mapped_name = _resolve_device_name_from_catalog(catalog, raw_name)
                if mapped_name != raw_name:
                    args_dict = {**args_dict, "device_name": mapped_name}

            if tool_name in ("send_rpc", "execute_device_action", "thingsboard_rpc") and catalog and catalog.targets:
                raw_id = str(args_dict.get("device_identifier") or args_dict.get("device_name") or args_dict.get("device_id") or "").strip()
                method = str(args_dict.get("method") or "").strip()
                raw_params = args_dict.get("params")
                if isinstance(raw_params, str):
                    try:
                        parsed_params = json.loads(raw_params)
                    except ValueError:
                        parsed_params = raw_params
                else:
                    parsed_params = {} if raw_params is None else raw_params
                matching = [
                    t for t in catalog.targets
                    if t.target_id == raw_id or _norm_key(t.device_name) == _norm_key(raw_id) or t.device_id.casefold() == raw_id.casefold()
                ]
                if matching:
                    exact_action_targets = [
                        t for t in matching
                        if any(m == method and p == parsed_params for m, p in t.actions.values())
                    ]
                    check_targets = exact_action_targets or ([matching[0]] if len(matching) == 1 else [])
                    if check_targets:
                        amb = check_user_ambiguity(user_text, history, check_targets, catalog, telemetry_checked=telemetry_checked)
                        if amb:
                            res_str = json.dumps(amb, ensure_ascii=False)
                            return res_str, [{"id": tc_id, "name": tool_name, "arguments": args_json, "result": res_str}]
            if tool_name in ("send_rpc", "execute_device_action", "thingsboard_rpc") and telemetry_checked:
                method_lower = str(args_dict.get("method") or "").lower()
                raw_p = args_dict.get("params")
                if isinstance(raw_p, str):
                    try:
                        raw_p = json.loads(raw_p)
                    except ValueError:
                        pass
                inferred_act = (
                    "toggle" if "toggle" in method_lower
                    else "on" if (raw_p is True or raw_p == 1 or (isinstance(raw_p, dict) and raw_p.get("state") is True))
                    else "off" if (raw_p is False or raw_p == 0 or (isinstance(raw_p, dict) and raw_p.get("state") is False))
                    else None
                )
                if inferred_act:
                    cond_err = evaluate_telemetry_condition(
                        user_text, latest_numeric_telemetry, [inferred_act], telemetry_by_device=telemetry_by_device
                    )
                    if cond_err:
                        res_str = json.dumps(cond_err, ensure_ascii=False)
                        return res_str, [{"id": tc_id, "name": tool_name, "arguments": args_json, "result": res_str}]

            if tool_name in ("thingsboard_get", "thingsboard_rpc"):
                args_dict = dict(args_dict)
                path = args_dict.get("path", "") if tool_name == "thingsboard_get" else ""
                match = re.match(r"^(/api/plugins/telemetry/DEVICE/)([^/?]+)(/.*)$", path) if isinstance(path, str) else None
                identifier = (
                    urllib_unquote(match.group(2)) if match
                    else args_dict.get("device_id", "") if tool_name == "thingsboard_rpc" else ""
                )
                if identifier:
                    if not agent_api_tools.UUID_RE.fullmatch(str(identifier)):
                        devices = await agent_api_tools._all_devices(tb_client, tb_host, tb_headers)
                        device = agent_api_tools._matching_device(devices, identifier)
                        if not device:
                            res_str = json.dumps({"status": "error", "message": f"Device '{identifier}' not found or name is ambiguous"})
                            return res_str, [{"id": tc_id, "name": tool_name, "arguments": args_json, "result": res_str}]
                        device_id = device["id"]["id"]
                        if match:
                            args_dict["path"] = match.group(1) + device_id + match.group(3)
                        else:
                            args_dict["device_id"] = device_id

            result = await agent_api_tools.execute(
                tb_client, validated_tb_conf, tool_name, args_dict,
                read_only=read_only, profile_id=profile_id,
            )
            if tool_name == "get_telemetry" and result.get("success"):
                raw_tel = result.get("telemetry") or {}
                record_telemetry(result.get("device") or args_dict.get("device_name") or "", raw_tel)
                if raw_tel:
                    result["values"] = _compact_telemetry(raw_tel)
            if tool_name in ("discover_capabilities", "list_available_rpc") and result.get("success"):
                caps = result.get("capabilities") or []
                if tool_name == "discover_capabilities" and caps:
                    catalog = compile_action_catalog(caps)
            if tool_name in ("execute_device_action", "send_rpc") and not result.get("success"):
                if result.get("error_code") in ("unsupported_method", "invalid_params", "device_not_found") and catalog and catalog.targets:
                    result["hint"] = "Use control_targets with an exact target_id: " + ", ".join(t.target_id for t in catalog.targets)
            res_str = json.dumps(result, ensure_ascii=False)
            return res_str, [{"id": tc_id, "name": tool_name, "arguments": args_json, "result": res_str}]

    # Stage 4 & 5: Multi-round execution loop + Response Integrity Guard.
    async with httpx.AsyncClient(timeout=25.0) as client:
        waiting_retried = False
        empty_retried = False
        action_nudges = 0
        is_control_request = can_control and bool(_CONTROL_REQUEST_RE.search(user_text) or _ABSTRACT_CONTROL_RE.search(user_text))

        for _attempt in range(MAX_TOOL_ROUNDS):
            model_response = await client.post(
                f"{ollama_url}/v1/chat/completions",
                json={"model": model_name, "messages": messages, "tools": pipeline_tools, "stream": False, "temperature": 0.1 if empty_retried else 0},
            )
            model_response.raise_for_status()
            msg = model_response.json().get("choices", [{}])[0].get("message", {})
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                content = (msg.get("content") or "").strip()
                if not content:
                    if not empty_retried:
                        empty_retried = True
                        continue
                    raise ValueError("Model returned an empty response")

                rpc_attempted = any(
                    tool["name"] in ("send_rpc", "thingsboard_rpc", "execute_device_action", "control_targets")
                    for tool in executed_tools
                )
                rpc_sent = any(_rpc_dispatched(tool) for tool in executed_tools)
                condition_blocked = any(
                    (json.loads(tool["result"]).get("error_code") == "condition_not_met")
                    for tool in executed_tools
                    if tool["name"] in ("control_targets", "execute_device_action", "send_rpc", "thingsboard_rpc")
                    and tool["result"].lstrip().startswith("{")
                )

                if condition_blocked:
                    if not rpc_sent and _UNVERIFIED_ACTION_RE.search(content):
                        if action_nudges < 2:
                            action_nudges += 1
                            messages.append({"role": "assistant", "content": content})
                            messages.append({"role": "user", "content": "No device RPC was executed because the condition is FALSE. Report the actual telemetry reading and clearly state the device was left unchanged."})
                            continue
                    return {"reply": content, "tool_calls": executed_tools}

                if _DESCRIBED_ACTION_RE.search(content):
                    if action_nudges >= 2 or rpc_sent:
                        content = (
                            "Tôi chưa thể xác nhận yêu cầu điều khiển đã hoàn tất."
                            if agent.get("language", "vi") == "vi"
                            else "I could not confirm that the control request completed."
                        )
                    else:
                        action_nudges += 1
                        # Qwen2.5's Ollama template drops role="system" messages after index 0, so nudges use user turns.
                        messages.append({"role": "assistant", "content": "I have not called the device tool yet."})
                        hint = (
                            "Call control_targets with turn_on=[...], turn_off=[...], or toggle=[...] using exact target_ids (or inspect_home first)."
                            if catalog and catalog.targets
                            else "Call inspect_home (or execute_device_action with a registered method) using a structured tool call."
                        )
                        messages.append({"role": "user", "content": f"Do not describe the tool call in text. {hint} Request: {user_text!r}."})
                        continue

                retryable_cat_err = False
                if not rpc_sent and executed_tools:
                    try:
                        last_res = json.loads(executed_tools[-1]["result"])
                        retryable_cat_err = bool(last_res.get("error_code") == "category_mismatch" and last_res.get("retryable"))
                    except (ValueError, TypeError):
                        retryable_cat_err = False

                missing_control_rpc = (
                    is_control_request
                    and (not rpc_attempted or retryable_cat_err)
                    and not ((executed_tools or catalog is not None) and _NOT_FOUND_REPLY_RE.search(content) and not _UNVERIFIED_ACTION_RE.search(content))
                )
                if not rpc_sent and (_UNVERIFIED_ACTION_RE.search(content) or missing_control_rpc):
                    if action_nudges >= 2:
                        content = (
                            "Tôi chưa thể xác nhận yêu cầu điều khiển đã hoàn tất."
                            if agent.get("language", "vi") == "vi"
                            else "I could not confirm that the control request completed."
                        )
                    else:
                        action_nudges += 1
                        messages.append({"role": "assistant", "content": "I have not executed the device action yet."})
                        hint = (
                            f"Call control_targets now with turn_on=[...], turn_off=[...], or toggle=[...] using exact target_ids ({', '.join(t.target_id for t in catalog.targets)}), or ask for clarification if ambiguous."
                            if catalog and catalog.targets
                            else "Call inspect_home or execute_device_action now using a registered method (or say not found if the device does not exist)."
                        )
                        messages.append({"role": "user", "content": f"No control tool was called yet for {user_text!r}. {hint}"})
                        continue

                if not rpc_sent and _WAITING_RE.search(content):
                    if waiting_retried:
                        content = (
                            "Tôi chưa thể hoàn thành yêu cầu này."
                            if agent.get("language", "vi") == "vi"
                            else "I could not complete this request."
                        )
                    else:
                        waiting_retried = True
                        messages.append({"role": "assistant", "content": content})
                        messages.append({"role": "user", "content": "Do not ask me to wait. Call the necessary tool now or explain clearly why you cannot complete the request."})
                        continue

                return {"reply": content, "tool_calls": executed_tools}

            messages.append({**msg, "content": ""})
            for tc in tool_calls:
                fn = tc.get("function", {})
                tc_id = tc.get("id", "call_default")
                fn_name = fn.get("name", "")
                raw_args = fn.get("arguments", "{}")
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    if not isinstance(args, dict):
                        args = {}
                except (ValueError, TypeError):
                    args = {}
                try:
                    tool_res_str, entries = await execute_single_tool(tc_id, fn_name, args)
                except Exception as exc:
                    logger.warning("Tool %s failed: %s", fn_name, type(exc).__name__)
                    tool_res_str = json.dumps({"status": "error", "message": "ThingsBoard request failed or timed out."})
                    entries = [{"id": tc_id, "name": fn_name, "arguments": json.dumps(args, ensure_ascii=False), "result": tool_res_str}]
                executed_tools.extend(entries)
                messages.append({"role": "tool", "tool_call_id": tc_id, "content": tool_res_str})
            if catalog is not None:
                pipeline_tools = build_pipeline_tools(
                    can_control=can_control,
                    include_custom_rpc=bool(catalog.custom_methods),
                )

        final_response = await client.post(
            f"{ollama_url}/v1/chat/completions",
            json={"model": model_name, "messages": messages, "stream": False, "temperature": 0},
        )
        final_response.raise_for_status()
        final_content = (final_response.json().get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
        if not final_content:
            final_content = (
                "Tôi chưa thể hoàn thành yêu cầu này."
                if agent.get("language", "vi") == "vi"
                else "I could not complete this request."
            )
        return {"reply": final_content, "tool_calls": executed_tools}


def urllib_unquote(value: str) -> str:
    from urllib.parse import unquote
    return unquote(value)
