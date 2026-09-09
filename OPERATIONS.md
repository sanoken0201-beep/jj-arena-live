# JJ Arena Production Operations

この文書をJJ Arena本番運用の基準手順とします。

## 1. Production topology

```text
Browser / mobile
  -> https://jj-arena-live.onrender.com
      -> jj-arena-db (Render PostgreSQL / Singapore)
```

`jj-arena-club` は旧公開プロキシです。新しい開発・検証・URL案内では使用しません。

## 2. Production source of truth

- GitHub repository: `sanoken0201-beep/jj-arena-live`
- Production branch: `main`
- ASGI entrypoint: `app:app`
- Database: **既存の `jj-arena-db` のみ**
- Region: Singapore

本番コードは `app.py` が `release_v14` とpatch chainから再構築します。ルート直下の古い `server.py` を直接起動しないでください。

## 3. Normal release flow

1. `main` の最後の正常commitから作業branchを作る。
2. 新しいpatch / UI / admin変更をbranchへ追加する。
3. 最新smoke testを追加・更新する。
4. GitHub Actionsを通す。
5. `main` へ反映する。
6. Renderが新commitを取得したかDeploy画面でSHAを確認する。
7. auto deployが動かなければ、**mainが正しいことを確認した後だけ**手動deployする。
8. `Application startup complete` と health check 200を確認する。
9. `/api/auth/pin`、`/api/me`、`/admin`、quiz、online pokerのエラーをログで確認する。

## 4. Render settings

### Web Service: jj-arena-live

- Plan: `0.5c-512mb`
- Region: Singapore
- Instances: 1
- Build command:

```bash
pip install -r requirements.txt && python smoke_test_v190.py
```

- Start command:

```bash
python -m uvicorn app:app --host 0.0.0.0 --port $PORT
```

- Health check: `/api/health`

### Database: jj-arena-db

- PostgreSQL
- Region: Singapore
- Compute: 0.1 CPU / 256MB
- Storage: 1GB以上

**DBの移行目的以外では `New Postgres` を押さないこと。**

## 5. Environment variables

通常運用で必要なもの:

```text
DATABASE_URL=<Render internal PostgreSQL URL>
JJ_ADMIN_NAME=<管理者のカタカナ名>
JJ_ENABLE_DEMO_MEMBER=0
```

通常運用では次を設定しません。

```text
JJ_ADMIN_PIN
JJ_ADMIN_EMAIL
JJ_ADMIN_LOGIN_EMAIL
JJ_ADMIN_LOGIN_PASSWORD
JJ_ADMIN_PASSWORD
```

古いキーがRenderに残っている場合は空にしてください。

## 6. Administrator PIN recovery

管理者PINを完全に失った場合だけ実行します。

### v1.19.0以降

1. Render -> `jj-arena-live` -> Environment を開く。
2. `JJ_ADMIN_NAME` を対象管理者名にする。
3. `JJ_ADMIN_PIN` に新しい6桁PINを一時設定する。
4. Saveして再デプロイする。
5. Live後、対象名 + 新PINでログインする。
6. 管理画面が開くことを確認する。
7. `JJ_ADMIN_PIN` を空にするか削除し、再デプロイする。
8. ログアウト -> 再ログインしてDBに保存されたPINだけで入れることを確認する。

復旧時には既存sessionを失効させます。これは意図した動作です。

### Shell fallback

通常は不要です。環境変数による復旧が動かない場合だけ、DBを書き換える前にコードとログを確認してください。Shellへ長いPythonコードを直接貼り付ける方式は標準手順にしません。

## 7. Rollback

コード更新後に本番が起動しない場合:

1. DBを変更しない。
2. Render Deploysから最後に正常だったcommit SHAを確認する。
3. GitHub `main` の内容とRender deploy SHAの差を確認する。
4. 最後の正常commitへコードを戻す、またはRenderでそのrevisionを再デプロイする。
5. 起動ログとhealth checkを確認する。

DB migrationが入ったreleaseでは、migrationの後方互換性を保つこと。破壊的 `DROP` / column renameを通常releaseに含めないこと。

## 8. Data integrity rules

- 公式ポイントはpoint ledgerを経由する。
- quiz rewardもpoint ledgerを経由する。
- 同一quiz attemptの二重報酬は禁止する。
- account deletionでは履歴参照を壊さない。
- production DBをSQLiteへ置換しない。
- テーブル/ハンド状態の修正とアカウント修正を同じSQLで行わない。

### Account lifecycle

- 削除は物理DELETEではなくtombstone化する。point ledgerや監査ログの外部キーを壊さないため、DB行自体は保持する。
- `deleted_at IS NOT NULL` のアカウントは、現行・旧管理APIのユーザー一覧から必ず除外する。`include_disabled=true` でも表示しない。
- 削除時は全sessionを失効し、元の名前由来login IDをランダムなtombstone IDへ退避し、元PIN hashもランダムsecretのhashへ置換する。
- ログイン名はNFKC正規化、空白除去、ひらがな→カタカナ変換後の名前から内部login IDを生成する。そのため `てすと` / `テスト` / 前後空白付き表記は同一login identityとして扱う。
- 削除後に同じ正規化名で登録すると、新しい`users.id`と、その登録時に入力した6桁PINの新しいhashでアカウントを作る。削除済み行のPIN hashを継承しない。
- 同じ正規化名の有効アカウントは、内部login IDのUNIQUE制約により同時に1件だけ存在できる。
- `ranking_name` は削除済み行に保持する。これは過去のランキング・ポイント履歴の帰属を維持するためで、再登録された同一プレイヤーの履歴継続に利用する。
- 削除済みuser IDに対する再有効化、PIN reset、session revoke、point操作は管理APIから拒否する。

## 9. Online poker change rules

オンラインポーカー変更は以下を分けます。

- `poker_engine` / game rule変更
- API state / WebSocket変更
- UI / sizing / action bar変更

UI改善だけの場合はgame engineを触らないこと。game rule変更時は最低レイズ、short all-in、side pot、split pot、turn ownership、timeoutを回帰確認します。

## 10. Security hygiene

- PIN・password・DATABASE_URLをcommitしない。
- secret値をRender Start Commandで `echo` しない。
- 管理者復旧用PINを常設しない。
- ログにはcredentialを出さない。
- 管理APIはrole checkを必須にする。
- account/PIN変更後は対象sessionを失効させる。

## 11. Post-deploy checklist

最低限次を確認します。

```text
[ ] Render deploy = expected main SHA
[ ] Application startup complete
[ ] health 200
[ ] normal login succeeds
[ ] /api/me succeeds after login
[ ] /admin opens for admin
[ ] ranking/points load
[ ] quiz question loads
[ ] quiz answer awards once
[ ] poker lobby loads
[ ] table state loads
[ ] WebSocket connects
[ ] no new ERROR logs
```
