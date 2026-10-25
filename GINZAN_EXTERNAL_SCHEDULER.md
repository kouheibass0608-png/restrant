# 銀山温泉・12月13日宿泊：5〜10分おきの外部起動設定

## 目的

`check-ginzan-onsen` のGitHub標準 `schedule` が15分設定にもかかわらず、
実際には数時間おきになったため、外部サービスで `workflow_dispatch` を呼ぶ。
**既存のPython監視ロジック、ntfyの通知先、状態ファイルはそのまま使う。**

外部サービス側のスケジューリングとGitHubジョブ起動には多少の遅延があるため、
「必ず5分以内に通知する」という保証はない。

## 設定方法（cron-job.org）

1. [cron-job.org](https://cron-job.org/en/) でアカウントを作成。
2. GitHubの [Fine-grained personal access tokens](https://github.com/settings/personal-access-tokens/new)
   でトークンを作成する。
   - Repository access → Only select repositories → `kouheibass0608-png/restrant`
   - Repository permissions → **Actions: Read and write**
   - Expiration → 2026-12-14頃（宿泊終了後に自動失効するよう短期間で設定）
   - 発行されたトークンは安全に保管し、GitHubのファイルやチャットに貼らない。
3. cron-job.orgで **Create cronjob** を選択。
   - Name: `Ginzan Onsen vacancy checker`
   - URL: `https://api.github.com/repos/kouheibass0608-png/restrant/actions/workflows/check-ginzan.yml/dispatches`
   - Schedule: **Every 5 minutes**（より低負荷なら10分ごと）
   - Request method: **POST**
   - Request headers:
     - `Authorization: Bearer <2で生成したGitHub PAT>`
     - `Accept: application/vnd.github+json`
     - `X-GitHub-Api-Version: 2022-11-28`
     - `Content-Type: application/json`
   - Request body（JSON）:
   
```json
{"ref":"main","inputs":{"mode":"check"}}
```

4. cron-job.orgの **Test run** を実行し、HTTP **204 No Content** が返ることを確認。
   `401/403` はトークンや権限の問題、`404` はURLやワークフロー名を確認。
5. GitHub の [check-ginzan-onsenの実行履歴](https://github.com/kouheibass0608-png/restrant/actions/workflows/check-ginzan.yml)
   に `workflow_dispatch` による新規実行が現れることを確認。
6. 監視の重複実行は `concurrency` で制御され、既存の
   `state.ginzan.json` で同じ客室リンクへの重複通知を避ける。

## 大事な注意事項

- **このファイルだけで外部スケジューラーは開始しない。**
  実際の起動には本人によるcron-job.orgアカウント設定が必要。
- PATは、指定リポジトリのActionsを起動する権限を持つ。
  cron-job.orgに保存する前にサービスとプライバシー条件を確認すること。
  トークンをURLクエリ文字列には絶対に入れない。
- GitHubの `schedule` は予備として残す。
  外部起動が安定したらGitHub側の定期実行頻度を下げることも検討する。
- 予約サイトへのアクセスは5施設の1回チェックにつき約5回。
  公開予約サイトへの過度なアクセスは避け、要求が拒否されたら間隔を広げる。
- 12月13日を過ぎるとPythonは判定を終了するが、外部cron-jobは自動停止されない。
  宿泊日を過ぎたらcron-job.orgでジョブを無効化・削除し、PATも失効させる。
- この監視は空室候補の検知であり、予約成立や希望人数での予約可能性を保証しない。
