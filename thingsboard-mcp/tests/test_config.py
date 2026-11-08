"""
Unit tests for ThingsBoard Agent Profile configuration resolver.
"""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from src.config import resolve_thingsboard_config, ThingsBoardConfig


class TestThingsBoardConfig(unittest.TestCase):

    def test_resolve_from_profile_dict(self):
        profile = {
            "id": "agent_test",
            "name": "Test Agent",
            "integrations": {
                "thingsboard": {
                    "host": "http://192.168.1.100:8080",
                    "api_key": "tb_test_key_12345",
                    "timeout_seconds": 15
                }
            }
        }
        cfg = resolve_thingsboard_config(profile_dict=profile)
        self.assertEqual(cfg.host, "http://192.168.1.100:8080")
        self.assertEqual(cfg.api_key, "tb_test_key_12345")
        self.assertEqual(cfg.timeout_seconds, 15.0)

    def test_resolve_from_nested_config_profile_dict(self):
        profile = {
            "id": "agent_test_nested",
            "config": {
                "integrations": {
                    "thingsboard": {
                        "host": "http://localhost:8081",
                        "username": "operator@iot.local",
                        "password": "secret_password"
                    }
                }
            }
        }
        cfg = resolve_thingsboard_config(profile_dict=profile)
        self.assertEqual(cfg.host, "http://localhost:8081")
        self.assertEqual(cfg.username, "operator@iot.local")
        self.assertEqual(cfg.password, "secret_password")

    def test_resolve_from_profile_file(self):
        profile_content = {
            "id": "agent_file",
            "integrations": {
                "thingsboard": {
                    "host": "http://thingsboard:8080/",
                    "token": "jwt_mock_token"
                }
            }
        }
        with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as f:
            json.dump(profile_content, f)
            temp_path = f.name

        try:
            cfg = resolve_thingsboard_config(profile_path=temp_path)
            self.assertEqual(cfg.host, "http://thingsboard:8080")  # Strips trailing slash
            self.assertEqual(cfg.token, "jwt_mock_token")
        finally:
            os.remove(temp_path)

    @patch.dict(os.environ, {
        "TB_HOST": "http://tb-env:8080",
        "TB_API_KEY": "tb_env_key"
    }, clear=True)
    def test_resolve_from_environment(self):
        cfg = resolve_thingsboard_config()
        self.assertEqual(cfg.host, "http://tb-env:8080")
        self.assertEqual(cfg.api_key, "tb_env_key")

    def test_missing_host_raises_error(self):
        empty_profile = {"integrations": {"thingsboard": {"api_key": "some_key"}}}
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                resolve_thingsboard_config(profile_dict=empty_profile)
            self.assertIn("host URL is not configured", str(ctx.exception))

    def test_missing_credentials_raises_error(self):
        no_auth_profile = {"integrations": {"thingsboard": {"host": "http://localhost:8080"}}}
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                resolve_thingsboard_config(profile_dict=no_auth_profile)
            self.assertIn("credentials not found in active Agent Profile", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
