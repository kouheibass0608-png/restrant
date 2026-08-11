#!/usr/bin/env python3
"""OMAKASE (omakase.in) の空き状況が取得できるかを調査するスクリプト。

最大の論点は「ログインなしで空き枠を読めるか」。
読めない場合、監視には認証情報が必要になり、実装方針が大きく変わる。

使い方:
    python scripts/probe_omakase.py [restaurant_id]
        restaurant_id 例: qt951856 (カンテサンス)
"""

from __future__ import annotations

import gzip
import io
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def fetch(url: str, accept: str = "text/html", xhr: bool = False) -> tuple[int, str, str]:
    """(status, final_url, body) を返す。リダイレクト先も見たいので final_url を含む。"""
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
            return resp.status, resp.geturl(), raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            if e.headers.get("Content-Encoding") == "gzip":
                raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
            body = raw.decode("utf-8", errors="replace")
        except Exception:
            body = "<unreadable>"
        return e.code, url, body
    except Exception as e:
        return -1, url, f"<{type(e).__name__}: {e}>"


def main() -> None:
    rid = sys.argv[1] if len(sys.argv) > 1 else "qt951856"
    page = f"https://omakase.in/r/{rid}"

    status, final, html = fetch(page)
    print(f"=== 店舗ページ ===")
    print(f"URL      : {page}")
    print(f"HTTP     : {status}")
    print(f"最終URL  : {final}")
    print(f"本文長   : {len(html)}")
    redirected = urllib.parse.urlparse(final).path != urllib.parse.urlparse(page).path
    print(f"リダイレクト: {'あり ← ログイン要求の可能性' if redirected else 'なし'}")

    # ログイン要求の痕跡
    print("\n=== ログイン要求の痕跡 ===")
    for kw in ("ログイン", "sign_in", "signin", "login", "会員登録", "Sign in"):
        n = html.count(kw)
        if n:
            print(f"  '{kw}': {n} 回")

    # タイトル
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    print(f"\ntitle: {m.group(1).strip()[:120] if m else '(なし)'}")

    # 埋め込みJSON (Next.js / Nuxt / Rails gon など)
    print("\n=== 埋め込みJSON ===")
    for pat, label in (
        (r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', "__NEXT_DATA__"),
        (r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', "application/json"),
        (r"window\.__NUXT__\s*=\s*(.*?);?\s*</script>", "__NUXT__"),
        (r"window\.gon\s*=\s*(\{.*?\});", "gon"),
    ):
        for hit in re.findall(pat, html, re.S)[:3]:
            hit = hit.strip()
            print(f"  [{label}] {len(hit)} bytes")
            try:
                data = json.loads(hit)
                print(f"    トップレベルkey: {list(data)[:20]}")
            except Exception:
                print(f"    先頭: {hit[:300]}")

    # 空き状況らしき語の出現
    print("\n=== 空き状況を示す語の出現 ===")
    for kw in (
        "available",
        "availability",
        "vacan",
        "calendar",
        "満席",
        "空席",
        "予約可能",
        "reservable",
        "seat",
        "×",
        "○",
    ):
        n = html.count(kw)
        if n:
            print(f"  '{kw}': {n} 回")

    # JSバンドルとAPIパス
    print("\n=== script src ===")
    srcs = re.findall(r'<script[^>]+src="([^"]+)"', html)
    for s in srcs[:25]:
        print(f"  {s}")

    print("\n=== HTML内のAPIらしきパス ===")
    paths = set()
    paths.update(re.findall(r'["\'](/api/[A-Za-z0-9_/\-{}.]{2,80})["\']', html))
    paths.update(re.findall(r'["\'](/r/[A-Za-z0-9_/\-{}.]{2,80})["\']', html))
    for p in sorted(paths)[:40]:
        print(f"  {p}")

    # 候補エンドポイントを試す
    print("\n=== 候補エンドポイント ===")
    candidates = [
        f"https://omakase.in/api/restaurants/{rid}",
        f"https://omakase.in/api/r/{rid}",
        f"https://omakase.in/api/r/{rid}/calendar",
        f"https://omakase.in/api/r/{rid}/availability",
        f"https://omakase.in/r/{rid}/calendar",
        f"https://omakase.in/r/{rid}.json",
        f"https://omakase.in/r/{rid}/reservation_frames",
    ]
    for url in candidates:
        st, fin, body = fetch(url, accept="application/json", xhr=True)
        snippet = re.sub(r"\s+", " ", body.strip())[:200]
        print(f"  HTTP {st:>4}  {url}")
        print(f"        {snippet}")

    print("\nprobe done")


if __name__ == "__main__":
    main()
