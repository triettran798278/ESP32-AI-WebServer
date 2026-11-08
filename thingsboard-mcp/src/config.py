"""
Configuration and Agent Profile Integration Resolver.
Resolves ThingsBoard API credentials dynamically from the active Agent Profile.
Never hardcodes credentials or device IDs.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("thingsboard_mcp.config")


class ThingsBoardConfig(BaseModel):
    """Resolved ThingsBoard connection parameters."""
    host: str = Field(description="ThingsBoard base URL, e.g. http://localhost:8080")
    api_key: Optional[str] = Field(default=None, description="ThingsBoard REST API Key (tb_...)")
    username: Optional[str] = Field(default=None, description="Tenant username / email")
    password: Optional[str] = Field(default=None, description="Tenant password")
    token: Optional[str] = Field(default=None, description="Existing JWT bearer token")
    timeout_seconds: float = Field(default=10.0, description="HTTP request timeout in seconds")


def _extract_tb_section(profile_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Search for ThingsBoard integration settings in standard Agent Profile structures:
    1. profile['integrations']['thingsboard']
    2. profile['config']['integrations']['thingsboard']
    3. profile['thingsboard']
    """
    if not isinstance(profile_data, dict):
        return None

    # Check top-level 'integrations.thingsboard'
    integrations = profile_data.get("integrations")
    if isinstance(integrations, dict) and "thingsboard" in integrations:
        return integrations["thingsboard"]

    # Check nested under 'config.integrations.thingsboard'
    config = profile_data.get("config")
    if isinstance(config, dict):
        cfg_integrations = config.get("integrations")
        if isinstance(cfg_integrations, dict) and "thingsboard" in cfg_integrations:
            return cfg_integrations["thingsboard"]
        if "thingsboard" in config:
            return config["thingsboard"]

    # Direct 'thingsboard' key
    if "thingsboard" in profile_data:
        return profile_data["thingsboard"]

    return None


def resolve_thingsboard_config(
    profile_path: Optional[str] = None,
    profile_dict: Optional[Dict[str, Any]] = None,
) -> ThingsBoardConfig:
    """
    Resolve ThingsBoard configuration with the following priority:
    1. Explicitly provided `profile_dict`
    2. Explicitly provided `profile_path` file
    3. Environment variable `AGENT_PROFILE_PATH` file
    4. Default profile file `./agent_profile.json` if present
    5. Environment variables (TB_HOST / THINGSBOARD_HOST, TB_API_KEY / THINGSBOARD_API_KEY, etc.)

    Raises:
        ValueError: If neither a valid agent profile integration nor environment variables
                    provide sufficient credentials.
    """
    raw_tb: Dict[str, Any] = {}
    source_name = "none"

    # 1. Profile Dict
    if profile_dict:
        extracted = _extract_tb_section(profile_dict)
        if extracted:
            raw_tb = extracted
            source_name = f"profile dict (agent: {profile_dict.get('id', profile_dict.get('name', 'unnamed'))})"

    # 2. Profile File (Explicit, Env Var, or Default)
    if not raw_tb:
        target_path = profile_path or os.getenv("AGENT_PROFILE_PATH")
        if not target_path and Path("agent_profile.json").is_file():
            target_path = "agent_profile.json"

        if target_path:
            p = Path(target_path)
            if p.is_file():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    extracted = _extract_tb_section(data)
                    if extracted:
                        raw_tb = extracted
                        source_name = f"profile file ({target_path})"
                    else:
                        logger.warning("Profile file %s has no 'integrations.thingsboard' section", target_path)
                except Exception as e:
                    logger.error("Failed to read agent profile from %s: %s", target_path, e)

    # 3. Fallback to Environment Variables
    host = raw_tb.get("host") or raw_tb.get("url") or os.getenv("THINGSBOARD_HOST") or os.getenv("TB_HOST")
    api_key = raw_tb.get("api_key") or raw_tb.get("apiKey") or os.getenv("THINGSBOARD_API_KEY") or os.getenv("TB_API_KEY")
    username = raw_tb.get("username") or raw_tb.get("email") or os.getenv("THINGSBOARD_USERNAME") or os.getenv("TB_USERNAME")
    password = raw_tb.get("password") or os.getenv("THINGSBOARD_PASSWORD") or os.getenv("TB_PASSWORD")
    token = raw_tb.get("token") or raw_tb.get("jwt_token") or os.getenv("THINGSBOARD_TOKEN") or os.getenv("TB_TOKEN")
    timeout = raw_tb.get("timeout_seconds") or raw_tb.get("timeout") or os.getenv("THINGSBOARD_TIMEOUT", 10.0)

    try:
        timeout_float = float(timeout)
    except (ValueError, TypeError):
        timeout_float = 10.0

    if not host:
        raise ValueError(
            "ThingsBoard host URL is not configured in the active Agent Profile or environment. "
            "Please configure 'integrations.thingsboard.host' in your agent profile or set TB_HOST."
        )

    # Validate that at least one auth mechanism is present
    has_auth = bool(api_key or token or (username and password))
    if not has_auth:
        raise ValueError(
            "ThingsBoard credentials not found in active Agent Profile. "
            "Please provide 'api_key', 'token', or 'username'/'password' in the profile's "
            "ThingsBoard integration settings or set TB_API_KEY."
        )

    clean_host = host.rstrip("/")
    logger.info("ThingsBoard configuration resolved successfully from %s (host: %s)", source_name, clean_host)

    return ThingsBoardConfig(
        host=clean_host,
        api_key=api_key,
        username=username,
        password=password,
        token=token,
        timeout_seconds=timeout_float,
    )
