"""Integration tests for config loading."""

import unittest

from src.config import load_config


class TestIntegration(unittest.TestCase):
    """Test config loading."""

    def test_config_loading_defaults(self):
        """Test loading config with defaults."""
        config = load_config("nonexistent.json", {})

        self.assertEqual(config.pool_size, 25)
        self.assertEqual(config.sim_count, 10000)
        # Auto risk profile gets converted based on pool size (25 -> balanced)
        self.assertEqual(config.risk_profile, "balanced")

    def test_config_loading_with_overrides(self):
        """Test loading config with CLI overrides."""
        overrides = {
            "pool_size": 50,
            "sim_count": 5000,
            "risk_profile": "aggressive"
        }

        config = load_config("nonexistent.json", overrides)

        self.assertEqual(config.pool_size, 50)
        self.assertEqual(config.sim_count, 5000)
        self.assertEqual(config.risk_profile, "aggressive")


if __name__ == '__main__':
    unittest.main()
