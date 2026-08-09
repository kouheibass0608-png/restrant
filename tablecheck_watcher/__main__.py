"""CLI エントリポイント: python -m tablecheck_watcher [check|test-notify]"""

from __future__ import annotations

import argparse
import sys

from . import watcher
from .config import ConfigError, load_config
from .notify import NotifyError, send_ntfy


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tablecheck_watcher", description="TableCheck 空席監視")
    p.add_argument("command", nargs="?", default="check", choices=["check", "test-notify"])
    p.add_argument("--config", default="config.toml", help="設定ファイルのパス")
    p.add_argument("--state", default="state.json", help="状態ファイルのパス")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="空き状況を表示するだけで、通知も状態保存もしない",
    )
    args = p.parse_args(argv)

    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        print(f"設定エラー: {e}", file=sys.stderr)
        return 2

    try:
        if args.command == "test-notify":
            send_ntfy(
                cfg.ntfy,
                "テスト通知",
                f"{cfg.shop_name or cfg.shop_slug} の空席監視からのテスト通知です。",
                click=cfg.reserve_page_url,
                priority=3,
                tags=["white_check_mark"],
            )
            print("テスト通知を送信しました")
            return 0
        return watcher.run(cfg, args.state, dry_run=args.dry_run)
    except NotifyError as e:
        print(f"通知エラー: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
