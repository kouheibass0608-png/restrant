#!/usr/bin/env bash
# state.json に変化があればコミットして push する。
# 監視ループから毎回呼ばれるため、変化が無いときは何もしない。
set -uo pipefail

cd "${GITHUB_WORKSPACE:-.}" || exit 1

[ -n "$(git status --porcelain state.json)" ] || exit 0

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add state.json
git commit -m "chore: update availability state" || exit 0

# 他の実行が先に push している場合があるので、rebase して数回リトライする。
for attempt in 1 2 3; do
  if git push; then
    exit 0
  fi
  echo "push に失敗しました (試行 ${attempt}/3)。rebase して再試行します。"
  git pull --rebase --autostash || true
  sleep $(( attempt * 2 ))
done

# push できなくても監視自体は続けたいので、警告に留める。
# 未 push のコミットは次回の実行で checkout し直されて消えるが、
# state.json は次のチェックで作り直されるため実害はない。
echo "::warning::state.json の push に失敗しました (監視は継続します)"
exit 0
