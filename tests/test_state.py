import tempfile
import unittest
from pathlib import Path

from tablecheck_watcher.state import State, diff_new_slots, load_state, save_state


class DiffNewSlotsTest(unittest.TestCase):
    def test_new_date_appears(self):
        new = diff_new_slots({}, {2: {"2026-09-01": ["18:00"]}})
        self.assertEqual(new, {2: {"2026-09-01": ["18:00"]}})

    def test_new_slot_on_existing_date(self):
        new = diff_new_slots(
            {2: {"2026-09-01": ["18:00"]}},
            {2: {"2026-09-01": ["12:00", "18:00"]}},
        )
        self.assertEqual(new, {2: {"2026-09-01": ["12:00"]}})

    def test_no_change(self):
        cur = {2: {"2026-09-01": ["18:00"]}}
        self.assertEqual(diff_new_slots(cur, cur), {})

    def test_slot_disappearing_is_not_reported(self):
        new = diff_new_slots(
            {2: {"2026-09-01": ["12:00", "18:00"]}}, {2: {"2026-09-01": ["18:00"]}}
        )
        self.assertEqual(new, {})

    def test_result_is_sorted(self):
        new = diff_new_slots({}, {2: {"2026-09-01": ["18:30", "12:00", "18:00"]}})
        self.assertEqual(new[2]["2026-09-01"], ["12:00", "18:00", "18:30"])

    def test_party_sizes_are_tracked_independently(self):
        # 2名は変化なし、1名だけ新しく空いたケース
        prev = {1: {}, 2: {"2026-09-01": ["18:00"]}}
        cur = {1: {"2026-09-01": ["19:00"]}, 2: {"2026-09-01": ["18:00"]}}
        self.assertEqual(diff_new_slots(prev, cur), {1: {"2026-09-01": ["19:00"]}})

    def test_new_party_size_is_all_new(self):
        # 監視人数を追加した直後は、その人数の空きがすべて新規扱いになる
        prev = {2: {"2026-09-01": ["18:00"]}}
        cur = {1: {"2026-09-01": ["18:00"]}, 2: {"2026-09-01": ["18:00"]}}
        self.assertEqual(diff_new_slots(prev, cur), {1: {"2026-09-01": ["18:00"]}})


class StateRoundtripTest(unittest.TestCase):
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            state = State(
                availability={2: {"2026-09-01": ["18:00", "12:00"]}, 1: {}},
                consecutive_failures=3,
                failure_notified=True,
                last_checked_at="2026-08-09T21:00:00+09:00",
            )
            save_state(path, state)
            loaded = load_state(path)
            self.assertIsNotNone(loaded)
            # JSON のキーは文字列になるが、読み込み時に int へ戻る
            self.assertEqual(loaded.availability, {1: {}, 2: {"2026-09-01": ["12:00", "18:00"]}})
            self.assertEqual(loaded.consecutive_failures, 3)
            self.assertTrue(loaded.failure_notified)
            self.assertEqual(loaded.last_checked_at, "2026-08-09T21:00:00+09:00")

    def test_legacy_flat_format_is_rejected(self):
        # 人数別になる前の形式は「記録なし」として扱い、初回実行として再スタートする
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            path.write_text(
                '{"availability": {"2026-09-01": ["18:00"]}, "consecutive_failures": 0}',
                encoding="utf-8",
            )
            self.assertIsNone(load_state(path))

    def test_missing_file_returns_none(self):
        self.assertIsNone(load_state("/nonexistent/state.json"))

    def test_writing_same_state_produces_identical_bytes(self):
        # 空き状況に変化がない実行で state.json が書き換わらない
        # (= 余計なコミットが発生しない) ことを保証する。
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            state = State(
                availability={
                    2: {"2026-09-02": ["19:00"], "2026-09-01": ["18:30", "18:00"]},
                    1: {},
                },
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
