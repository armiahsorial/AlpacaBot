import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trading_bot.config import Settings


class SettingsTests(unittest.TestCase):
    def test_from_env_requires_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "GEX_API_KEY"):
                Settings.from_env(None)

    def test_from_env_reads_values(self):
        env = {
            "GEX_API_KEY": "abc123",
            "GEX_BASE_URL": "https://example.test/",
            "GEX_USER_AGENT": "test-client/1.0",
            "GEX_TIMEOUT_SECONDS": "5",
        }

        with patch.dict(os.environ, env, clear=True):
            settings = Settings.from_env()

        self.assertEqual(settings.api_key, "abc123")
        self.assertEqual(settings.base_url, "https://example.test")
        self.assertEqual(settings.user_agent, "test-client/1.0")
        self.assertEqual(settings.timeout_seconds, 5.0)

    def test_from_env_reads_dotenv_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "# local settings",
                        "GEX_API_KEY=from-file",
                        "export GEX_BASE_URL=https://dotenv.example.test/",
                        'GEX_USER_AGENT="dotenv-client/1.0"',
                        "GEX_TIMEOUT_SECONDS='10'",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                settings = Settings.from_env(env_file)

        self.assertEqual(settings.api_key, "from-file")
        self.assertEqual(settings.base_url, "https://dotenv.example.test")
        self.assertEqual(settings.user_agent, "dotenv-client/1.0")
        self.assertEqual(settings.timeout_seconds, 10.0)

    def test_environment_overrides_dotenv_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_file = Path(temp_dir) / ".env"
            env_file.write_text("GEX_API_KEY=from-file", encoding="utf-8")

            with patch.dict(os.environ, {"GEX_API_KEY": "from-env"}, clear=True):
                settings = Settings.from_env(env_file)

        self.assertEqual(settings.api_key, "from-env")

if __name__ == "__main__":
    unittest.main()
