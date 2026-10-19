"""銀山温泉 2026-12-13 宿泊の空室監視（公式予約カレンダー、通知のみ）。

5施設の489ban「お部屋一覧」表をPlaywrightで読む。
対象日の<td>内にある予約リンクのみを空室と判断し、満室アイコンは満室と判断。
部屋の定員・予約確定はリンク先で確認すること（自動予約は行わない）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from tablecheck_watcher.config import NtfyConfig
from tablecheck_watcher.notify import send_ntfy

CHECKIN = date(2026, 12, 13)
CALENDAR_START = "2026-12-01"
STATE = Path("state.ginzan.json")
JST = timezone(timedelta(hours=9))
INNS = {
    "ginzanso": ("仙峡の宿 銀山荘", "ginzanso"),
    "kosekiya": ("古勢起屋別館", "kosekiya"),
    "kosekikan": ("本館古勢起屋", "kosekikan"),
    "notoya": ("能登屋旅館", "notoyaryokan"),
    "takimikan": ("滝と蕎麦の宿 瀧見舘", "takimikan"),
}

# 2026-10-20にGitHub Actionsから実ページへのアクセスとカレンダーDOMを検証。
CELL_JS = r"""() => {
  const tables=[...document.querySelectorAll('table')].filter(t=>{
    const heads=[...t.querySelectorAll('thead th')].map(h=>(h.innerText||'').replace(/\s+/g,''));
    return heads.length === 14 && heads[0].startsWith('12/1') && heads[12] === '13日';
  });
  return tables.map(t=>{
    const heads=[...t.querySelectorAll('thead th')];
    const row=[...t.querySelectorAll('tbody tr')].find(r=>r.querySelectorAll('td').length === heads.length);
    const td=row?.querySelectorAll('td')[12];
    if(!td)return null;
    return {
      icons:[...td.querySelectorAll('i')].map(x=>String(x.className)),
      text:(td.innerText||'').trim(),
      links:[...td.querySelectorAll('a[href]')].map(a=>({href:a.href,text:(a.innerText||'').trim()})),
    };
  });
}"""


def calendar_url(client: str) -> str:
    return f"https://reserve.489ban.net/client/{client}/0/plan/availability/room/stay?date={CALENDAR_START}"


def booking_url(href: str) -> bool:
    """正確な宿泊日を含む489banの予約リンク以外は通知しない。"""
    try:
        parsed = urlparse(href)
        if parsed.scheme != "https" or parsed.netloc != "reserve.489ban.net":
            return False
        if re.search(r"^/client/[^/]+/0/plan/room/\d+/stay$", parsed.path) is None:
            return False
        return parse_qs(parsed.query).get("date") == [CHECKIN.isoformat()]
    except (ValueError, TypeError):
        return False


def classify_cells(raw: object) -> tuple[str, list[str], int]:
    """空きリンクがあればavailable、全て満室/提供なしはunavailable、その他unknown。"""
    if not isinstance(raw, list) or not raw:
        return "unknown", [], 0
    available: set[str] = set()
    closed = 0
    for cell in raw:
        if not isinstance(cell, dict):
            return "unknown", [], len(raw)
        links = cell.get("links") or []
        for link in links:
            if not isinstance(link, dict):
                continue
            href = str(link.get("href") or "")
            if booking_url(href) and re.fullmatch(r"[1-9]\d*", str(link.get("text") or "").strip()):
                available.add(href)
        icons = cell.get("icons") or []
        if any("text-danger" in s and ("fa-xmark" in s or "fa-minus" in s) for s in icons):
            closed += 1
    if available:
        return "available", sorted(available), len(raw)
    if closed == len(raw):
        return "unavailable", [], len(raw)
    return "unknown", [], len(raw)


def inspect_inn(browser, client: str) -> tuple[str, list[str], int]:
    page = browser.new_page(locale="ja-JP", timezone_id="Asia/Tokyo")
    try:
        resp = page.goto(calendar_url(client), wait_until="domcontentloaded", timeout=30000)
        if resp is None or resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status if resp else 'none'}")
        page.wait_for_timeout(500)
        result = page.evaluate(CELL_JS)
        status, links, rooms = classify_cells(result)
        if status == "unknown":
            raise RuntimeError(f"予約カレンダー判定不可 (room_rows={rooms})")
        return status, links, rooms
    finally:
        page.close()


def send(title: str, body: str, url: str, priority: int = 4) -> None:
    cfg = NtfyConfig(
        server=os.getenv("NTFY_SERVER") or "https://ntfy.sh",
        topic=os.getenv("NTFY_TOPIC") or "",
        token=os.getenv("NTFY_TOKEN") or "",
    )
    send_ntfy(cfg, title, body, click=url, priority=priority, tags=["hotel"])


def load_state() -> dict:
    try:
        data = json.loads(STATE.read_text("utf-8"))
        if data.get("checkin") == CHECKIN.isoformat():
            return data
    except (FileNotFoundError, ValueError, TypeError):
        pass
    return {"checkin": CHECKIN.isoformat(), "rooms": {}, "failures": 0, "failure_warned": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("check", "dry-run", "test-notify"), nargs="?", default="check")
    args = parser.parse_args()
    if args.mode == "test-notify":
        send("銀山温泉・通知テスト", "12/13の空室通知テストです。予約はしていません。",
             "https://www.ginzanonsen.jp/yado/")
        return 0
    if datetime.now(JST).date() > CHECKIN:
        print("宿泊日を過ぎたためチェックを終了します")
        return 0
    if args.mode == "check" and not os.getenv("NTFY_TOPIC"):
        print("ERROR: GitHub Secret NTFY_TOPIC が未設定です", file=sys.stderr)
        return 2

    state = load_state()
    old_rooms = dict(state.get("rooms") or {})
    new_rooms = dict(old_rooms)
    checked = 0
    found = []
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for key, (name, client) in INNS.items():
                try:
                    status, links, room_count = inspect_inn(browser, client)
                    checked += 1
                    print(f"{name}: {status}, room_types={room_count}, available={len(links)}", flush=True)
                    previous = set(old_rooms.get(key) or [])
                    fresh = sorted(set(links) - previous)
                    if args.mode == "check":
                        for link in fresh:
                            send(
                                f"銀山温泉 12/13 空室候補：{name}",
                                "2026/12/13(日)チェックイン・1泊の空室表示を検知しました。"
                                "客室定員・人数・料金はリンク先で必ず確認してください。",
                                link, priority=5,
                            )
                        new_rooms[key] = links
                    found.extend((name, link) for link in links)
                except Exception as e:
                    print(f"CHECK_UNKNOWN {name}: {type(e).__name__}: {e}", flush=True)
                time.sleep(1.0)
        finally:
            browser.close()

    if args.mode == "dry-run":
        print(f"dry-run 判定可能 {checked}/{len(INNS)}軒, 空室候補 {len(found)}件")
        return 0 if checked else 2
    if checked and not state.get("initialized"):
        send("銀山温泉 監視開始", f"12月13日宿泊の空室監視を開始しました（判定成功 {checked}/{len(INNS)}軒）。",
             "https://www.ginzanonsen.jp/yado/", priority=3)
    failures = 0 if checked else int(state.get("failures", 0)) + 1
    warned = False if checked else bool(state.get("failure_warned"))
    if failures >= 3 and not warned:
        send("銀山温泉 監視エラー", "3回連続で全施設の確認に失敗しています。GitHub Actionsのログを確認してください。",
             "https://github.com/kouheibass0608-png/restrant/actions", priority=3)
        warned = True
    payload = {
        "checkin": CHECKIN.isoformat(),
        "rooms": new_rooms,
        "initialized": bool(state.get("initialized")) or bool(checked),
        "failures": failures,
        "failure_warned": warned,
        "checked_count": checked,
        "last_run_jst": datetime.now(JST).isoformat(timespec="seconds"),
    }
    STATE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if checked else 2


if __name__ == "__main__":
    sys.exit(main())
