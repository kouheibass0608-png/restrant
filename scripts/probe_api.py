#!/usr/bin/env python3
"""TableCheck の予約ウィジェットが使う内部APIを調査するスクリプト (v2)。

GitHub Actions (workflow_dispatch / push) またはローカルPCから実行し、
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

MAX_BODY_PRINT = 1600


def fetch(url: str, accept: str = "application/json", xhr: bool = False) -> tuple[int, str]:
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


def context_dump(label: str, text: str, needle_re: str, width: int = 220, limit: int = 30) -> None:
    print(f"\n--- context: {label} (pattern: {needle_re}) ---")
    count = 0
    for m in re.finditer(needle_re, text):
        start = max(0, m.start() - width)
        end = min(len(text), m.end() + width)
        snippet = text[start:end].replace("\n", " ")
        print(f"  [{count}] ...{snippet}...")
        count += 1
        if count >= limit:
            print("  (limit reached)")
            break
    if count == 0:
        print("  (no match)")


def main() -> None:
    slug = sys.argv[1] if len(sys.argv) > 1 else "joelrobuchon"
    today = dt.date.today()
    date1 = today + dt.timedelta(days=14)
    t0 = f"{today.isoformat()}T00:00:00.000Z"

    # 1) 予約ページ本体: インラインscriptの設定値を探す
    page_url = f"https://www.tablecheck.com/ja/shops/{slug}/reserve"
    status, html = fetch(page_url, accept="text/html")
    print(f"=== reserve page ===\nURL: {page_url}\nHTTP {status}  length={len(html)}")
    inline_scripts = re.findall(r"<script(?![^>]*src)[^>]*>(.*?)</script>", html, re.S)
    print(f"inline scripts: {len(inline_scripts)}")
    for i, s in enumerate(inline_scripts):
        if re.search(r"avail|api|url|token|config", s, re.I):
            trimmed = re.sub(r"\s+", " ", s.strip())
            print(f"  inline[{i}] ({len(s)} bytes): {trimmed[:1000]}")

    # meta タグ (csrf 等)
    for m in re.finditer(r'<meta[^>]+(csrf|api)[^>]*>', html, re.I):
        print(f"  meta: {m.group(0)[:200]}")

    # 2) アプリバンドルから /available 周辺のコードを文脈付きで抽出
    bundles = [
        s for s in re.findall(r'<script[^>]+src="([^"]+)"', html) if "tablecheck" in s
    ]
    for src in bundles:
        if src.startswith("//"):
            src = "https:" + src
        s, js = fetch(src, accept="*/*")
        print(f"\n=== bundle {src} -> HTTP {s} ({len(js)} bytes) ===")
        if s != 200:
            continue
        context_dump("available/timetable", js, r"available/timetable")
        context_dump("available/chain", js, r"available/chain")
        context_dump("'/available'", js, r"['\"`]/available['\"`]")
        context_dump("available_request", js, r"available_request")
        context_dump("production.tablecheck", js, r"production\.tablecheck")
        context_dump("apiUrl-ish", js, r"api_?[Uu]rl", limit=10)

    # 3) 候補エンドポイントを試す
    candidates = [
        (
            "www available/timetable (ja)",
            f"https://www.tablecheck.com/ja/shops/{slug}/available/timetable"
            f"?start_at={date1.isoformat()}&num_people=2",
        ),
        (
            "www available/timetable (no locale)",
            f"https://www.tablecheck.com/shops/{slug}/available/timetable"
            f"?start_at={date1.isoformat()}&num_people=2",
        ),
        (
            "www available (date)",
            f"https://www.tablecheck.com/ja/shops/{slug}/available"
            f"?date={date1.isoformat()}&num_people=2",
        ),
        (
            "v2 available",
            f"https://production.tablecheck.com/v2/shops/{slug}/available"
            f"?start_at={t0}&num_people=2&locale=ja",
        ),
        (
            "v2 available/timetable",
            f"https://production.tablecheck.com/v2/shops/{slug}/available/timetable"
            f"?start_at={t0}&num_people=2&locale=ja",
        ),
    ]
    for name, url in candidates:
        status, body = fetch(url, xhr=True)
        show(name, url, status, body)

    print("\nprobe done")


if __name__ == "__main__":
    main()
