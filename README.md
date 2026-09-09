# JJ Arena Live

JJ Poker Club向けの共有Webアプリです。ランキング、公式ポイント、活動予定、学習、管理機能、プレイマネーのリアルタイムNLHを統合しています。

**現金・換金・賭け金機能はありません。** オンライン卓のArena chipsは練習用プレイマネーで、公式JJポイントとは分離されています。

## 現在の本番構成

```text
user
  -> jj-arena-live (Render Web Service / Singapore / 0.5 CPU 512MB)
      -> jj-arena-db (Render PostgreSQL / Singapore / 0.1 CPU 256MB / 1GB)
```

本番入口は `jj-arena-live` です。`jj-arena-club` は旧プロキシであり、新しい実装では依存先にしません。

## 重要: 本番の起動方式

本番のASGI entrypointは **`app.py` の `app`** です。

```bash
python -m uvicorn app:app --host 0.0.0.0 --port $PORT
```

ルート直下の古い `server.py` / `db.py` を直接起動する構成ではありません。`app.py` は検証済みの `release_v14` を展開し、`v15_patch.py` 以降のパッチを順番に適用して `/tmp/jj_arena_v39_runtime` に現在のランタイムを再構築します。

したがって、変更時は次のルールを守ります。

1. 既存の動作を変える場合は最新パッチを追加する。
2. 過去パッチを後から書き換えない。
3. 最新smoke testでv1.4からの完全再構築を必ず検証する。
4. `app.py` の適用順序と最新runtime pathを更新する。
5. CI成功後にのみmainへ反映する。

このパッチ連鎖は互換性維持のため当面残していますが、将来的にはmaterialized runtimeへ縮約する予定です。

## 認証

現在のユーザー認証は次の方式です。

- カタカナ表示名 + 6桁PIN
- PBKDF2-SHA256 hashing
- Admin / Member role
- session cookie
- ログイン試行回数制限

旧Email + Password認証は廃止済みです。

### 管理者復旧

通常運用では `JJ_ADMIN_PIN` を設定しません。管理者PINを失った場合だけ、Renderの `jj-arena-live` Environmentに一時的に設定します。

```text
JJ_ADMIN_NAME=<管理者のカタカナ名>
JJ_ADMIN_PIN=<新しい6桁PIN>
```

v1.19.0以降は、再デプロイ時に既存管理者のPIN hashも確実に更新し、既存sessionを失効させます。復旧後は `JJ_ADMIN_PIN` を空にするか削除してください。

## 主な機能

### Club

- シーズン / 月間ランキング
- 公式ポイント台帳
- 管理者によるポイント振込・回収
- 活動予定・告知
- 戦略議論
- ポーカークイズ
- クイズ回答ごとの公式ポイント報酬
- 管理者コンソール
- アカウント停止・復旧・削除

### Realtime Poker

- 2 / 6 / 8 / 9-max
- 着席 / 離席 / 退席 / Rebuy
- SB / BB / BTNローテーション
- Preflop / Flop / Turn / River
- Fold / Check / Call / Raise / All-in
- 最低レイズ・short all-in・side pot・split pot
- 非手番操作のサーバー拒否
- action timer
- WebSocket同期 + HTTP fallback
- DBへのテーブル状態保存
- スマートフォン縦画面向けポーカーUI

## 開発環境

Pythonは `.python-version` で本番と同じバージョンへ固定します。

```bash
python -m pip install -r requirements.txt
python smoke_test_v190.py
```

本番相当の起動確認は次です。

```bash
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

SQLiteを使う開発モードと、`DATABASE_URL` があるPostgreSQLモードの両方をサポートします。

## テスト / CI

GitHub Actionsはpushとpull requestで最低限次を検証します。

- Python syntax compile
- v1.4 release bundleのchecksum
- v15〜最新patchの完全再構築
- 最新version marker
- 管理者PIN復旧 regression
- ポーカークイズのserver-authoritative reward
- ポーカー操作性 regression
- UI用語監査

最新の主テストは `smoke_test_v190.py` です。

## Render

リポジトリの `render.yaml` は現在の本番構成に合わせています。

- Region: Singapore
- Web compute: 0.5 CPU / 512MB
- Build: dependencies + `smoke_test_v190.py`
- Start: `python -m uvicorn app:app ...`
- Health check: `/api/health`

**既存の `jj-arena-db` を維持してください。新しいPostgreSQLを作成しないでください。**

## 運用上の原則

- production DBを作り直さない
- ポイント履歴を直接上書きせず台帳経由で処理する
- 管理者PINをGitHub・チャット・ログへ保存しない
- Renderの起動コマンドでcredentialを生成・echoしない
- 変更はbranch -> CI -> main -> Render -> logsの順で確認する
- poker engine変更とUI変更を同一修正で混在させない
- 本番障害時はDBを触る前に最後の正常commitへrollbackする

詳しい復旧・デプロイ手順は `OPERATIONS.md` を参照してください。
