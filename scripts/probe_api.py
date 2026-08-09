#!/usr/bin/env python3
"""TableCheck の予約ウィジェットが使う内部APIを調査するスクリプト (v3)。

www.tablecheck.com の /shops/{slug}/available* エンドポイントの
正しいリクエストパラメータを特定する。

使い方:
    python scripts/probe_api.py [shop_slug]
"""

from __future__ import annotations

import datetime as dt
import gzip
import io
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

MAX_BODY_PRINT = 2500


def fetch(url: str, accept: str = "application/json", xhr: bool = True) -> tuple[int, str]:
    headers = {
        "User-Agent": UA,
        "Accept": accept,
        "Accept-Language": "ja,en;q=0.8",
        "Accept-Encoding": "gzip",
    }
    if xhr:
        headers["X-Requested-With"] = "XMLHttpRequest"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
            return resp.status, raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            if e.headers.get("Content-Encoding") == "gzip":
                raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
            body = raw.decode("utf-8", errors="replace")
        except Exception:
            body = "<body unreadable>"
        return e.code, body
    except Exception as e:
        return -1, f"<{type(e).__name__}: {e}>"


def show(name: str, url: str, status: int, body: str) -> None:
    print(f"\n=== {name} ===")
    print(f"URL: {url}")
    print(f"HTTP {status}")
    body = body.strip()
    if body.startswith("{") or body.startswith("["):
        try:
            parsed = json.loads(body)
            pretty = json.dumps(parsed, ensure_ascii=False, indent=1)
            if len(pretty) > MAX_BODY_PRINT:
                pretty = pretty[:MAX_BODY_PRINT] + "\n... (truncated)"
            print(pretty)
            return
        except Exception:
            pass
    print(body[:MAX_BODY_PRINT] + ("... (truncated)" if len(body) > MAX_BODY_PRINT else ""))


def main() -> None:
    slug = sys.argv[1] if len(sys.argv) > 1 else "joelrobuchon"
    jst = ZoneInfo("Asia/Tokyo")
    target_date = (dt.datetime.now(jst) + dt.timedelta(days=14)).date()
    dinner = dt.datetime.combine(target_date, dt.time(18, 0), tzinfo=jst)
    epoch = int(dinner.timestamp())

    # 1) バンドルから requestData 関数の全体を抽出
    page_url = f"https://www.tablecheck.com/ja/shops/{slug}/reserve"
    status, html = fetch(page_url, accept="text/html", xhr=False)
    print(f"=== reserve page ===\nHTTP {status}")

    bundle_urls = [
        s
        for s in re.findall(r'<script[^>]+src="([^"]+)"', html)
        if "assets/table_check/application-" in s
    ]
    js = ""
    if bundle_urls:
        s, js = fetch(bundle_urls[0], accept="*/*", xhr=False)
        print(f"bundle: {bundle_urls[0]} HTTP {s} ({len(js)} bytes)")

    def dump_after(label: str, pattern: str, after: int = 2500, before: int = 200) -> None:
        print(f"\n--- {label} ---")
        m = re.search(pattern, js)
        if not m:
            print("(no match)")
            return
        start = max(0, m.start() - before)
        print(js[start : m.end() + after])

    dump_after("Timetable request (available/timetable)", r"available/timetable")
    dump_after("OnlineAvailability request ('/available')", r"['\"]/available['\"]")
    dump_after("startAtEpoch def", r"startAtEpoch\s*=\s*function", after=800)

    # 2) パラメータ候補を試す
    base = f"https://www.tablecheck.com/ja/shops/{slug}"
    date_s = target_date.isoformat()
    course = "66a05ab965b68ef11684ebd2"  # ReservationCourses.available の先頭

    def q(params: dict) -> str:
        return urllib.parse.urlencode(params, doseq=True)

    candidates = [
        ("available epoch+adult", f"{base}/available?{q({'start_at_epoch': epoch, 'num_people_adult': 2})}"),
        ("available epoch+adult+course", f"{base}/available?{q({'start_at_epoch': epoch, 'num_people_adult': 2, 'course_ids[]': course})}"),
        ("timetable start_date+adult", f"{base}/available/timetable?{q({'start_date': date_s, 'num_people_adult': 2})}"),
        ("timetable reservation[...]", f"{base}/available/timetable?{q({'start_date': date_s, 'reservation[num_people_adult]': 2})}"),
        (
            "timetable reservation full",
            f"{base}/available/timetable?"
            + q(
                {
                    "start_date": date_s,
                    "reservation[num_people_adult]": 2,
                    "reservation[num_people_child]": 0,
                    "reservation[course_ids][]": course,
                }
            ),
        ),
        ("chain epoch+adult", f"{base}/available/chain?{q({'start_at_epoch': epoch, 'num_people_adult': 2})}"),
    ]
    for name, url in candidates:
        st, body = fetch(url)
        show(name, url, st, body)

    print("\nprobe done")


if __name__ == "__main__":
    main()
