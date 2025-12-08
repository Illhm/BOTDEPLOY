
import unittest
import os
from unittest.mock import patch, MagicMock

# Create a dummy config module to satisfy run.py import
import sys
from types import ModuleType
config_mock = ModuleType("config")
config_mock.BOT_TOKEN = "123456789:TEST_TOKEN"
config_mock.TEMP_DIR = "/tmp"
config_mock.LOG_DIR = "/tmp"
config_mock.VENV_DIR = "/tmp"
sys.modules["config"] = config_mock

# We also need to mock telebot to avoid connection attempts
sys.modules["telebot"] = MagicMock()
sys.modules["telebot.async_telebot"] = MagicMock()
sys.modules["flask"] = MagicMock()

import run

class TestSecurity(unittest.TestCase):

    def setUp(self):
        self.process_manager = run.ProcessManager()

    def test_get_sanitized_env(self):
        """Test that _get_sanitized_env removes sensitive variables."""

        # Setup environment with sensitive and safe variables
        test_env = {
            "PATH": "/usr/bin",
            "LANG": "en_US.UTF-8",
            "BOT_TOKEN": "secret_token",
            "API_ID": "secret_id",
            "API_HASH": "secret_hash",
            "SHUTDOWN_TOKEN": "secret_shutdown",
            "TELEGRAM_API_ID": "secret_tg_id",
            "MY_SECRET_KEY": "super_secret",
            "DB_PASSWORD": "password123",
            "AWS_CREDENTIALS": "aws_creds",
            "SAFE_VAR": "safe_value"
        }

        with patch.dict(os.environ, test_env, clear=True):
            sanitized_env = self.process_manager._get_sanitized_env()

            # Verify safe variables are present
            self.assertIn("PATH", sanitized_env)
            self.assertEqual(sanitized_env["PATH"], "/usr/bin")
            self.assertIn("SAFE_VAR", sanitized_env)
            self.assertEqual(sanitized_env["SAFE_VAR"], "safe_value")

            # Verify explicit sensitive keys are removed
            self.assertNotIn("BOT_TOKEN", sanitized_env)
            self.assertNotIn("API_ID", sanitized_env)
            self.assertNotIn("API_HASH", sanitized_env)
            self.assertNotIn("SHUTDOWN_TOKEN", sanitized_env)
            self.assertNotIn("TELEGRAM_API_ID", sanitized_env)

            # Verify heuristic removal
            self.assertNotIn("MY_SECRET_KEY", sanitized_env)
            self.assertNotIn("DB_PASSWORD", sanitized_env)
            self.assertNotIn("AWS_CREDENTIALS", sanitized_env)

if __name__ == "__main__":
    unittest.main()
