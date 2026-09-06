from __future__ import annotations
from pathlib import Path
import re


def apply(root: Path) -> None:
    _server(root/'server.py')
    _app(root/'static'/'app.js')
    _index(root/'static'/'index.html')
    _sw(root/'static'/'sw.js')


def _server(p: Path) -> None:
    s=p.read_text(encoding='utf-8')
    s=s.replace('version="1.18.0"','version="1.18.3"').replace('"version":"1.18.0"','"version":"1.18.3"')
    s=s.replace('request.url.query == "v=34"','request.url.query == "v=35"')
    p.write_text(s,encoding='utf-8')


def _app(p: Path) -> None:
    s=p.read_text(encoding='utf-8')
    # Poker presence: reserve "一時離席" for keeping the seat and "テーブルから退席" for releasing it.
    replacements=[
      ('次ハンドから離席','次ハンドから一時離席'),
      ('離席予約を取消','一時離席予約を取消'),
      ('離席予約を取り消しました','一時離席予約を取り消しました'),
      ('離席を設定しました','一時離席を設定しました'),
      ('離席する','一時離席する'),
      ('離席中','一時離席中'),
      ('席を離れる','テーブルから退席'),
      ('席を離れました','テーブルから退席しました'),
      ('途中着席はSIT OUTで入り','途中着席は一時離席状態で入り'),
      ('SIT OUT NEXT','次ハンドから一時離席'),
      ('SIT OUT','一時離席'),
      ('離席 ${Number(t.sitouts||0)}','一時離席 ${Number(t.sitouts||0)}'),
      ('Rebuyまたは退出','リバイ（150bb）またはテーブルから退席'),
      ('Rebuy 150bb','リバイ（150bb）'),
      ('150bbでRebuyしました','150bbでリバイしました'),
      ('150bbでRebuy','150bbでリバイ'),
      ('テーブルを見る','テーブルを開く'),
      ('参加 ${Number(t.players||0)}/6','プレイ中 ${Number(t.players||0)}/6'),
      ('着席 ${Number(t.seated||0)}/6','着席中 ${Number(t.seated||0)}/6'),
      ('参加 ${active}/6','プレイ中 ${active}/6'),
      ('着席 ${seated}/6','着席中 ${seated}/6'),
    ]
    for old,new in replacements:s=s.replace(old,new)

    # READY is a first-deal consent action; label the action rather than exposing the state-machine term.
    for old,new in [
      ('✓ READY · 取消','✓ 準備OK · 取消'),
      ('✓ READY','✓ 準備OK'),
      ('READYを取り消しました','開始準備を取り消しました'),
      ('参加準備を送りました','開始準備を完了しました'),
      ('READYで開始します','全員が準備OKになると開始します'),
      ('全員のREADYで開始','全員が準備OKで開始'),
      ('TABLE READY','開始準備'),
      ('Waiting / Ready','開始待ち'),
      ('>READY</button>','>準備OK</button>'),
      ('`READY ${','`準備 ${'),
      ("?'READY'","?'準備OK'"),
      ('AUTO PLAY','自動進行'),
      ('NEXT HAND','次ハンド'),
    ]:s=s.replace(old,new)

    # Account suspension is reversible; make that explicit wherever the legacy member manager is still reachable.
    s=s.replace("${m.disabled?'利用再開':'利用停止'}","${m.disabled?'利用再開':'一時停止'}")

    # "Cash" in study copy means poker cash games, not money movement.
    s=s.replace('CashとMTTを1本ずつ。','キャッシュゲームとMTTを1本ずつ。')
    s=s.replace('学習テーマをCash / MTTで分離しています。','学習テーマをキャッシュゲーム / MTTで分離しています。')
    p.write_text(s,encoding='utf-8')


def _index(p: Path) -> None:
    s=p.read_text(encoding='utf-8')
    s=s.replace('?v=34','?v=35')
    s=s.replace('登録アカウント、ポイント振込・回収、制度設定、監査ログは','登録アカウント、ポイント付与・回収、制度設定、監査ログは')
    s=s.replace('承認操作は不要です。必要な場合だけ利用停止、PINリセット、ランキング名の紐付けを行えます。','登録後の承認操作は不要です。必要な場合だけアカウントの一時停止、PINリセット、ランキング名の紐付けを行えます。')
    p.write_text(s,encoding='utf-8')


def _sw(p: Path) -> None:
    s=p.read_text(encoding='utf-8')
    s=re.sub(r'jj-arena-live-v\d+','jj-arena-live-v35',s)
    p.write_text(s,encoding='utf-8')
