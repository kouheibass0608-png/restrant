"""www.tablecheck.com の予約ウィジェットが使う内部APIのクライアント。

予約ページ (https://www.tablecheck.com/{locale}/shops/{slug}/reserve) の
タイムテーブル表示が呼んでいる
    GET /{locale}/shops/{slug}/available/timetable
を利用する。パラメータは Rails の form 形式で reservation[...] にネストする。
1回のリクエストで queried_date から約1週間分のスロットが返る。

レスポンス例:
    {
      "queried_date": "2026-08-12",
      "data": {
        "slots": {
          "2026-08-12": {
            "1786519800": {"available": false, "seconds": 59400, "meal": "dinner", ...},
            ...
          },
          ...
        }
      }
    }
"""

from __future__ import annotations

import datetime as dt
import gzip
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .config import Config

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# fetch_availability 1店舗・1人数あたりのリクエスト数の上限 (暴走防止)。
# 1リクエスト約1週間分のため、20回で「3か月先の月末」までカバーできる。
MAX_REQUESTS_PER_CHECK = 20


class TableCheckError(Exception):
    pass


class TableCheckRateLimitError(TableCheckError):
    pass


def seconds_to_hhmm(seconds: int) -> str:
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}"


def parse_timetable_response(data: dict) -> tuple[str, dict[str, list[str]]]:
    """レスポンスを (queried_date, {日付: [空き時刻 "HH:MM", ...]}) に変換する。

    スロットが1件もない日も空リストとして含める (休業日/満席の区別はしない)。
    """
    if not isinstance(data, dict):
        raise TableCheckError(f"想定外のレスポンス形式です: {str(data)[:200]}")
    if "status" in data and "data" not in data:
        # 例: {"status": "disabled"} — パラメータ不備か、オンライン予約停止中
        raise TableCheckError(f"APIがステータス '{data['status']}' を返しました")
    queried = data.get("queried_date")
    slots = (data.get("data") or {}).get("slots")
    if not queried or not isinstance(slots, dict):
        raise TableCheckError(f"想定外のレスポンス形式です: {str(data)[:200]}")

    days: dict[str, list[str]] = {}
    for date, times in slots.items():
        available: list[str] = []
        if isinstance(times, dict):
            for info in times.values():
                if isinstance(info, dict) and info.get("available"):
                    available.append(seconds_to_hhmm(int(info["seconds"])))
        days[str(date)] = sorted(available)
    return str(queried), days


class TableCheckClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def _get_json(self, url: str) -> dict:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Accept-Language": "ja,en;q=0.8",
                "Accept-Encoding": "gzip",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": self.cfg.reserve_page_url,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.request_timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                retry_after = e.headers.get("Retry-After") if e.headers else None
                detail = f" (Retry-After: {retry_after}秒)" if retry_after else ""
                raise TableCheckRateLimitError(f"HTTP 429{detail}: {url}") from e
            raise TableCheckError(f"HTTP {e.code}: {url}") from e
        except urllib.error.URLError as e:
            raise TableCheckError(f"接続エラー: {e.reason}") from e
        except OSError as e:
            raise TableCheckError(f"通信エラー: {e}") from e
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise TableCheckError(f"JSONを解析できません: {raw[:200]!r}") from e

    def fetch_timetable(
        self, start_date: str, num_people: int
    ) -> tuple[str, dict[str, list[str]]]:
        """start_date からの1週間分の空き状況を取得する。"""
        params = {
            "reservation[start_date]": start_date,
            "reservation[num_people_adult]": num_people,
            "reservation[num_people_child]": 0,
        }
        url = (
            f"https://www.tablecheck.com/{self.cfg.locale}/shops/{self.cfg.shop_slug}"
            f"/available/timetable?{urllib.parse.urlencode(params)}"
        )
        return parse_timetable_response(self._get_json(url))

    def fetch_availability(self, dates: list[str], num_people: int) -> dict[str, list[str]]:
        """指定人数について、対象日付をカバーする範囲の空き状況を取得する。

        週単位のレスポンスを、最終対象日をカバーするまでページングする。
        返り値は {日付: [空き時刻]} (空きのある日のみ)。
        """
        if not dates:
            return {}
        last = max(dates)
        last_date = dt.date.fromisoformat(last)
        cursor = min(dates)
        result: dict[str, list[str]] = {}

        for i in range(MAX_REQUESTS_PER_CHECK):
            if i > 0 and self.cfg.request_interval > 0:
                time.sleep(self.cfg.request_interval)
            _, window = self.fetch_timetable(cursor, num_people)
            for date, times in window.items():
                if times:
                    result[date] = times

            if window:
                covered_through = max(window)
                if covered_through >= last:
                    break
                next_date = dt.date.fromisoformat(covered_through) + dt.timedelta(days=1)
            else:
                # 休業期間などでは slots 自体が空になることがある。
                # 予約受付期間の終端とは限らないため、次週へ進んで探索を続ける。
                next_date = dt.date.fromisoformat(cursor) + dt.timedelta(days=7)

            cursor_date = dt.date.fromisoformat(cursor)
            if next_date <= cursor_date:
                # APIが要求日より過去のウィンドウを返しても必ず前進させる。
                next_date = cursor_date + dt.timedelta(days=7)
            if next_date > last_date:
                break
            cursor = next_date.isoformat()
        return result
