import unittest

from tablecheck_watcher.tablecheck import (
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


if __name__ == "__main__":
    unittest.main()
