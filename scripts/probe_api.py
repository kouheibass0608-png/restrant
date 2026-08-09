#!/usr/bin/env python3
"""TableCheck の予約ウィジェットの内部APIを調査するスクリプト。

主な用途:
  1. 仕様変更で監視が壊れたときの原因調査
  2. 「APIが空きと言っている枠が、本当に予約できるのか」の検証

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

JST = ZoneInfo("Asia/Tokyo")
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


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
            return e.code, raw.decode("utf-8", errors="replace")
        except Exception:
            return e.code, "<unreadable>"
    except Exception as e:
        return -1, f"<{type(e).__name__}: {e}>"


def slots_for(slug: str, start_date: str, num_people: int) -> dict[str, dict]:
    """{日付: {"HH:MM": epoch}} の形で「予約可能」枠だけ返す。"""
    params = {
        "reservation[start_date]": start_date,
        "reservation[num_people_adult]": num_people,
        "reservation[num_people_child]": 0,
    }
    url = (
        f"https://www.tablecheck.com/ja/shops/{slug}/available/timetable"
        f"?{urllib.parse.urlencode(params)}"
    )
    status, body = fetch(url)
    if status != 200:
        print(f"  timetable HTTP {status}: {body[:200]}")
        return {}
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        print(f"  timetable JSON parse error: {body[:200]}")
        return {}
    if "data" not in data:
        print(f"  timetable unexpected: {json.dumps(data, ensure_ascii=False)[:200]}")
        return {}
    out: dict[str, dict] = {}
    for date, times in (data["data"].get("slots") or {}).items():
        avail = {}
        for epoch, info in times.items():
            if isinstance(info, dict) and info.get("available"):
                sec = int(info["seconds"])
                avail[f"{sec // 3600:02d}:{sec % 3600 // 60:02d}"] = int(epoch)
        if avail:
            out[date] = avail
    return out


def main() -> None:
    slug = sys.argv[1] if len(sys.argv) > 1 else "joelrobuchon"
    page_url = f"https://www.tablecheck.com/ja/shops/{slug}/reserve"
    status, html = fetch(page_url, accept="text/html", xhr=False)
    print(f"=== 予約ページ === HTTP {status} ({len(html)} bytes)")

    # --- 1) 人数セレクタに 1 は存在するか -------------------------------------
    print("\n=== 人数セレクタ (#reservation_num_people_adult) ===")
    m = re.search(
        r'<select[^>]*id="reservation_num_people_adult".*?</select>', html, re.S
    )
    if m:
        opts = re.findall(r"<option[^>]*value=\"([^\"]*)\"[^>]*>(.*?)</option>", m.group(0))
        print(f"  選択肢 {len(opts)} 件: {[(v, re.sub(r'<[^>]+>', '', t).strip()) for v, t in opts]}")
        selected = re.search(r'<option[^>]*selected[^>]*value="([^"]*)"', m.group(0))
        print(f"  既定値: {selected.group(1) if selected else '(なし)'}")
    else:
        print("  (セレクタが見つかりません — 別UIの可能性)")

    # 人数まわりの設定値
    print("\n=== 人数まわりの設定値 (インラインJS) ===")
    for pat in (
        r"max_num_people\s*=\s*[^;]+",
        r"min_num_people\s*=\s*[^;]+",
        r"num_people[A-Za-z_]*\s*=\s*[^;]{0,60}",
    ):
        for hit in sorted(set(re.findall(pat, html)))[:10]:
            print(f"  {hit.strip()}")

    # --- 2) 1名と2名の空き枠を同一週で比較 -----------------------------------
    start = (dt.datetime.now(JST) + dt.timedelta(days=3)).date().isoformat()
    print(f"\n=== 1名 vs 2名 の空き比較 (start_date={start}) ===")
    per_size = {}
    for n in (1, 2, 3, 4):
        s = slots_for(slug, start, n)
        per_size[n] = s
        total = sum(len(v) for v in s.values())
        print(f"  {n}名: {len(s)}日 / {total}枠  {dict(list(s.items())[:3])}")

    # --- 3) 予約ボタン相当のチェック (/available) ----------------------------
    # タイムテーブルが「空き」と言う枠が、実際に予約可能かを確認する。
    # 予約ページで時間を選んだときに呼ばれるエンドポイント。
    print("\n=== /available による実予約可否チェック ===")
    for n in (1, 2):
        target = None
        for date, times in sorted(per_size[n].items()):
            for hhmm, epoch in sorted(times.items()):
                target = (date, hhmm, epoch)
                break
            if target:
                break
        if not target:
            print(f"  {n}名: 空き枠が無いためスキップ")
            continue
        date, hhmm, epoch = target
        variants = {
            "最小": {"start_at_epoch": epoch, "num_people_adult": n},
            "全人数フィールド": {
                "start_at_epoch": epoch,
                "num_people_adult": n,
                "num_people_child": 0,
                "num_people_senior": 0,
                "num_people_baby": 0,
            },
            "reservation[] 形式": {
                "reservation[start_at_epoch]": epoch,
                "reservation[num_people_adult]": n,
                "reservation[num_people_child]": 0,
            },
        }
        for label, params in variants.items():
            url = (
                f"https://www.tablecheck.com/ja/shops/{slug}/available"
                f"?{urllib.parse.urlencode(params)}"
            )
            st, body = fetch(url)
            print(f"  {n}名 {date} {hhmm} [{label}] -> HTTP {st} {body.strip()[:300]}")

    # --- 3.5) 2名の「枠そのもの」を確認 (空き有無に関わらず) -----------------
    # 空き枠だけ見ていると営業時間帯を誤認するため、グリッド全体を見る。
    print("\n=== 2名の枠グリッド (available を問わず全時間帯) ===")
    seen_times: dict[str, set[str]] = {}
    for wk in range(0, 21, 7):
        d = (dt.datetime.now(JST) + dt.timedelta(days=3 + wk)).date().isoformat()
        params = {
            "reservation[start_date]": d,
            "reservation[num_people_adult]": 2,
            "reservation[num_people_child]": 0,
        }
        st, body = fetch(
            f"https://www.tablecheck.com/ja/shops/{slug}/available/timetable"
            f"?{urllib.parse.urlencode(params)}"
        )
        if st != 200:
            continue
        try:
            slots = (json.loads(body).get("data") or {}).get("slots") or {}
        except json.JSONDecodeError:
            continue
        for date, times in slots.items():
            ts = set()
            for info in times.values():
                if isinstance(info, dict) and "seconds" in info:
                    sec = int(info["seconds"])
                    ts.add(f"{sec // 3600:02d}:{sec % 3600 // 60:02d}")
            if ts:
                seen_times[date] = ts
    weekday_ja = ["月", "火", "水", "木", "金", "土", "日"]
    for date in sorted(seen_times)[:21]:
        w = weekday_ja[dt.date.fromisoformat(date).weekday()]
        print(f"  {date}({w}): {sorted(seen_times[date])}")
    all_times = sorted({t for ts in seen_times.values() for t in ts})
    print(f"  → 出現する全時間帯: {all_times}")

    # --- 4) OnlineAvailability.requestData の実装を確認 ----------------------
    print("\n=== バンドル内 OnlineAvailability.requestData ===")
    bundles = [
        s
        for s in re.findall(r'<script[^>]+src="([^"]+)"', html)
        if "assets/table_check/application-" in s
    ]
    if bundles:
        st, js = fetch(bundles[0], accept="*/*", xhr=False)
        if st == 200:
            m = re.search(r"OnlineAvailability=function\(\).{0,12000}?requestData=function", js, re.S)
            if m:
                tail = js[m.end() : m.end() + 1500]
                print(tail)
            else:
                m2 = re.search(r"requestData=function\(\)\{[^}]{0,1200}", js)
                print(m2.group(0) if m2 else "(requestData が見つかりません)")

    print("\nprobe done")


if __name__ == "__main__":
    main()
