"""銀山温泉・指定日の公式予約カレンダー空室監視（通知のみ、予約しない）。"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from tablecheck_watcher.config import NtfyConfig
from tablecheck_watcher.notify import send_ntfy

TARGET_DATE = date(2026, 12, 13)
JST = timezone(timedelta(hours=9))
STATE_PATH = Path("state.ginzan.json")
# 銀山温泉旅館組合の公式宿一覧から辿れる11軒の予約入口。
INNS = {
    "fujiya": "藤屋",
    "ginzanso": "銀山荘",
    "showakan": "昭和館",
    "kozankaku": "古山閣",
    "notoya": "能登屋旅館",
    "matsumoto": "旅館 松本",
    "yanadaya": "御宿 やなだ屋",
    "itouya": "旅籠 いとうや",
    "takimikan": "瀧見舘",
    "kosekiya": "古勢起屋別館",
    "kosekikan": "本館古勢起屋",
}
SITE_URL = "https://www.nj-yoyaku.net/{slug}/plan.aspx?PID=-1"


def classify_day_cell(text: str) -> str:
    """カレンダーの *その日* のセルだけを判定。意味が不明ならunknown。"""
    s = re.sub(r"[\s\u3000]+", "", text or "")
    s = re.sub(r"^13(?:日|日曜)?", "", s, count=1)
    if any(mark in s for mark in ("○", "◯", "〇", "◎", "△")):
        return "available"
    # '1' のような空室数表記。ただし日付の数字とは区別する。
    if re.fullmatch(r"[1-9]\d*(?:室|部屋|件)?", s):
        return "available"
    if any(mark in s for mark in ("満室", "受付終了", "予約不可", "×", "✕", "✖", "−", "－", "-")):
        return "full"
    return "unknown"


def aggregate(cells: list[str]) -> str:
    """少なくとも1つの空きは肯定的証拠、全セル満室なら満室。"""
    statuses = [classify_day_cell(c) for c in cells]
    if "available" in statuses:
        return "available"
    if statuses and all(s == "full" for s in statuses):
        return "full"
    return "unknown"


# カレンダーのみを対象にする。ページ全体の『予約可能』等の文字列では判定しない。
CALENDAR_CELLS_JS = r"""(day) => {
  const result = [];
  for (const table of document.querySelectorAll('table')) {
    const rows = [...table.querySelectorAll('tr')];
    const weekdayCount = [...table.querySelectorAll('th')].filter(
      x => /^(日|月|火|水|木|金|土)(曜日)?$/.test(x.innerText.trim())
    ).length;
    if (weekdayCount < 5 && !/calendar|calender|カレンダー/i.test(table.className || '')) continue;
    for (const cell of table.querySelectorAll('td')) {
      const s = (cell.innerText || '').trim();
      if (new RegExp('^' + day + '(?=\\D|$)').test(s)) {
        result.push(s.slice(0, 120));
      }
    }
  }
  // 非table型の予約カレンダーを使用するサイトに備えた保守的fallback。
  if (!result.length) {
    for (const el of document.querySelectorAll('[data-date], [data-day]')) {
      const key = el.getAttribute('data-date') || el.getAttribute('data-day') || '';
      if (key === '2026-12-13' || key === '20261213') {
        result.push((el.innerText || '').trim().slice(0, 120));
      }
    }
  }
  return result.slice(0, 30);
}"""


def set_party_size(page, people: int) -> bool:
    """人数のセレクトが確認できなければ安全側で監視失敗にする。"""
    for selector in page.locator("select").all():
        try:
            options = selector.locator("option").all()
            for option in options:
                label = (option.inner_text() or "").strip().replace(" ", "")
                if re.fullmatch(rf"{people}(?:名|人|名様)(?:1室)?", label):
                    selector.select_option(value=option.get_attribute("value"))
                    page.wait_for_timeout(600)
                    return True
        except Exception:
            continue
    return False


def month_on_page(page, year: int, month: int) -> bool:
    # 非表示テンプレート等の月表示を誤読しないよう可視要素のみ。
    return page.get_by_text(re.compile(rf"{year}\s*年\s*0?{month}\s*月")).first.is_visible(timeout=3000)


def check_inn(browser, slug: str, party_size: int) -> tuple[str, list[str]]:
    """ページ操作が成立したときだけ full / available を返す。"""
    page = browser.new_page(locale="ja-JP", timezone_id="Asia/Tokyo")
    try:
        page.goto(SITE_URL.format(slug=slug), wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(900)
        if not set_party_size(page, party_size):
            raise RuntimeError("2名等の人数指定欄を特定できません")
        # 基本画面は当月から始まる。上限8回で無限巡回を防ぐ。
        for _ in range(8):
            if month_on_page(page, TARGET_DATE.year, TARGET_DATE.month):
                break
            nxt = page.get_by_text("次月", exact=True).first
            if not nxt.is_visible(timeout=3000):
                raise RuntimeError("次月への操作が見つかりません")
            nxt.click(timeout=8000)
            page.wait_for_timeout(800)
        else:
            raise RuntimeError("対象月へ移動できません")
        page.wait_for_timeout(500)
        cells = page.evaluate(CALENDAR_CELLS_JS, TARGET_DATE.day)
        status = aggregate(cells)
        if status == "unknown":
            raise RuntimeError(f"12/13のカレンダー値を安全に判定できません: {cells[:4]!r}")
        return status, cells
    finally:
        page.close()


def read_state() -> dict:
    if not STATE_PATH.exists():
        return {"statuses": {}, "failures": 0, "failure_warned": False}
    data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if data.get("target_date") != TARGET_DATE.isoformat() or data.get("party_size") != get_party_size():
        return {"statuses": {}, "failures": 0, "failure_warned": False}
    return data


def get_party_size() -> int:
    n = int(os.getenv("GINZAN_PARTY_SIZE", "2"))
    if not 1 <= n <= 8:
        raise ValueError("GINZAN_PARTY_SIZEは1〜8の整数にしてください")
    return n


def notify(title: str, message: str, url: str, *, priority: int = 4) -> None:
    cfg = NtfyConfig(
        server=os.getenv("NTFY_SERVER") or "https://ntfy.sh",
        topic=os.getenv("NTFY_TOPIC") or "",
        token=os.getenv("NTFY_TOKEN") or "",
    )
    send_ntfy(cfg, title, message, click=url, priority=priority, tags=["hotel"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["check", "dry-run", "test-notify"], nargs="?", default="check")
    args = parser.parse_args()
    party = get_party_size()
    if args.mode == "test-notify":
        notify("銀山温泉 空室通知テスト", "2026/12/13・通知経路の確認です。", "https://www.ginzanonsen.jp/yado/")
        return 0
    if date.today() > TARGET_DATE and datetime.now(JST).date() > TARGET_DATE:
        print("監視対象日を過ぎたため終了しました。")
        return 0
    if args.mode == "check" and not os.getenv("NTFY_TOPIC"):
        raise RuntimeError("NTFY_TOPIC secretが必要です。")
    state = read_state()
    old = dict(state.get("statuses") or {})
    updated = dict(old)
    succeeded = 0
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for slug, name in INNS.items():
                url = SITE_URL.format(slug=slug)
                try:
                    status, cells = check_inn(browser, slug, party)
                    succeeded += 1
                    print(f"{name}: {status} | 12/13セル: {cells[:3]!r}", flush=True)
                    if args.mode == "check" and status == "available" and old.get(slug) != "available":
                        notify(
                            f"銀山温泉 空室あり：{name}",
                            f"2026年12月13日(日) 1泊 / {party}名でカレンダーに空き表示を検知。予約画面で必ず最終確認してください。",
                            url,
                            priority=5,
                        )
                    if args.mode == "check":
                        updated[slug] = status
                except Exception as e:
                    print(f"CHECK_UNKNOWN {name}: {type(e).__name__}: {e}", flush=True)
                time.sleep(1.5)  # 同一予約ドメインへの過剰アクセス回避
        finally:
            browser.close()
    if args.mode == "dry-run":
        print(f"dry-run 成功判定 {succeeded}/{len(INNS)}（通知・状態保存なし）")
        return 0 if succeeded else 2
    fails = 0 if succeeded else int(state.get("failures", 0)) + 1
    warned = False if succeeded else bool(state.get("failure_warned"))
    if fails >= 3 and not warned:
        notify("銀山温泉 監視エラー", "3回連続で全旅館の空室判定に失敗しました。GitHub Actionsのログを確認してください。",
               "https://github.com/kouheibass0608-png/restrant/actions", priority=3)
        warned = True
    payload = {
        "target_date": TARGET_DATE.isoformat(),
        "party_size": party,
        "statuses": updated,
        "failures": fails,
        "failure_warned": warned,
        "last_checked_at": datetime.now(JST).isoformat(timespec="seconds"),
        "successful_checks": succeeded,
    }
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Completed {succeeded}/{len(INNS)}; state saved.", flush=True)
    return 0 if succeeded else 2


if __name__ == "__main__":
    sys.exit(main())
