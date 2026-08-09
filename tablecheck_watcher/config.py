"""config.toml と環境変数から設定を読み込む。"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(Exception):
    pass


@dataclass
class NtfyConfig:
    server: str = "https://ntfy.sh"
    topic: str = ""
    token: str = ""


@dataclass
class Config:
    shop_slug: str = "joelrobuchon"
    shop_name: str = ""
    locale: str = "ja"
    # 監視する人数。複数指定でき、それぞれ別々に空きを確認する。
    party_sizes: list[int] = field(default_factory=lambda: [2])
    days_ahead: int = 60
    time_ranges: list[str] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    failure_warning_threshold: int = 12
    ntfy: NtfyConfig = field(default_factory=NtfyConfig)
    api_base_url: str = "https://production.tablecheck.com/v2"
    request_timeout: float = 30.0
    request_interval: float = 1.0

    @property
    def reserve_page_url(self) -> str:
        return f"https://www.tablecheck.com/{self.locale}/shops/{self.shop_slug}/reserve"


def load_config(path: str | Path = "config.toml") -> Config:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"設定ファイルが見つかりません: {path}")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"設定ファイルの形式が不正です: {e}") from e

    shop = data.get("shop", {})
    search = data.get("search", {})
    notify = data.get("notify", {})
    ntfy = notify.get("ntfy", {})
    api = data.get("api", {})

    cfg = Config(
        shop_slug=shop.get("slug", "joelrobuchon"),
        shop_name=shop.get("name", ""),
        locale=shop.get("locale", "ja"),
        party_sizes=_parse_party_sizes(search.get("num_people", [2])),
        days_ahead=int(search.get("days_ahead", 60)),
        time_ranges=list(search.get("time_ranges", [])),
        dates=[str(d) for d in search.get("dates", [])],
        failure_warning_threshold=int(notify.get("failure_warning_threshold", 12)),
        ntfy=NtfyConfig(
            server=ntfy.get("server", "https://ntfy.sh"),
            topic=ntfy.get("topic", ""),
            token=ntfy.get("token", ""),
        ),
        api_base_url=api.get("base_url", "https://production.tablecheck.com/v2"),
        request_timeout=float(api.get("request_timeout", 30)),
        request_interval=float(api.get("request_interval", 1.0)),
    )

    # 秘密情報は環境変数を優先 (GitHub Actions では Secrets から渡す)
    cfg.ntfy.server = os.environ.get("NTFY_SERVER", "") or cfg.ntfy.server
    cfg.ntfy.topic = os.environ.get("NTFY_TOPIC", "") or cfg.ntfy.topic
    cfg.ntfy.token = os.environ.get("NTFY_TOKEN", "") or cfg.ntfy.token

    for r in cfg.time_ranges:
        _parse_range(r)  # 形式チェック (不正なら ConfigError)

    return cfg


def _parse_party_sizes(raw: object) -> list[int]:
    """num_people を人数のリストに正規化する。

    単一の整数 (num_people = 2) とリスト (num_people = [1, 2]) の両方を受け付ける。
    """
    values = [raw] if isinstance(raw, int) else raw
    if not isinstance(values, (list, tuple)) or not values:
        raise ConfigError(
            f"num_people は人数、または人数のリストで指定してください: {raw!r}"
        )
    sizes: list[int] = []
    for v in values:
        if isinstance(v, bool) or not isinstance(v, int):
            raise ConfigError(f"num_people に数値以外が含まれています: {v!r}")
        if v < 1:
            raise ConfigError(f"num_people は1以上で指定してください: {v}")
        sizes.append(v)
    return sorted(set(sizes))


def _parse_range(r: str) -> tuple[str, str]:
    try:
        start, end = r.split("-")
        for t in (start, end):
            h, m = t.split(":")
            if not (0 <= int(h) <= 23 and 0 <= int(m) <= 59):
                raise ValueError(t)
        return start, end
    except (ValueError, AttributeError) as e:
        raise ConfigError(
            f"time_ranges の形式が不正です: {r!r} ('HH:MM-HH:MM' で指定してください)"
        ) from e
