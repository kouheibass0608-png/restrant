"""メインロジック: 空き状況の取得 → 差分検出 → 通知 → 状態保存。"""

from __future__ import annotations

import datetime as dt
import json
from zoneinfo import ZoneInfo

from .config import Config
from .notify import send_ntfy
from .state import Availability, State, diff_new_slots, load_state, save_state
from .tablecheck import TableCheckClient, TableCheckError

JST = ZoneInfo("Asia/Tokyo")
WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"]

MAX_DATES_IN_MESSAGE = 10
MAX_TIMES_PER_DATE = 8

# state.json を更新する最低頻度。空き状況に変化がなくても、この間隔で
# last_checked_at を書き換えてリポジトリに活動を発生させる。
# GitHub は「60日間活動のない public リポジトリの定期実行を自動停止」するため。
HEARTBEAT_INTERVAL = dt.timedelta(days=7)


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


def heartbeat_due(last_checked_at: str, now: dt.datetime) -> bool:
    """前回記録から HEARTBEAT_INTERVAL 以上経過していれば True。

    記録が無い/壊れている場合も True (書き直して回復させる)。
    """
    try:
        last = dt.datetime.fromisoformat(last_checked_at)
    except (TypeError, ValueError):
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=JST)
    return now - last >= HEARTBEAT_INTERVAL


def format_date_ja(date_s: str) -> str:
    d = dt.date.fromisoformat(date_s)
    return f"{d.month}/{d.day}({WEEKDAYS_JA[d.weekday()]})"


def reserve_url(
    cfg: Config, num_people: int, date_s: str | None = None, hhmm: str | None = None
) -> str:
    url = (
        f"https://www.tablecheck.com/{cfg.locale}/shops/{cfg.shop_slug}/reserve"
        f"?num_people={num_people}"
    )
    if date_s:
        url += f"&start_date={date_s}"
        if hhmm:
            h, m = hhmm.split(":")
            url += f"&start_time={int(h) * 3600 + int(m) * 60}"
    return url


def _slot_lines(days: dict[str, list[str]]) -> list[str]:
    lines = []
    for date in sorted(days)[:MAX_DATES_IN_MESSAGE]:
        times = days[date]
        shown = "・".join(times[:MAX_TIMES_PER_DATE])
        if len(times) > MAX_TIMES_PER_DATE:
            shown += " ほか"
        lines.append(f"{format_date_ja(date)} {shown}")
    rest = len(days) - MAX_DATES_IN_MESSAGE
    if rest > 0:
        lines.append(f"…ほか{rest}日にも空きあり")
    return lines


def _availability_lines(avail: Availability, *, label_sizes: bool) -> list[str]:
    """人数の多い順に空き枠を並べる (先頭が予約リンクの対象)。"""
    lines: list[str] = []
    for size in sorted(avail, reverse=True):
        if not avail[size]:
            continue
        if label_sizes:
            lines.append(f"【{size}名】")
        lines.extend(_slot_lines(avail[size]))
    return lines


def build_vacancy_message(new_slots: Availability, cfg: Config) -> tuple[str, str, str]:
    """(title, message, click_url) を返す。"""
    name = cfg.shop_name or cfg.shop_slug
    label_sizes = len(cfg.party_sizes) > 1
    lines = _availability_lines(new_slots, label_sizes=label_sizes)

    # 予約リンクは、空きが出た中で最も人数の多い枠に合わせる
    # (メッセージの先頭に表示している枠と一致させる)
    top = max(size for size, days in new_slots.items() if days)
    first_date = sorted(new_slots[top])[0]
    lines.append(
        "タップで予約ページへ" if label_sizes else f"{top}名/タップで予約ページへ"
    )
    click = reserve_url(cfg, top, first_date, new_slots[top][first_date][0])
    return f"空席が出ました: {name}", "\n".join(lines), click


def _count_slots(avail: Availability) -> int:
    return sum(len(times) for days in avail.values() for times in days.values())


def run(cfg: Config, state_path: str, *, dry_run: bool = False) -> int:
    now = dt.datetime.now(JST)
    today = now.date()
    prev = load_state(state_path)
    client = TableCheckClient(cfg)
    dates = target_dates(cfg, today)

    try:
        avail: Availability = {
            size: filter_availability(client.fetch_availability(dates, size), cfg, today)
            for size in cfg.party_sizes
        }
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

    for size in cfg.party_sizes:
        days = avail[size]
        slots = sum(len(t) for t in days.values())
        print(f"取得完了 ({size}名): 空きのある日 {len(days)}日 / 合計 {slots}枠")

    if dry_run:
        print(json.dumps(avail, ensure_ascii=False, indent=1))
        return 0

    if prev is None:
        # 初回実行 (または保存形式の変更後): 現状をベースラインとして保存し、開始通知を送る
        name = cfg.shop_name or cfg.shop_slug
        if _count_slots(avail):
            body_lines = ["現在の空き状況:"]
            body_lines += _availability_lines(avail, label_sizes=True)
        else:
            sizes_label = "・".join(f"{n}名" for n in cfg.party_sizes)
            body_lines = [
                f"現在、監視範囲 ({sizes_label}) に空きはありません。",
                "空きが出たら通知します。",
            ]
        send_ntfy(
            cfg.ntfy,
            f"空席監視を開始しました: {name}",
            "\n".join(body_lines),
            click=reserve_url(cfg, max(cfg.party_sizes)),
            priority=3,
            tags=["eyes"],
        )
        print("監視開始通知を送信しました")
    else:
        new = diff_new_slots(prev.availability, avail)
        if new:
            title, msg, click = build_vacancy_message(new, cfg)
            send_ntfy(cfg.ntfy, title, msg, click=click, priority=5, tags=["tada"])
            print(f"空席通知を送信: {_count_slots(new)}枠")
        else:
            print("新規の空きはありません")

    # 毎回 last_checked_at を書き換えると実行のたびに state.json が変化し、
    # チェック間隔ぶんのコミットが積み上がってしまう。空き状況が変わったとき
    # (と週1回のハートビート) だけ更新し、それ以外は前回の内容を保つ。
    if prev is None or avail != prev.availability or heartbeat_due(prev.last_checked_at, now):
        last_checked_at = now.isoformat()
    else:
        last_checked_at = prev.last_checked_at

    save_state(
        state_path,
        State(
            availability=avail,
            consecutive_failures=0,
            failure_notified=False,
            last_checked_at=last_checked_at,
        ),
    )
    return 0
