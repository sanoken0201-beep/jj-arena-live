# JJ Arena Live

JJ Poker Club向けの共有Webアプリです。`JJ 2026 Summer Season` の229件を初期データとして搭載し、ランキング・予定・告知・学習・戦略議論・リアルタイムNLHを1つに統合しています。

## 実装済み

### Club
- 総合ランキング / 月間ランキング
- Summer Season実績229件を初期投入
- 管理者限定の公式ポイント入力
  - `残りチップ - (リエントリー + 1) × 初期点数`
- 活動予定（日付・時間・教室・メモ）
- JJ内告知 / 外部イベント告知
- 戦略議論スレッド + 返信
- Pot Odds Sprint

### Realtime Poker
- 2 / 6 / 8 / 9-max テーブル作成
- 観戦 / 着席 / プレイマネーバイイン / キャッシュアウト
- SB / BB、BTNローテーション
- 2枚のホールカードを各ユーザーにのみ配信
- Preflop / Flop / Turn / River
- Fold / Check / Call / Raise / All-in
- 最低レイズ額管理
- short all-inでアクションがre-openしないルール
- サイドポット
- split pot
- 7枚からの役判定
- 非手番操作のサーバー拒否
- 45秒アクションタイマー（可能ならCheck、otherwise Fold）
- テーブルチャット
- WebSocketリアルタイム同期 + 切断時HTTP polling fallback + 再接続
- ハンド進行状態をDBへ保存

**現金・換金・賭け金機能はありません。** Arena chipsは練習用プレイマネーで、公式JJポイントとも分離しています。

## 認証

- Email + Password
- PBKDF2-SHA256 password hashing
- 30日session token
- Admin / Member role

本番では管理者資格情報を環境変数 `JJ_ADMIN_NAME` / `JJ_ADMIN_EMAIL` / `JJ_ADMIN_PASSWORD` から初期化します。固定の管理者パスワードはRenderへデプロイしません。ローカル開発時のみ、環境変数がない場合に開発用フォールバックを使用します。

## ローカル起動

Python 3.11+ を推奨します。

```bash
pip install -r requirements.txt
python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

Windowsでは `START_JJ_ARENA_LIVE.bat` を実行できます。

ブラウザ: `http://localhost:8000`

DBはデフォルトで `jj_arena.db` に作成されます。別の場所に保存する場合:

```bash
JJ_DB_PATH=/path/to/jj_arena.db python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

## テスト

```bash
pytest -q
```

対象には、役判定、ヘッズアップ進行、private hole cards、out-of-turn拒否、short BB、side pots、Summerランキング、admin権限、2ユーザー着席、WebSocket初期同期が含まれます。

## クラウド配備

`Dockerfile` と `render.yaml` を同梱しています。RenderではWebSocket対応の単一Web Service + PostgreSQLを想定しています。ローカル開発ではSQLiteを自動使用します。

### Render想定
- Health check: `/api/health`
- Database: PostgreSQL (`DATABASE_URL`)
- HTTPとWebSocketを同じservice/portで提供

## 本番公開前チェック

1. 本番管理者パスワードはRender環境変数だけに保存
2. HTTPS環境のみで公開
3. 本番ではsessionをHttpOnly Secure Cookieへ移行（現在はSPA互換のBearer token）
4. 定期DBバックアップ
5. 利用規約・プライバシー文言
6. JJ会員本人と表示名の紐付け方法を決定
7. オンライン卓はplay-money限定を維持

## ファイル構成

- `server.py` — FastAPI API / auth / WebSocket / realtime hub
- `poker_engine.py` — NLH game engine / hand evaluation / side pots
- `db.py` — SQLite/PostgreSQL schema / session / Summer seed
- `static/index.html` — SPA
- `static/app.js` — frontend / WebSocket client
- `static/styles.css` — responsive UI
- `data/seed.json` — JJ 2026 Summer seed (229 entries)
- `tests/` — automated tests
- `Dockerfile`, `render.yaml` — deployment

## Render deployment (2026-09-06)

The app supports both local SQLite and Render Postgres.

- Local: no `DATABASE_URL` -> SQLite is used.
- Cloud: set `DATABASE_URL` -> PostgreSQL is used automatically.
- Render region: Singapore is recommended for JJ users in Japan.
- Build command: `pip install -r requirements.txt`
- Start command: `python -m uvicorn server:app --host 0.0.0.0 --port $PORT`
- Health check: `/api/health`

A Render Free Postgres instance named `jj-arena-db` can be attached by setting its internal database URL as the `DATABASE_URL` environment variable on the web service. The database schema and Summer seed data initialize automatically on first boot.
