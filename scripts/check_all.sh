#!/usr/bin/env bash
# 設定済みの全店舗を順番にチェックする。
set -uo pipefail

cd "${GITHUB_WORKSPACE:-.}" || exit 1

mode="${1:-check}"
case "$mode" in
  check)
    command_args=(check)
    ;;
  dry-run)
    command_args=(check --dry-run)
    ;;
  test-notify)
    command_args=(test-notify)
    ;;
  *)
    echo "usage: $0 [check|dry-run|test-notify]" >&2
    exit 2
    ;;
esac

shops=(
  "config.toml:state.json"
  "config.losier.toml:state.losier.json"
)

status=0
for shop in "${shops[@]}"; do
  config="${shop%%:*}"
  state="${shop#*:}"
  echo "=== ${config} ==="
  if python -m tablecheck_watcher "${command_args[@]}" --config "$config" --state "$state"; then
    continue
  else
    status=$?
  fi
  # 429時は同じ実行元から次の店舗へアクセスせず、呼び出し側にバックオフを促す。
  [ "$status" -eq 75 ] && break
done

exit "$status"
