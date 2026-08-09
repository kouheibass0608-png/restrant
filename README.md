# TableCheck 空席ウォッチャー

[ガストロノミー "ジョエル・ロブション"](https://www.tablecheck.com/ja/shops/joelrobuchon/reserve)
(恵比寿ガーデンプレイス) の TableCheck 予約枠を定期的にチェックし、
**空席が出たらスマホにプッシュ通知**を送るツールです。

- チェックは **GitHub Actions** が30分ごとに自動実行 (PC不要)
- 通知は **[ntfy](https://ntfy.sh/)** で受信 (無料・アカウント登録不要)
- 通知をタップするとそのまま TableCheck の予約ページが開きます

## 仕組み

```
GitHub Actions (30分ごと)
  └─ tablecheck_watcher
       ├─ TableCheck の予約ページが使う内部API
       │    GET /ja/shops/joelrobuchon/available/timetable
       │  を週単位でページングし、今後60日分の空き枠を取得
       ├─ 前回チェック時の状態 (state.json) と比較して「新たに空いた枠」を検出
       └─ 新たな空きがあれば ntfy にプッシュ通知
            (state.json はリポジトリにコミットして次回に引き継ぐ)
```

- 通知が来るのは「前回チェック時になかった空きが出たとき」だけです (毎回は来ません)
- チェックの失敗が続いた場合 (サイト仕様変更など) は、一度だけ警告通知が届きます

## セットアップ

### 1. ntfy アプリを入れて購読する

1. スマホに ntfy アプリをインストール
   ([iOS](https://apps.apple.com/us/app/ntfy/id1625396347) /
   [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy))
2. アプリで **Subscribe to topic** を選び、**推測されにくいトピック名**を購読する
   - 例: `robuchon-aki-x7k2m9`
   - ⚠️ ntfy.sh のトピックは名前を知っていれば誰でも購読/送信できます。
     必ずランダムな文字列を含めてください。

### 2. GitHub Secrets にトピック名を設定する

リポジトリの **Settings → Secrets and variables → Actions → New repository secret** で:

| Name | Value |
|---|---|
| `NTFY_TOPIC` | 手順1で決めたトピック名 (例: `robuchon-aki-x7k2m9`) |

(セルフホストの認証付き ntfy サーバーを使う場合のみ `NTFY_TOKEN` も設定)

### 3. main ブランチにマージする

定期実行 (cron) は **main ブランチのワークフローだけ**が対象です。
この変更を main にマージした時点から30分ごとのチェックが始まります。

### 4. 動作確認

**Actions → check-availability → Run workflow** から手動実行できます:

| mode | 動作 |
|---|---|
| `test-notify` | テスト通知を送る (ntfy の設定確認) |
| `dry-run` | 空き状況を取得してログに表示するだけ (通知しない) |
| `check` | 本番と同じ動作 (初回は「監視開始」通知が届きます) |

まず `test-notify` でスマホに通知が届くことを確認してください。

## 設定の変更 (`config.toml`)

```toml
[search]
num_people = 2       # 人数
days_ahead = 60      # 何日先まで監視するか
time_ranges = []     # 空 = 全時間帯。ディナーのみなら ["17:00-22:00"]
dates = []           # 特定日だけ監視: ["2026-09-15", "2026-09-22"]
```

変更を main に push すれば次回チェックから反映されます。

- 監視間隔を変えるには `.github/workflows/check.yml` の `cron` を編集してください。
  private リポジトリの Actions 無料枠は月2,000分のため、デフォルトは30分間隔です
  (1回の実行は約1分)。リポジトリを **public にすれば実行時間無制限**なので
  `*/10` などに短縮できます。
- この店舗の予約枠は現在ディナーのみ (16:30〜19:30 開始、30分刻み) です。

## ローカルでの実行

Python 3.11 以上があれば依存パッケージなしで動きます:

```bash
# 空き状況を見るだけ
python -m tablecheck_watcher check --dry-run

# 通知テスト
NTFY_TOPIC=あなたのトピック python -m tablecheck_watcher test-notify

# 本番と同じ動作 (state.json を読み書き)
NTFY_TOPIC=あなたのトピック python -m tablecheck_watcher check
```

## トラブルシューティング

- **「チェックが失敗しています」の通知が来た**:
  TableCheck 側の仕様変更の可能性があります。
  **Actions → probe-tablecheck-api → Run workflow** を実行すると、
  現在のAPIの応答がログに出るので原因調査に使えます。
- **通知が多すぎる/少なすぎる**: `config.toml` の `time_ranges` や `dates` で絞り込めます。

## 注意事項

- TableCheck の公開ドキュメントにない内部APIを利用しているため、
  サイトの仕様変更で動かなくなることがあります (その場合は警告通知が届きます)。
- チェック間隔は30分ごと・1回あたり10リクエスト程度と、
  通常のブラウザ利用より軽い負荷に抑えています。間隔を極端に短くするのは避けてください。
- 空席の確保 (自動予約) は行いません。通知が来たら手動で予約してください。
