"""前回チェック時の空き状況の保存と差分検出。

空き状況は人数別に保持する:
    {人数: {日付 "YYYY-MM-DD": [空き時刻 "HH:MM", ...]}}
JSON のキーは文字列になるため、保存時に str・読み込み時に int へ変換する。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# 人数 -> 日付 -> 空き時刻
Availability = dict[int, dict[str, list[str]]]


@dataclass
class State:
    availability: Availability = field(default_factory=dict)
    consecutive_failures: int = 0
    failure_notified: bool = False
    last_checked_at: str = ""


def _parse_availability(raw: object) -> Availability | None:
    """保存形式を検証しつつ復元する。形式が違えば None。

    人数別になる前の旧形式 ({日付: [時刻]}) もここで弾かれ、
    呼び出し側では「記録なし」として扱われる。
    """
    if not isinstance(raw, dict):
        return None
    out: Availability = {}
    for size, days in raw.items():
        try:
            size_i = int(size)
        except (TypeError, ValueError):
            return None
        if not isinstance(days, dict):
            return None
        parsed_days: dict[str, list[str]] = {}
        for date, slots in days.items():
            if not isinstance(slots, list) or not all(isinstance(s, str) for s in slots):
                return None
            parsed_days[str(date)] = sorted(slots)
        out[size_i] = parsed_days
    return out


def load_state(path: str | Path) -> State | None:
    """状態を読み込む。ファイルが無い/壊れている/形式が古い場合は None。"""
    path = Path(path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    availability = _parse_availability(data.get("availability", {}))
    if availability is None:
        return None
    return State(
        availability=availability,
        consecutive_failures=int(data.get("consecutive_failures", 0)),
        failure_notified=bool(data.get("failure_notified", False)),
        last_checked_at=str(data.get("last_checked_at", "")),
    )


def save_state(path: str | Path, state: State) -> None:
    payload = {
        "availability": {
            str(size): {d: sorted(t) for d, t in sorted(days.items())}
            for size, days in sorted(state.availability.items())
        },
        "consecutive_failures": state.consecutive_failures,
        "failure_notified": state.failure_notified,
        "last_checked_at": state.last_checked_at,
    }
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


def diff_new_slots(prev: Availability, cur: Availability) -> Availability:
    """前回は空いていなかったが今回空いている枠を人数別に返す。"""
    new: Availability = {}
    for size, days in cur.items():
        prev_days = prev.get(size, {})
        added_days: dict[str, list[str]] = {}
        for date, slots in days.items():
            added = sorted(set(slots) - set(prev_days.get(date, [])))
            if added:
                added_days[date] = added
        if added_days:
            new[size] = added_days
    return new
