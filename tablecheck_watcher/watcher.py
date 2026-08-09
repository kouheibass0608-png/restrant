"""メインロジック: 空き状況の取得 → 差分検出 → 通知 → 状態保存。"""

from __future__ import annotations

import datetime as dt
import json
from zoneinfo import ZoneInfo

from .config import Config
from .notify import send_ntfy
from .state import State, diff_new_slots, load_state, save_state
from .tablecheck import TableCheckClient, TableCheckError

JST = ZoneInfo("Asia/Tokyo")
WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"]

MAX_DATES_IN_MESSAGE = 10
MAX_TIMES_PER_DATE = 8


def target_dates(cfg: Config, today: dt.date) -> list[str]:
    """監視対象の日付 (YYYY-MM-DD) のリスト。"""
    if cfg.dates:
        return sorted(d for d in cfg.dates if d >= today.isoformat())
    return [(today + dt.timedelta(days=i)).isoformat() for i in range(cfg.days_ahead + 1)]


def in_time_ranges(hhmm: str, ranges: list[str]) -> bool:
    if not ranges:
        return True
    for r in ranges:
        start, end = r.split("-")
        if start <= hhmm <= end:
            return True
    return False


def filter_availability(
    avail: dict[str, list[str]], cfg: Config, today: dt.date
) -> dict[str, list[str]]:
    dates = set(target_dates(cfg, today))
    out: dict[str, list[str]] = {}
    for date, slots in avail.items():
        if date not in dates:
            continue
        kept = sorted(s for s in slots if in_time_ranges(s, cfg.time_ranges))
        if kept:
            out[date] = kept
    return out


def format_date_ja(date_s: str) -> str:
    d = dt.date.fromisoformat(date_s)
    return f"{d.month}/{d.day}({WEEKDAYS_JA[d.weekday()]})"


def reserve_url(cfg: Config, date_s: str | None = None, hhmm: str | None = None) -> str:
    url = (
        f"https://www.tablecheck.com/{cfg.locale}/shops/{cfg.shop_slug}/reserve"
        f"?num_people={cfg.num_people}"
    )
    if date_s:
        url += f"&start_date={date_s}"
        if hhmm:
            h, m = hhmm.split(":")
            url += f"&start_time={int(h) * 3600 + int(m) * 60}"
    return url


def _slot_lines(avail: dict[str, list[str]]) -> list[str]:
    lines = []
    for date in sorted(avail)[:MAX_DATES_IN_MESSAGE]:
        times = avail[date]
        shown = "・".join(times[:MAX_TIMES_PER_DATE])
        if len(times) > MAX_TIMES_PER_DATE:
            shown += " ほか"
        lines.append(f"{format_date_ja(date)} {shown}")
    rest = len(avail) - MAX_DATES_IN_MESSAGE
    if rest > 0:
        lines.append(f"…ほか{rest}日にも空きあり")
    return lines


def build_vacancy_message(new_slots: dict[str, list[str]], cfg: Config) -> tuple[str, str, str]:
    """(title, message, click_url) を返す。"""
    name = cfg.shop_name or cfg.shop_slug
    title = f"空席が出ました: {name}"
    lines = _slot_lines(new_slots)
    lines.append(f"{cfg.num_people}名/タップで予約ページへ")
    first_date = sorted(new_slots)[0]
    click = reserve_url(cfg, first_date, new_slots[first_date][0])
    return title, "\n".join(lines), click


def run(cfg: Config, state_path: str, *, dry_run: bool = False) -> int:
    now = dt.datetime.now(JST)
    today = now.date()
    prev = load_state(state_path)
    client = TableCheckClient(cfg)

    try:
        avail = client.fetch_availability(target_dates(cfg, today))
    except TableCheckError as e:
        print(f"チェック失敗: {e}")
        if dry_run:
            raise
        state = prev or State()
        state.consecutive_failures += 1
        state.last_checked_at = now.isoformat()
        if (
            state.consecutive_failures >= cfg.failure_warning_threshold
            and not state.failure_notified
        ):
            send_ntfy(
                cfg.ntfy,
                "空席チェックが失敗しています",
                (
                    f"{state.consecutive_failures}回連続でTableCheckの空席チェックに"
                    f"失敗しています。サイト仕様が変わった可能性があります。\n"
                    f"最新のエラー: {e}"
                ),
                priority=3,
                tags=["warning"],
            )
            state.failure_notified = True
        save_state(state_path, state)
        return 0

    avail = filter_availability(avail, cfg, today)
    open_days = len(avail)
    total_slots = sum(len(v) for v in avail.values())
    print(f"取得完了: 空きのある日 {open_days}日 / 合計 {total_slots}枠")

    if dry_run:
        print(json.dumps(avail, ensure_ascii=False, indent=1))
        return 0

    if prev is None:
        # 初回実行: 現状をベースラインとして保存し、開始通知を送る
        name = cfg.shop_name or cfg.shop_slug
        if avail:
            body_lines = _slot_lines(avail)
            body_lines.insert(0, "現在の空き状況:")
        else:
            body_lines = ["現在、監視範囲に空きはありません。", "空きが出たら通知します。"]
        send_ntfy(
            cfg.ntfy,
            f"空席監視を開始しました: {name}",
            "\n".join(body_lines),
            click=reserve_url(cfg),
            priority=3,
            tags=["eyes"],
        )
        print("監視開始通知を送信しました")
    else:
        new = diff_new_slots(prev.availability, avail)
        if new:
            title, msg, click = build_vacancy_message(new, cfg)
            send_ntfy(cfg.ntfy, title, msg, click=click, priority=5, tags=["tada"])
            print(f"空席通知を送信: {sum(len(v) for v in new.values())}枠 ({len(new)}日)")
        else:
            print("新規の空きはありません")

    save_state(
        state_path,
        State(
            availability=avail,
            consecutive_failures=0,
            failure_notified=False,
            last_checked_at=now.isoformat(),
        ),
    )
    return 0
