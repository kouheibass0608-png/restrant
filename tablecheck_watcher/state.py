"""前回チェック時の空き状況の保存と差分検出。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class State:
    # 日付 (YYYY-MM-DD) -> 空きスロット時刻 ("HH:MM") のソート済みリスト
    availability: dict[str, list[str]] = field(default_factory=dict)
    consecutive_failures: int = 0
    failure_notified: bool = False
    last_checked_at: str = ""


def load_state(path: str | Path) -> State | None:
    """状態を読み込む。ファイルがなければ None (= 初回実行)。"""
    path = Path(path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return State(
        availability={str(k): sorted(v) for k, v in data.get("availability", {}).items()},
        consecutive_failures=int(data.get("consecutive_failures", 0)),
        failure_notified=bool(data.get("failure_notified", False)),
        last_checked_at=str(data.get("last_checked_at", "")),
    )


def save_state(path: str | Path, state: State) -> None:
    payload = {
        "availability": {k: sorted(v) for k, v in sorted(state.availability.items())},
        "consecutive_failures": state.consecutive_failures,
        "failure_notified": state.failure_notified,
        "last_checked_at": state.last_checked_at,
    }
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


def diff_new_slots(
    prev: dict[str, list[str]], cur: dict[str, list[str]]
) -> dict[str, list[str]]:
    """前回は空いていなかったが今回空いているスロットを返す。"""
    new: dict[str, list[str]] = {}
    for date, slots in cur.items():
        added = sorted(set(slots) - set(prev.get(date, [])))
        if added:
            new[date] = added
    return new
