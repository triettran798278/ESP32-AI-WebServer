"""
Platform Data Store.
Manages Agent Profiles, Device Bindings, and ThingsBoard Integrations.
Serves as the single source of truth for the platform.
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

try:
    from .device_db import device_db
except ImportError:
    from device_db import device_db

logger = logging.getLogger("platform_bridge.store")

DATA_DIR = Path(os.getenv("PLATFORM_DATA_DIR", "/app/data" if os.path.exists("/app") else "./data"))
PROFILES_FILE = DATA_DIR / "agents.json"
BINDINGS_FILE = DATA_DIR / "device_bindings.json"


def normalize_mac(mac: str) -> str:
    """Normalize MAC address to standard colon-separated uppercase format."""
    clean = re.sub(r"[^0-9a-fA-F]", "", mac).upper()
    if len(clean) == 12:
        return ":".join(clean[i:i+2] for i in range(0, 12, 2))
    return mac.strip().upper()


def mask_api_key(key: Optional[str]) -> str:
    """Mask sensitive API key to prevent frontend exposure while keeping hint."""
    if not key:
        return ""
    if len(key) <= 12:
        return "***"
    return f"{key[:8]}...{key[-4:]}"


DEFAULT_AGENTS = [
    {
        "id": "agent_101",
        "name": "Desk Companion (ESP32-S3)",
        "role": "Nova",
        "status": "online",
        "language": "vi",
        "tool_policy": "full_control",
        "prompt": (
            "Bạn là Nova, trợ lý giọng nói thông minh cho gia đình. "
            "Trả lời bằng tiếng Việt ngắn gọn, súc tích (1-2 câu), tự nhiên để phát âm qua loa TTS. "
            "Khi người dùng hỏi về cảm biến, thông số môi trường (nhiệt độ, độ ẩm, CO2, áp suất) "
            "hoặc yêu cầu điều khiển thiết bị, hãy sử dụng các công cụ ThingsBoard tương ứng "
            "(list_devices, get_telemetry, send_rpc)."
        ),
        "tts": {
            "voice": "vi_female_linh",
            "speed": "standard"
        },
        "llm": {
            "model": "qwen2.5:3b-instruct"
        },
        "integrations": {
            "thingsboard": {
                "host": os.getenv("THINGSBOARD_HOST", "https://codehelpers.tech"),
                "api_key": os.getenv(
                    "THINGSBOARD_API_KEY",
                    "tb_G5TSH2WJsF3g25Q_7jImZwyUpdAYqGtI6cT86c-dMCKy_d8WZ3M3rNjn9zhzOT5Y9AnvV-KKQPpIQChD7qPluA"
                ),
                "display_name": "CodeHelpers IoT Cloud",
                "timeout_seconds": 10.0
            }
        },
        "devices": [
            {
                "mac": "48:27:E2:B1:5A:1C",
                "name": "ESP32-S3 AI Voice Box"
            }
        ],
        "chats": [],
        "memories": [
            {
                "id": "mem_01",
                "content": "Người dùng thích câu trả lời ngắn gọn, ưu tiên nhiệt độ phòng khách và điều khiển rèm cửa.",
                "createdAt": "Hôm nay",
                "type": "context"
            }
        ]
    },
    {
        "id": "agent_102",
        "name": "Living Room Monitor (Virtual ESP32)",
        "role": "Luna",
        "status": "online",
        "language": "en",
        "tool_policy": "read_only_telemetry",
        "prompt": (
            "You are Luna, an environmental monitoring and room atmosphere assistant. "
            "Answer strictly in English in 1 concise sentence. "
            "You have read-only access to query sensors and cannot perform RPC control or switch state changes."
        ),
        "tts": {
            "voice": "en_US-lessac-medium",
            "speed": "standard"
        },
        "llm": {
            "model": "qwen2.5:3b-instruct"
        },
        "integrations": {
            "thingsboard": {
                "host": os.getenv("THINGSBOARD_HOST", "https://codehelpers.tech"),
                "api_key": os.getenv(
                    "THINGSBOARD_API_KEY",
                    "tb_G5TSH2WJsF3g25Q_7jImZwyUpdAYqGtI6cT86c-dMCKy_d8WZ3M3rNjn9zhzOT5Y9AnvV-KKQPpIQChD7qPluA"
                ),
                "display_name": "CodeHelpers IoT Cloud (Read-Only)",
                "timeout_seconds": 10.0
            }
        },
        "devices": [
            {
                "mac": "00:11:22:33:44:55",
                "name": "Virtual ESP32 Test Node"
            }
        ],
        "chats": [],
        "memories": []
    },
    {
        "id": "agent_103",
        "name": "Virtual PC Tester (Browser/Microphone)",
        "role": "Aero",
        "status": "online",
        "language": "vi",
        "tool_policy": "full_control",
        "prompt": (
            "Bạn là Aero, trợ lý giọng nói trên máy tính (PC Virtual Companion). "
            "Trả lời bằng tiếng Việt ngắn gọn, súc tích (1-2 câu), tự nhiên để phát âm qua loa máy tính. "
            "Bạn hỗ trợ người dùng kiểm thử đàm thoại trực tiếp qua microphone và loa máy tính, "
            "kiểm tra nhận diện giọng nói và tích hợp nhà thông minh ThingsBoard."
        ),
        "tts": {
            "voice": "vi_female_linh",
            "speed": "standard"
        },
        "llm": {
            "model": "qwen2.5:3b-instruct"
        },
        "integrations": {
            "thingsboard": {
                "host": os.getenv("THINGSBOARD_HOST", "https://codehelpers.tech"),
                "api_key": os.getenv(
                    "THINGSBOARD_API_KEY",
                    "tb_G5TSH2WJsF3g25Q_7jImZwyUpdAYqGtI6cT86c-dMCKy_d8WZ3M3rNjn9zhzOT5Y9AnvV-KKQPpIQChD7qPluA"
                ),
                "display_name": "CodeHelpers IoT Cloud",
                "timeout_seconds": 10.0
            }
        },
        "devices": [
            {
                "mac": "02:00:00:00:00:01",
                "name": "PC Virtual Microphone & Speaker"
            }
        ],
        "chats": [],
        "memories": []
    }
]


class PlatformStore:
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.agents: Dict[str, Dict[str, Any]] = {}
        self.device_to_agent: Dict[str, str] = {}
        self.load()

    def load(self):
        if PROFILES_FILE.exists():
            try:
                with open(PROFILES_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    self.agents = {a["id"]: a for a in raw}
            except Exception as e:
                logger.error("Failed to load profiles file: %s", e)
                self.agents = {a["id"]: a for a in DEFAULT_AGENTS}
        else:
            self.agents = {a["id"]: a for a in DEFAULT_AGENTS}
            self.save()

        # Rebuild device_to_agent map
        self.device_to_agent = {}
        for agent_id, agent in self.agents.items():
            for dev in agent.get("devices", []):
                mac = normalize_mac(dev.get("mac", ""))
                if mac:
                    self.device_to_agent[mac] = agent_id

        logger.info("Loaded %d agent profile(s) and %d device binding(s)", len(self.agents), len(self.device_to_agent))

    def save(self):
        try:
            with open(PROFILES_FILE, "w", encoding="utf-8") as f:
                json.dump(list(self.agents.values()), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Failed to save profiles: %s", e)

    def get_agent_for_device(self, mac_address: str) -> Optional[Dict[str, Any]]:
        norm = normalize_mac(mac_address)
        # Check active authenticated devices in SQLite first
        try:
            for auth_dev in device_db.list_authenticated_devices():
                if normalize_mac(auth_dev.get("mac_address", "")) == norm:
                    agent_id = auth_dev.get("agent_id")
                    if agent_id and agent_id in self.agents:
                        return self.agents[agent_id]
        except Exception as e:
            logger.warning("Error checking authenticated devices: %s", e)

        # Fallback to manual MAC binding map
        agent_id = self.device_to_agent.get(norm)
        if agent_id and agent_id in self.agents:
            return self.agents[agent_id]
        return None

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        return self.agents.get(agent_id)

    def list_agents(self) -> List[Dict[str, Any]]:
        return list(self.agents.values())

    def list_safe_agents(self) -> List[Dict[str, Any]]:
        """Formats agent profiles into complete console schema with masked API keys."""
        res = []
        for agent in self.agents.values():
            raw_devices = agent.get("devices", [])
            devs = []
            for d in raw_devices:
                mac = normalize_mac(d.get("mac", ""))
                devs.append({
                    "id": f"dev_{mac.replace(':', '')}",
                    "name": d.get("name", "ESP32 Device"),
                    "mac_address": mac,
                    "status": "online",
                    "firmware_version": "v2.1.8",
                    "is_auth": False,
                    "ota_enabled": True
                })

            tb_cfg = agent.get("integrations", {}).get("thingsboard", {})
            masked_tb = {
                "host": tb_cfg.get("host", "https://codehelpers.tech"),
                "api_key": mask_api_key(tb_cfg.get("api_key")),
                "display_name": tb_cfg.get("display_name", "ThingsBoard IoT"),
                "is_configured": bool(tb_cfg.get("api_key")),
                "timeout_seconds": tb_cfg.get("timeout_seconds", 10.0)
            }

            res.append({
                "id": agent["id"],
                "name": agent["name"],
                "role": agent.get("role", "Assistant"),
                "model": agent.get("llm", {}).get("model", "qwen2.5:3b-instruct"),
                "voice": agent.get("tts", {}).get("voice", "vi_female_linh"),
                "status": agent.get("status", "online"),
                "deviceCount": len(devs),
                "onlineDeviceCount": len(devs),
                "lastSeen": "Just now",
                "tool_policy": agent.get("tool_policy", "full_control"),
                "devices": devs,
                "chats": agent.get("chats", []),
                "config": {
                    "language": agent.get("language", "vi"),
                    "ttsVoice": agent.get("tts", {}).get("voice", "vi_female_linh"),
                    "customCharacter": True,
                    "character": agent.get("prompt", ""),
                    "asrSpeed": "standard",
                    "ttsSpeechSpeed": agent.get("tts", {}).get("speed", "standard"),
                    "ttsPitch": "standard",
                    "llmModel": agent.get("llm", {}).get("model", "qwen2.5:3b-instruct"),
                    "knowledgeBaseId": agent.get("config", {}).get("knowledgeBaseId", ""),
                    "teenMode": False,
                    "memoryEnabled": len(agent.get("memories", [])) > 0,
                    "memories": agent.get("memories", []),
                    "mcpEndpoints": agent.get("config", {}).get("mcpEndpoints", ["thingsboard-tools"]),
                    "speakers": agent.get("speakers", []),
                    "tool_policy": agent.get("tool_policy", "full_control"),
                    "integrations": {
                        "thingsboard": masked_tb
                    }
                },
                "integrations": {
                    "thingsboard": masked_tb
                }
            })
        return res

    def create_agent(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Creates a new agent profile."""
        agent_id = data.get("id") or f"agent_{int(time.time())}"
        name = data.get("name") or "New Agent"
        role = data.get("role") or "Assistant"
        prompt = data.get("prompt") or data.get("config", {}).get("character", "")
        language = data.get("language") or data.get("config", {}).get("language", "vi")
        voice = data.get("ttsVoice") or data.get("config", {}).get("ttsVoice", "vi_female_linh")
        model = data.get("llmModel") or data.get("config", {}).get("llmModel", "qwen2.5:3b-instruct")
        tool_policy = data.get("tool_policy") or "full_control"

        tb_in = data.get("integrations", {}).get("thingsboard", {})
        integrations = {
            "thingsboard": {
                "host": tb_in.get("host", "https://codehelpers.tech"),
                "api_key": tb_in.get("api_key", ""),
                "display_name": tb_in.get("display_name", "ThingsBoard IoT"),
                "timeout_seconds": 10.0
            }
        }

        new_agent = {
            "id": agent_id,
            "name": name,
            "role": role,
            "status": "online",
            "language": language,
            "tool_policy": tool_policy,
            "prompt": prompt or f"Bạn là {role}, trợ lý giọng nói thông minh.",
            "tts": {
                "voice": voice,
                "speed": "standard"
            },
            "llm": {
                "model": model
            },
            "integrations": integrations,
            "devices": [],
            "chats": [],
            "memories": []
        }
        self.agents[agent_id] = new_agent
        self.save()
        return new_agent

    def update_agent(self, agent_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Updates an existing agent profile, preserving sensitive credentials if masked."""
        if agent_id not in self.agents:
            raise ValueError(f"Agent '{agent_id}' does not exist.")

        agent = self.agents[agent_id]
        if "name" in data:
            agent["name"] = data["name"]
        if "role" in data:
            agent["role"] = data["role"]
        if "tool_policy" in data:
            agent["tool_policy"] = data["tool_policy"]

        # Config fields (from ConfigModal or direct payload)
        cfg = data.get("config", {})
        if "language" in cfg:
            agent["language"] = cfg["language"]
        elif "language" in data:
            agent["language"] = data["language"]

        if "character" in cfg:
            agent["prompt"] = cfg["character"]
        elif "prompt" in data:
            agent["prompt"] = data["prompt"]

        if "ttsVoice" in cfg:
            agent.setdefault("tts", {})["voice"] = cfg["ttsVoice"]
        if "ttsSpeechSpeed" in cfg:
            agent.setdefault("tts", {})["speed"] = cfg["ttsSpeechSpeed"]
        if "llmModel" in cfg:
            agent.setdefault("llm", {})["model"] = cfg["llmModel"]
        if "memories" in cfg:
            agent["memories"] = cfg["memories"]
        if "mcpEndpoints" in cfg:
            agent.setdefault("config", {})["mcpEndpoints"] = cfg["mcpEndpoints"]

        # Tool policy inside config
        if "tool_policy" in cfg:
            agent["tool_policy"] = cfg["tool_policy"]

        # Update Integrations (ThingsBoard)
        tb_input = data.get("integrations", {}).get("thingsboard") or cfg.get("integrations", {}).get("thingsboard")
        if tb_input:
            existing_tb = agent.setdefault("integrations", {}).setdefault("thingsboard", {})
            if tb_input.get("host"):
                existing_tb["host"] = tb_input["host"].rstrip("/")
            if tb_input.get("display_name"):
                existing_tb["display_name"] = tb_input["display_name"]
            # Only update API key if user supplied a new unmasked key
            raw_key = tb_input.get("api_key")
            if raw_key and "..." not in raw_key and raw_key != "***":
                existing_tb["api_key"] = raw_key.strip()

        self.save()
        # Sync active profile to agent_profile.json
        try:
            self.sync_to_agent_profile_json(agent_id)
        except Exception as e:
            logger.warning("Failed to sync updated profile to agent_profile.json: %s", e)

        return agent

    def delete_agent(self, agent_id: str):
        """Deletes an agent profile and cleans up device mappings."""
        if agent_id not in self.agents:
            return
        del self.agents[agent_id]
        # Rebuild device map
        self.device_to_agent = {
            mac: a_id for mac, a_id in self.device_to_agent.items() if a_id != agent_id
        }
        self.save()

    def list_devices(self) -> List[Dict[str, Any]]:
        """Aggregates all registered devices across authenticated hardware and manual bindings."""
        devices = []
        seen_macs = set()

        # 1. Authenticated physical devices from persistent SQLite DB
        try:
            for auth_d in device_db.list_authenticated_devices():
                norm = normalize_mac(auth_d.get("mac_address", ""))
                agent_id = auth_d.get("agent_id", "")
                agent = self.agents.get(agent_id, {})
                seen_macs.add(norm)
                devices.append({
                    "id": auth_d.get("device_id") or f"dev_{norm.replace(':', '')}",
                    "device_id": auth_d.get("device_id"),
                    "name": auth_d.get("name", "ESP32 Device"),
                    "mac_address": norm,
                    "agent_id": agent_id,
                    "agent_name": agent.get("name", "Unknown Agent"),
                    "agent_role": agent.get("role", "Assistant"),
                    "status": auth_d.get("status", "online"),
                    "last_seen": auth_d.get("last_seen", "Just now"),
                    "hardware_model": auth_d.get("hardware_model", "ESP32-S3"),
                    "firmware_version": auth_d.get("firmware_version", "v2.1.8"),
                    "registration_status": "authenticated",
                    "registered_at": auth_d.get("registered_at"),
                    "is_auth": True,
                    "ota_enabled": True
                })
        except Exception as e:
            logger.warning("Failed to load authenticated devices from SQLite: %s", e)

        # 2. Manual MAC bindings from agents.json
        for agent_id, agent in self.agents.items():
            for d in agent.get("devices", []):
                norm = normalize_mac(d.get("mac", ""))
                if norm in seen_macs:
                    continue
                seen_macs.add(norm)
                devices.append({
                    "id": f"dev_{norm.replace(':', '')}",
                    "device_id": f"dev_{norm.replace(':', '')}",
                    "name": d.get("name", "ESP32 Device"),
                    "mac_address": norm,
                    "agent_id": agent_id,
                    "agent_name": agent.get("name", "Unknown Agent"),
                    "agent_role": agent.get("role", "Assistant"),
                    "status": "online",
                    "last_seen": "Just now",
                    "hardware_model": "ESP32-S3 (Manual)",
                    "firmware_version": "v2.1.8",
                    "registration_status": "manual_mac",
                    "registered_at": None,
                    "is_auth": False,
                    "ota_enabled": True
                })
        return devices

    def unbind_device(self, mac_address: str):
        """Removes a device binding from whatever agent currently owns it and revokes credentials."""
        norm = normalize_mac(mac_address)
        # Revoke in SQLite DB if present
        try:
            device_db.unbind_device_by_identifier(norm)
            device_db.unbind_device_by_identifier(mac_address)
        except Exception as e:
            logger.warning("Error unbinding device in SQLite: %s", e)

        for agent in self.agents.values():
            devs = agent.get("devices", [])
            filtered = [d for d in devs if normalize_mac(d.get("mac", "")) != norm]
            if len(filtered) != len(devs):
                agent["devices"] = filtered
                break
        if norm in self.device_to_agent:
            del self.device_to_agent[norm]
        self.save()
        logger.info("Unbound device %s from platform", norm)

    def bind_device(self, mac_address: str, agent_id: str, device_name: str = "ESP32 Device"):
        norm = normalize_mac(mac_address)
        if agent_id not in self.agents:
            raise ValueError(f"Agent '{agent_id}' does not exist.")

        agent = self.agents[agent_id]
        devices = agent.setdefault("devices", [])
        # Remove existing if present
        devices = [d for d in devices if normalize_mac(d.get("mac", "")) != norm]
        devices.append({"mac": norm, "name": device_name})
        agent["devices"] = devices

        self.device_to_agent[norm] = agent_id
        self.save()
        logger.info("Bound device %s to agent %s (%s)", norm, agent_id, device_name)

    def record_chat(self, mac_address: str, session_id: str, chat_type: int, content: str):
        agent = self.get_agent_for_device(mac_address)
        if not agent:
            return
        chats = agent.setdefault("chats", [])
        role = "assistant" if chat_type == 2 else "user"
        chats.append({
            "session_id": session_id,
            "mac": normalize_mac(mac_address),
            "role": role,
            "content": content,
            "timestamp": int(os.environ.get("MOCK_TIMESTAMP", 0)) or None
        })
        # Keep latest 50 messages
        if len(chats) > 50:
            agent["chats"] = chats[-50:]
        self.save()

    def sync_to_agent_profile_json(self, agent_id: str, output_path: str = "agent_profile.json"):
        """Exports the active Agent Profile into agent_profile.json for ThingsBoard MCP Server."""
        agent = self.get_agent(agent_id)
        if not agent:
            return
        profile_data = {
            "id": agent["id"],
            "name": agent["name"],
            "role": agent.get("role", "Assistant"),
            "integrations": agent.get("integrations", {}),
            "config": {
                "language": agent.get("language", "vi"),
                "llmModel": agent.get("llm", {}).get("model", "qwen2.5:3b-instruct"),
                "mcpEndpoints": ["thingsboard-tools"]
            }
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(profile_data, f, ensure_ascii=False, indent=2)
        logger.info("Exported active agent profile '%s' to %s", agent_id, output_path)


# Global singleton instance
platform_store = PlatformStore()
