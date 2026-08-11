import unittest
from unittest import mock

from tablecheck_watcher.config import Config
from tablecheck_watcher.tablecheck import (
    TableCheckClient,
    TableCheckError,
    parse_timetable_response,
    seconds_to_hhmm,
)

SAMPLE = {
    "queried_date": "2026-08-12",
    "data": {
        "slots": {
            "2026-08-12": {
                "1786519800": {
                    "available": False,
                    "seconds": 59400,
                    "meal": "dinner",
                    "is_all_day": False,
                },
                "1786525200": {
                    "available": True,
                    "seconds": 64800,
                    "meal": "dinner",
                    "is_all_day": False,
                },
                "1786528800": {
                    "available": True,
                    "seconds": 68400,
                    "meal": "dinner",
                    "is_all_day": False,
                },
            },
            "2026-08-13": {
                "1786606200": {
                    "available": False,
                    "seconds": 59400,
                    "meal": "dinner",
                    "is_all_day": False,
                },
            },
        }
    },
}


class SecondsToHhmmTest(unittest.TestCase):
    def test_conversion(self):
        self.assertEqual(seconds_to_hhmm(59400), "16:30")
        self.assertEqual(seconds_to_hhmm(64800), "18:00")
        self.assertEqual(seconds_to_hhmm(0), "00:00")
        self.assertEqual(seconds_to_hhmm(70200), "19:30")


class ParseTimetableResponseTest(unittest.TestCase):
    def test_parses_available_slots(self):
        queried, days = parse_timetable_response(SAMPLE)
        self.assertEqual(queried, "2026-08-12")
        self.assertEqual(days["2026-08-12"], ["18:00", "19:00"])
        self.assertEqual(days["2026-08-13"], [])

    def test_disabled_status_raises(self):
        with self.assertRaises(TableCheckError) as ctx:
            parse_timetable_response({"status": "disabled"})
        self.assertIn("disabled", str(ctx.exception))

    def test_unexpected_shape_raises(self):
        with self.assertRaises(TableCheckError):
            parse_timetable_response({"foo": "bar"})
        with self.assertRaises(TableCheckError):
            parse_timetable_response({"queried_date": "2026-08-12", "data": {}})


class FetchAvailabilityTest(unittest.TestCase):
    def test_empty_week_does_not_stop_later_weeks_from_being_checked(self):
        client = TableCheckClient(Config(request_interval=0))
        responses = [
            # 休業期間は slots が空でも、その先に予約可能日が存在し得る。
            ("2026-08-14", {}),
            ("2026-08-18", {"2026-08-18": [], "2026-08-24": []}),
            ("2026-08-25", {"2026-08-25": ["18:00"]}),
        ]
        with mock.patch.object(client, "fetch_timetable", side_effect=responses) as fetch:
            result = client.fetch_availability(
                ["2026-08-11", "2026-08-25"], num_people=2
            )

        self.assertEqual(result, {"2026-08-25": ["18:00"]})
        self.assertEqual(
            [call.args[0] for call in fetch.call_args_list],
            ["2026-08-11", "2026-08-18", "2026-08-25"],
        )

    def test_empty_weeks_are_scanned_through_three_month_horizon(self):
        client = TableCheckClient(Config(request_interval=0))
        with mock.patch.object(
            client, "fetch_timetable", return_value=("2026-08-11", {})
        ) as fetch:
            result = client.fetch_availability(
                ["2026-08-11", "2026-11-30"], num_people=2
            )

        self.assertEqual(result, {})
        self.assertEqual(fetch.call_count, 16)
        self.assertEqual(fetch.call_args_list[-1].args[0], "2026-11-24")


if __name__ == "__main__":
    unittest.main()
