import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tablecheck_watcher.config import ConfigError, load_config

MINIMAL = """
[shop]
slug = "joelrobuchon"
name = "テスト店"

[search]
num_people = 4
time_ranges = ["17:00-22:00"]

[notify.ntfy]
topic = "my-topic"
"""


class LoadConfigTest(unittest.TestCase):
    def _write(self, content: str) -> Path:
        d = tempfile.mkdtemp()
        path = Path(d) / "config.toml"
        path.write_text(content, encoding="utf-8")
        return path

    def test_load_minimal(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NTFY_TOPIC", None)
            cfg = load_config(self._write(MINIMAL))
        self.assertEqual(cfg.shop_slug, "joelrobuchon")
        self.assertEqual(cfg.num_people, 4)
        self.assertEqual(cfg.time_ranges, ["17:00-22:00"])
        self.assertEqual(cfg.ntfy.topic, "my-topic")
        self.assertEqual(cfg.ntfy.server, "https://ntfy.sh")
        self.assertEqual(cfg.days_ahead, 60)

    def test_env_overrides_topic(self):
        with mock.patch.dict(os.environ, {"NTFY_TOPIC": "env-topic"}):
            cfg = load_config(self._write(MINIMAL))
        self.assertEqual(cfg.ntfy.topic, "env-topic")

    def test_invalid_time_range_raises(self):
        bad = MINIMAL.replace('["17:00-22:00"]', '["1700-2200"]')
        with self.assertRaises(ConfigError):
            load_config(self._write(bad))

    def test_missing_file_raises(self):
        with self.assertRaises(ConfigError):
            load_config("/nonexistent/config.toml")

    def test_reserve_page_url(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            cfg = load_config(self._write(MINIMAL))
        self.assertEqual(
            cfg.reserve_page_url,
            "https://www.tablecheck.com/ja/shops/joelrobuchon/reserve",
        )


if __name__ == "__main__":
    unittest.main()
