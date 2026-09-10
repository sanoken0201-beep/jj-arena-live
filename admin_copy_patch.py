from __future__ import annotations
import re
from pathlib import Path


ADMIN_ASSET_VERSION = "184"


def apply(static_dir: Path) -> None:
    _index(static_dir/'index.html')
    _js(static_dir/'admin.js')


def _index(p: Path) -> None:
    s=p.read_text(encoding='utf-8')
    replacements=[
      ('本人確認済み','JJメンバー確認済み'),
      ('登録アカウント、公式ポイントの振込・回収、制度設定、操作履歴を一元管理します。','登録アカウント、公式ポイントの付与・回収、制度設定、操作履歴を一元管理します。'),
      ('ポイント振込・回収','ポイント付与・回収'),
      ('ポイント振込','ポイント付与'),
      ('＋ 振込','＋ 付与'),
      ('管理者による1回の振込・回収上限','管理者による1回の付与・回収上限'),
      ('通常は利用停止で管理できます。','通常は一時停止で管理できます。'),
      ('利用停止を含む','一時停止を含む'),
    ]
    for old,new in replacements:s=s.replace(old,new)

    for asset in ('admin.css','admin.js','admin_delete.js'):
        s=re.sub(
            rf'/admin-static/{re.escape(asset)}(?:\?v=\d+)?',
            f'/admin-static/{asset}?v={ADMIN_ASSET_VERSION}',
            s,
        )

    pin_css=f'<link rel="stylesheet" href="/admin-static/admin_pin_verify.css?v={ADMIN_ASSET_VERSION}">'
    pin_js=f'<script src="/admin-static/admin_pin_verify.js?v={ADMIN_ASSET_VERSION}"></script>'
    if 'admin_pin_verify.css' not in s:
        if '</head>' not in s:raise RuntimeError('admin head marker missing')
        s=s.replace('</head>',pin_css+'\n</head>',1)
    else:
        s=re.sub(r'/admin-static/admin_pin_verify\.css(?:\?v=\d+)?',f'/admin-static/admin_pin_verify.css?v={ADMIN_ASSET_VERSION}',s)
    if 'admin_pin_verify.js' not in s:
        if '</body>' not in s:raise RuntimeError('admin body marker missing')
        s=s.replace('</body>',pin_js+'\n</body>',1)
    else:
        s=re.sub(r'/admin-static/admin_pin_verify\.js(?:\?v=\d+)?',f'/admin-static/admin_pin_verify.js?v={ADMIN_ASSET_VERSION}',s)
    p.write_text(s,encoding='utf-8')


def _js(p: Path) -> None:
    s=p.read_text(encoding='utf-8')
    replacements=[
      ("points:'ポイント振込・回収'","points:'ポイント付与・回収'"),
      ("'point.credit':'ポイント振込'","'point.credit':'ポイント付与'"),
      ('本人確認が未完了のアカウント','JJメンバー確認が未完了のアカウント'),
      ("u.club_verified?'チェック済'","u.club_verified?'JJ確認済'"),
      ("u.club_verified?'<span class=\"badge verify\">確認済</span>'","u.club_verified?'<span class=\"badge verify\">JJ確認済</span>'"),
      ("${u.disabled?'利用停止':'ACTIVE'}","${u.disabled?'一時停止中':'ACTIVE'}"),
      ("${u.disabled?'利用を再開':'利用を停止'}","${u.disabled?'利用を再開':'一時停止'}"),
      ('このアカウントを利用停止にします。既存セッションも失効します。','このアカウントを一時停止します。既存セッションも失効します。'),
      ("disabled?'利用停止にしました':'利用を再開しました'","disabled?'一時停止しました':'利用を再開しました'"),
      ("x.kind==='credit'?'振込'","x.kind==='credit'?'付与'"),
      ("state.direction==='credit'?'振込':'回収'","state.direction==='credit'?'付与':'回収'"),
      ("const verb=state.direction==='credit'?'振込':'回収'","const verb=state.direction==='credit'?'付与':'回収'"),
      ('管理者による1回の振込・回収上限','管理者による1回の付与・回収上限'),
    ]
    for old,new in replacements:s=s.replace(old,new)
    p.write_text(s,encoding='utf-8')
