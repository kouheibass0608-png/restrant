"""ntfy への通知送信。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .config import NtfyConfig


class NotifyError(Exception):
    pass


def send_ntfy(
    cfg: NtfyConfig,
    title: str,
    message: str,
    *,
    click: str | None = None,
    priority: int = 4,
    tags: list[str] | None = None,
    timeout: float = 30.0,
) -> None:
    """ntfy に通知を送る。日本語を扱うため JSON publish 形式を使う。"""
    if not cfg.topic:
        raise NotifyError(
            "ntfy の topic が未設定です。環境変数 NTFY_TOPIC "
            "(GitHub Actions では Secrets) か config.toml で設定してください。"
        )
    body: dict = {
        "topic": cfg.topic,
        "title": title,
        "message": message,
        "priority": priority,
    }
    if click:
        body["click"] = click
    if tags:
        body["tags"] = tags

    headers = {"Content-Type": "application/json"}
    if cfg.token:
        headers["Authorization"] = f"Bearer {cfg.token}"

    req = urllib.request.Request(
        cfg.server.rstrip("/"),
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status >= 300:
                raise NotifyError(f"ntfy がエラーを返しました: HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        raise NotifyError(f"ntfy がエラーを返しました: HTTP {e.code} {e.read()[:200]!r}") from e
    except urllib.error.URLError as e:
        raise NotifyError(f"ntfy に接続できません: {e.reason}") from e
