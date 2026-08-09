import datetime as dt
import unittest

from tablecheck_watcher.config import Config
from tablecheck_watcher.watcher import (
    JST,
    build_vacancy_message,
    filter_availability,
    format_date_ja,
    heartbeat_due,
    in_time_ranges,
    reserve_url,
    target_dates,
)


class TimeRangeTest(unittest.TestCase):
    def test_empty_ranges_allow_all(self):
        self.assertTrue(in_time_ranges("03:00", []))

    def test_inside_range(self):
        self.assertTrue(in_time_ranges("18:00", ["17:00-22:00"]))

    def test_boundaries_inclusive(self):
        self.assertTrue(in_time_ranges("17:00", ["17:00-22:00"]))
        self.assertTrue(in_time_ranges("22:00", ["17:00-22:00"]))

    def test_outside_range(self):
        self.assertFalse(in_time_ranges("16:30", ["17:00-22:00"]))

    def test_multiple_ranges(self):
        ranges = ["11:00-15:00", "17:00-22:00"]
        self.assertTrue(in_time_ranges("12:00", ranges))
        self.assertTrue(in_time_ranges("19:00", ranges))
        self.assertFalse(in_time_ranges("16:00", ranges))


class TargetDatesTest(unittest.TestCase):
    def test_days_ahead(self):
        cfg = Config(days_ahead=2)
        today = dt.date(2026, 8, 9)
        self.assertEqual(
            target_dates(cfg, today), ["2026-08-09", "2026-08-10", "2026-08-11"]
        )

    def test_explicit_dates_exclude_past(self):
        cfg = Config(dates=["2026-08-01", "2026-09-15"])
        today = dt.date(2026, 8, 9)
        self.assertEqual(target_dates(cfg, today), ["2026-09-15"])


class FilterAvailabilityTest(unittest.TestCase):
    def test_filters_by_date_and_time(self):
        cfg = Config(days_ahead=30, time_ranges=["17:00-22:00"])
        today = dt.date(2026, 8, 9)
        avail = {
            "2026-08-15": ["12:00", "18:00"],
            "2026-12-31": ["18:00"],  # days_ahead の範囲外
        }
        self.assertEqual(
            filter_availability(avail, cfg, today), {"2026-08-15": ["18:00"]}
        )

    def test_date_with_no_matching_time_dropped(self):
        cfg = Config(days_ahead=30, time_ranges=["17:00-22:00"])
        today = dt.date(2026, 8, 9)
        self.assertEqual(filter_availability({"2026-08-15": ["12:00"]}, cfg, today), {})


class FormattingTest(unittest.TestCase):
    def test_format_date_ja(self):
        self.assertEqual(format_date_ja("2026-08-09"), "8/9(日)")
        self.assertEqual(format_date_ja("2026-08-15"), "8/15(土)")

    def test_reserve_url_with_slot(self):
        cfg = Config(shop_slug="joelrobuchon", locale="ja")
        url = reserve_url(cfg, 2, "2026-08-15", "18:30")
        self.assertEqual(
            url,
            "https://www.tablecheck.com/ja/shops/joelrobuchon/reserve"
            "?num_people=2&start_date=2026-08-15&start_time=66600",
        )

    def test_build_vacancy_message_single_size(self):
        cfg = Config(shop_slug="joelrobuchon", shop_name="テスト店", party_sizes=[2])
        title, msg, click = build_vacancy_message(
            {2: {"2026-08-15": ["18:00", "18:30"], "2026-08-16": ["12:00"]}}, cfg
        )
        self.assertIn("テスト店", title)
        self.assertIn("8/15(土) 18:00・18:30", msg)
        self.assertIn("8/16(日) 12:00", msg)
        self.assertIn("2名", msg)
        # 人数が1種類なら見出しは付けない
        self.assertNotIn("【2名】", msg)
        self.assertIn("num_people=2", click)
        self.assertIn("start_date=2026-08-15", click)
        self.assertIn("start_time=64800", click)

    def test_build_vacancy_message_labels_each_party_size(self):
        cfg = Config(shop_name="テスト店", party_sizes=[1, 2])
        _, msg, click = build_vacancy_message(
            {1: {"2026-08-16": ["19:00"]}, 2: {"2026-08-15": ["18:00"]}}, cfg
        )
        # 人数の多い順に並び、リンクは先頭 (2名) の枠を指す
        self.assertLess(msg.index("【2名】"), msg.index("【1名】"))
        self.assertIn("num_people=2", click)
        self.assertIn("start_date=2026-08-15", click)

    def test_build_vacancy_message_links_to_only_available_size(self):
        # 1名だけ空いた場合はリンクも1名になる
        cfg = Config(shop_name="テスト店", party_sizes=[1, 2])
        _, msg, click = build_vacancy_message({1: {"2026-08-16": ["19:00"]}, 2: {}}, cfg)
        self.assertIn("【1名】", msg)
        self.assertNotIn("【2名】", msg)
        self.assertIn("num_people=1", click)

    def test_build_vacancy_message_truncates(self):
        cfg = Config(shop_name="テスト店", party_sizes=[2])
        many = {2: {f"2026-09-{d:02d}": ["18:00"] for d in range(1, 15)}}
        _, msg, _ = build_vacancy_message(many, cfg)
        self.assertIn("…ほか4日にも空きあり", msg)


class HeartbeatDueTest(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 8, 9, 21, 0, tzinfo=JST)

    def test_recent_check_is_not_due(self):
        last = (self.now - dt.timedelta(days=1)).isoformat()
        self.assertFalse(heartbeat_due(last, self.now))

    def test_old_check_is_due(self):
        last = (self.now - dt.timedelta(days=8)).isoformat()
        self.assertTrue(heartbeat_due(last, self.now))

    def test_exactly_seven_days_is_due(self):
        last = (self.now - dt.timedelta(days=7)).isoformat()
        self.assertTrue(heartbeat_due(last, self.now))

    def test_missing_or_corrupt_timestamp_is_due(self):
        self.assertTrue(heartbeat_due("", self.now))
        self.assertTrue(heartbeat_due("not-a-date", self.now))

    def test_naive_timestamp_is_treated_as_jst(self):
        last = (self.now - dt.timedelta(days=1)).replace(tzinfo=None).isoformat()
        self.assertFalse(heartbeat_due(last, self.now))


if __name__ == "__main__":
    unittest.main()
