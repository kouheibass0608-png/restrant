import tempfile
import unittest
from pathlib import Path

from tablecheck_watcher.state import State, diff_new_slots, load_state, save_state


class DiffNewSlotsTest(unittest.TestCase):
    def test_new_date_appears(self):
        new = diff_new_slots({}, {"2026-09-01": ["18:00"]})
        self.assertEqual(new, {"2026-09-01": ["18:00"]})

    def test_new_slot_on_existing_date(self):
        new = diff_new_slots(
            {"2026-09-01": ["18:00"]},
            {"2026-09-01": ["12:00", "18:00"]},
        )
        self.assertEqual(new, {"2026-09-01": ["12:00"]})

    def test_no_change(self):
        cur = {"2026-09-01": ["18:00"]}
        self.assertEqual(diff_new_slots(cur, cur), {})

    def test_slot_disappearing_is_not_reported(self):
        new = diff_new_slots({"2026-09-01": ["12:00", "18:00"]}, {"2026-09-01": ["18:00"]})
        self.assertEqual(new, {})

    def test_reappearing_slot_is_reported(self):
        # 一度消えて再度出た枠は (前回状態に無いので) 通知対象
        new = diff_new_slots({"2026-09-01": ["18:00"]}, {"2026-09-01": ["12:00", "18:00"]})
        self.assertEqual(new, {"2026-09-01": ["12:00"]})

    def test_result_is_sorted(self):
        new = diff_new_slots({}, {"2026-09-01": ["18:30", "12:00", "18:00"]})
        self.assertEqual(new["2026-09-01"], ["12:00", "18:00", "18:30"])


class StateRoundtripTest(unittest.TestCase):
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            state = State(
                availability={"2026-09-01": ["18:00", "12:00"]},
                consecutive_failures=3,
                failure_notified=True,
                last_checked_at="2026-08-09T21:00:00+09:00",
            )
            save_state(path, state)
            loaded = load_state(path)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.availability, {"2026-09-01": ["12:00", "18:00"]})
            self.assertEqual(loaded.consecutive_failures, 3)
            self.assertTrue(loaded.failure_notified)
            self.assertEqual(loaded.last_checked_at, "2026-08-09T21:00:00+09:00")

    def test_missing_file_returns_none(self):
        self.assertIsNone(load_state("/nonexistent/state.json"))

    def test_writing_same_state_produces_identical_bytes(self):
        # 空き状況に変化がない実行で state.json が書き換わらない
        # (= 余計なコミットが発生しない) ことを保証する。
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            state = State(
                availability={"2026-09-02": ["19:00"], "2026-09-01": ["18:30", "18:00"]},
                last_checked_at="2026-08-09T21:00:00+09:00",
            )
            save_state(path, state)
            first = path.read_bytes()
            save_state(path, load_state(path))
            self.assertEqual(path.read_bytes(), first)

    def test_corrupt_file_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            path.write_text("{broken json", encoding="utf-8")
            self.assertIsNone(load_state(path))


if __name__ == "__main__":
    unittest.main()
