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

現在のproduction coreは、検証済みv1.24.4 Golden Masterをコミット済みソースとして固定した **`materialized_v1244/`** です。`app_materialized.py` がこのcoreを読み込み、管理・学習・分析・レジリエンス・性能・セキュリティ等のroot-level extensionを既定順序で適用します。`app.py` はRender-facingの安定entrypointで、materialized coreを直接変更せずにproduction統合を行います。

旧 `release_v14` + patch chainによるruntime再構築はproduction startupでは使用しません。旧経路は **`app_legacy.py`** と `runtime_builder.py` に残してあり、parity検証と緊急rollbackの基準として利用します。

### Browser asset build

`materialized_v1244/static` もimmutableな入力です。プレイヤーUXの各transformは `served_assets.py` に集約され、Render build中に `build_served_assets.py` が完成版を `.jj_build/` へ生成します。manifestにはcanonical sourceと生成物のSHA-256を保存し、production startupでは検証済み生成物を読むだけです。

- production runtimeでUX transform chainを実行しない
- productionで `.jj_build/` が欠けている場合はfail closedする
- local/test環境だけは互換性のため不足時に生成可能
- `.jj_build/` はgenerated artifactでありGit管理しない

### Core変更の原則

1. `materialized_v1244/` はcanonical coreとして原則変更しない。
2. 通常の改善はroot-level extension / integration shimで行う。
3. game rule変更とUI変更を同一修正で混在させない。
4. materialized coreとのparity・production entrypoint・PostgreSQL・browser regressionをCIで維持する。
5. CI成功後にのみ `main` へ反映する。
6. production DBは既存の `jj-arena-db` を継続利用し、通常releaseで破壊的migrationを行わない。

## Canonical project memory

長期開発ではChatGPTの会話履歴をプロジェクトの正本として扱いません。新しい開発チャットや引き継ぎでは、まず次を確認してください。

1. `docs/PROJECT_STATE.md` — 現在の正しいプロジェクト状態と情報源の優先順位
2. `ARCHITECTURE_STATUS.md` — active / compatibility-only / retired の分類
3. `docs/DECISION_LOG.md` — 将来も維持すべき設計・運用判断と理由
4. 対象機能のdomain document（例: `docs/SITNGO_GAMEPLAY.md`）
5. production作業なら `OPERATIONS.md`
6. 必要な場合のみ最新のchat handoff

チャットが長くなった場合は全文を次のチャットへ移さず、`docs/CHAT_HANDOFF_TEMPLATE.md` を使います。永続すべき内容はGitHub上のcode/tests/docsへ昇格させ、古いChatGPT会話は依存先にしません。

## 認証

現在のユーザー認証は次の方式です。

- カタカナ表示名 + 6桁PIN
- PBKDF2-SHA256 hashing
- Admin / Member role
- HttpOnly session cookie
- 本番では `__Host-` session cookie
- ログイン / PIN確認の試行回数制限
- same-origin / Fetch MetadataによるCSRF防御

旧Email + Password認証は廃止済みです。

### 管理者復旧

通常運用では `JJ_ADMIN_PIN` を設定しません。管理者PINを失った場合だけ、Renderの `jj-arena-live` Environmentに一時的に設定します。

```text
JJ_ADMIN_NAME=<管理者のカタカナ名>
JJ_ADMIN_PIN=<新しい6桁PIN>
```

再デプロイ時に対象管理者のPIN hashを更新し、既存sessionを失効させます。復旧後は `JJ_ADMIN_PIN` を空にするか削除してください。

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
- 管理監査ログ / resilience確認

### Realtime Poker

- 2 / 6 / 8 / 9-max engine support
- JJ本番ロビーは1卓・6-max・150bb固定
- 着席 / 離席 / 退席 / Rebuy
- SB / BB / BTNローテーション
- Preflop / Flop / Turn / River
- Fold / Check / Call / Raise / All-in
- 最低レイズ・short all-in・side pot・split pot
- 非手番操作のサーバー拒否
- 45秒 action timer
- WebSocket同期 + HTTP fallback
- イベント駆動の次hand / forced runout / timeout進行
- PostgreSQL connection pool
- DBへのテーブル状態保存 + 状態backup
- スマートフォン縦画面向けポーカーUI
- participant-only hand review
- privacy-preserving UX telemetry

## 開発環境

Pythonは `.python-version` で本番と同じバージョンへ固定します。

```bash
python -m pip install -r requirements.txt
python build_served_assets.py
python smoke_test_v190.py
```

`smoke_test_v190.py` 自体もserved asset buildを実行するため、Renderの既存build commandとの互換性があります。

本番相当の起動確認は次です。

```bash
python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

SQLiteを使う開発モードと、`DATABASE_URL` があるPostgreSQLモードの両方をサポートします。

## テスト / CI

GitHub Actionsはpushとpull requestで、主に次を検証します。

- Python syntax compile
- deterministic served asset build / manifest integrity
- final served JavaScript syntax
- materialized core reproducibility / parity
- production entrypoint startup
- PostgreSQL 18 integration
- 認証・WebSocket auth・card privacy
- 公式ポイント / quiz reward / ranking
- poker engine / settlement / timeout / runout
- hand analytics / stat definitions
- runtime performance regression
- served asset / cache / encoding contract
- desktop / mobile Chromium regression
- UI用語・アクセシビリティ関連の回帰

`smoke_test_v190.py` はRender buildとの互換entrypointとして維持されています。詳細な本番release手順は `OPERATIONS.md` を参照してください。

## Render

リポジトリの `render.yaml` は現在の本番構成に合わせています。

- Region: Singapore
- Web compute: 0.5 CPU / 512MB
- Build compatibility entrypoint: `smoke_test_v190.py`（served assetsも生成）
- Start: `python -m uvicorn app:app ...`
- Health check: `/api/health`

**既存の `jj-arena-db` を維持してください。新しいPostgreSQLを作成しないでください。**

## 運用上の原則

- `materialized_v1244/` を通常改善の直接編集先にしない
- production DBを作り直さない
- ポイント履歴を直接上書きせず台帳経由で処理する
- 管理者PINをGitHub・チャット・ログへ保存しない
- Renderの起動コマンドでcredentialを生成・echoしない
- 変更はbranch -> CI -> main -> Render -> logsの順で確認する
- poker engine変更とUI変更を同一修正で混在させない
- 本番障害時はDBを触る前に最後の正常commitへrollbackする
- `app_legacy.py` / historical patch chainはparity・rollback参照として保持する

詳しい復旧・デプロイ手順は `OPERATIONS.md` を参照してください。
