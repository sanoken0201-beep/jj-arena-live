from __future__ import annotations
import base64,hashlib,io,shutil,tarfile,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
WORK=Path(tempfile.mkdtemp(prefix='jj-ui-copy-'))
DEST=WORK/'runtime';DEST.mkdir(parents=True)
raw=base64.b64decode(''.join(p.read_text(encoding='utf-8').strip() for p in sorted((ROOT/'release_v14').glob('part*.b64'))),validate=True)
assert hashlib.sha256(raw).hexdigest()=='3ccb973f9ab146ce1c0d7da598242b0c1521a8ecc85c091caa10c1f1ebc9ddfd'
with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as ar:ar.extractall(DEST)
import v15_patch,v16_patch,v17_patch,v18_patch,v19_patch,v20_patch,v21_patch,v22_patch,v23_patch,v24_patch,v25_patch,v26_patch,v27_patch,v28_patch,v29_patch,v30_patch,v31_patch,v32_patch,v33_patch,v34_patch,v35_patch,admin_copy_patch
for m in [v15_patch,v16_patch,v17_patch]:m.apply(DEST)
v18_patch.apply(DEST,ROOT/'v18_assets')
for m in [v19_patch,v20_patch,v21_patch,v22_patch,v23_patch,v24_patch,v25_patch,v26_patch,v27_patch,v28_patch,v29_patch,v30_patch,v31_patch,v32_patch,v33_patch,v34_patch,v35_patch]:m.apply(DEST)
admin=WORK/'admin_static';shutil.copytree(ROOT/'admin_static',admin);admin_copy_patch.apply(admin)
appjs=(DEST/'static/app.js').read_text(encoding='utf-8');index=(DEST/'static/index.html').read_text(encoding='utf-8');server=(DEST/'server.py').read_text(encoding='utf-8')
adminjs=(admin/'admin.js').read_text(encoding='utf-8');adminindex=(admin/'index.html').read_text(encoding='utf-8')
for s in ['次ハンドから一時離席','一時離席する','テーブルから退席','準備OK','テーブルを開く','キャッシュゲームとMTT']:
    assert s in appjs,s
for s in ['席を離れる','次ハンドから離席','途中着席はSIT OUTで入り','READYで開始します','CashとMTTを1本ずつ。']:
    assert s not in appjs,s
assert 'プレイ中 ${Number(t.players||0)}/6' in appjs
assert '登録後の承認操作は不要です。必要な場合だけアカウントの一時停止' in index
assert '?v=35' in index and 'version="1.18.3"' in server
for s in ['JJメンバー確認済み','ポイント付与・回収','一時停止を含む']:
    assert s in adminindex,s
for s in ['本人確認済み','ポイント振込・回収','利用停止を含む']:
    assert s not in adminindex,s
for s in ['JJメンバー確認が未完了','一時停止中',"x.kind==='credit'?'付与'","const verb=state.direction==='credit'?'付与':'回収'"]:
    assert s in adminjs,s
for s in ['本人確認が未完了',"${u.disabled?'利用停止':'ACTIVE'}","const verb=state.direction==='credit'?'振込':'回収'"]:
    assert s not in adminjs,s
assert '/admin-static/admin.js?v=183' in adminindex
print('UI_COPY_SMOKE_OK',flush=True)
shutil.rmtree(WORK,ignore_errors=True)
