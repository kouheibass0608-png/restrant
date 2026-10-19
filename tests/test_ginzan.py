"""銀山温泉の誤通知防止テスト。"""
import unittest

from ginzan_watcher import booking_url, classify_cells


class GinzanTest(unittest.TestCase):
    URL = ("https://reserve.489ban.net/client/takimikan/0/plan/room/17759/stay"
           "?date=2026-12-13&roomCount=1#chooseFromRoom")

    def test_valid_booking_link(self):
        self.assertTrue(booking_url(self.URL))

    def test_wrong_date_not_alerted(self):
        self.assertFalse(booking_url(self.URL.replace("2026-12-13", "2026-12-14")))

    def test_wrong_site_not_alerted(self):
        self.assertFalse(booking_url(self.URL.replace("reserve.489ban.net", "example.com")))

    def test_empty_unknown(self):
        self.assertEqual(classify_cells([])[0], "unknown")

    def test_all_closed(self):
        rows = [
            {"icons": ["fa-solid fa-xmark text-danger"], "links": []},
            {"icons": ["fa-solid fa-minus text-danger"], "links": []},
        ]
        self.assertEqual(classify_cells(rows), ("unavailable", [], 2))

    def test_one_available(self):
        rows = [
            {"icons": ["fa-solid fa-xmark text-danger"], "links": []},
            {"icons": [], "links": [{"href": self.URL, "text": "1"}]},
        ]
        self.assertEqual(classify_cells(rows), ("available", [self.URL], 2))

    def test_day_header_link_not_available(self):
        rows = [{"icons": [], "links": [
            {"href": "https://reserve.489ban.net/client/takimikan/0/plan/availability/room/stay?date=2026-12-13", "text": "13"}
        ]}]
        self.assertEqual(classify_cells(rows)[0], "unknown")

    def test_no_numeric_room_count_not_available(self):
        rows = [{"icons": [], "links": [{"href": self.URL, "text": ""}]}]
        self.assertEqual(classify_cells(rows)[0], "unknown")


if __name__ == "__main__":
    unittest.main()
