#!/usr/bin/env python3
"""TableCheck の予約ウィジェットが使う内部APIを調査するスクリプト。

GitHub Actions (workflow_dispatch) またはローカルPCから実行し、
どのエンドポイントが有効か・レスポンスの形はどうかをログに出力する。

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
import urllib.request

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

MAX_BODY_PRINT = 1200


def fetch(url: str, accept: str = "application/json") -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": accept,
            "Accept-Language": "ja,en;q=0.8",
            "Accept-Encoding": "gzip",
        },
    )
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
    except Exception as e:  # DNS, timeout, TLS など
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
    today = dt.date.today()
    end = today + dt.timedelta(days=60)
    t0 = f"{today.isoformat()}T00:00:00.000Z"
    t1 = f"{end.isoformat()}T23:59:59.000Z"

    candidates = [
        ("shop_info(production)", f"https://production.tablecheck.com/v2/shops/{slug}?locale=ja"),
        (
            "availability_calendar",
            f"https://production.tablecheck.com/v2/shops/{slug}/availability_calendar"
            f"?start_at={t0}&end_at={t1}&num_people=2&locale=ja",
        ),
        (
            "availability_calendar(min)",
            f"https://production.tablecheck.com/v2/shops/{slug}/availability_calendar?num_people=2",
        ),
        (
            "availability(date)",
            f"https://production.tablecheck.com/v2/shops/{slug}/availability"
            f"?date={today.isoformat()}&num_people=2&locale=ja",
        ),
        (
            "availability(start/end)",
            f"https://production.tablecheck.com/v2/shops/{slug}/availability"
            f"?start_at={t0}&end_at={t1}&num_people=2&locale=ja",
        ),
        (
            "availability_days",
            f"https://production.tablecheck.com/v2/shops/{slug}/availability_days"
            f"?start_at={t0}&num_people=2&locale=ja",
        ),
        ("shop_info(api-host)", f"https://api.tablecheck.com/v2/shops/{slug}"),
    ]

    for name, url in candidates:
        status, body = fetch(url)
        show(name, url, status, body)

    # 予約ページ本体から JS バンドルを取り出し、API パスの文字列を探す
    page_url = f"https://www.tablecheck.com/ja/shops/{slug}/reserve"
    status, html = fetch(page_url, accept="text/html")
    print(f"\n=== reserve page ===\nURL: {page_url}\nHTTP {status}  length={len(html)}")

    scripts = re.findall(r'<script[^>]+src="([^"]+)"', html)
    print(f"script tags: {len(scripts)}")
    seen: set[str] = set()
    for src in scripts[:20]:
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = "https://www.tablecheck.com" + src
        s, js = fetch(src, accept="*/*")
        if s != 200:
            print(f"  bundle {src}: HTTP {s}")
            continue
        hits = set()
        hits.update(re.findall(r'https?://[a-z0-9.\-]*tablecheck[a-z0-9.\-]*/[A-Za-z0-9_/${}.\-]*', js))
        hits.update(re.findall(r'["`\'](/?v2/[A-Za-z0-9_/${}.\-]{2,80})["`\']', js))
        hits.update(re.findall(r'["`\']([A-Za-z0-9_/${}.\-]*availab[A-Za-z0-9_/${}.\-]*)["`\']', js))
        new = sorted(h for h in hits if h not in seen)
        seen.update(new)
        if new:
            print(f"  bundle {src} ({len(js)} bytes):")
            for h in new[:60]:
                print(f"    {h}")

    # ページ内に埋め込まれた設定 JSON (API ホスト等) も探す
    for m in re.finditer(r'https?://[a-z0-9.\-]*tablecheck[a-z0-9.\-]*[A-Za-z0-9_/.\-]*', html):
        u = m.group(0)
        if "/v2/" in u or "api" in u or "production" in u:
            print(f"  page url ref: {u}")

    print("\nprobe done")


if __name__ == "__main__":
    main()
