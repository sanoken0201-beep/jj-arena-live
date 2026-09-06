from __future__ import annotations
import base64, hashlib, io, re, tarfile, tempfile, shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parent
WORK=Path(tempfile.mkdtemp(prefix='jj-ui-audit-'))
DEST=WORK/'runtime'; DEST.mkdir(parents=True)
parts=sorted((ROOT/'release_v14').glob('part*.b64'))
raw=base64.b64decode(''.join(p.read_text(encoding='utf-8').strip() for p in parts),validate=True)
assert hashlib.sha256(raw).hexdigest()=='3ccb973f9ab146ce1c0d7da598242b0c1521a8ecc85c091caa10c1f1ebc9ddfd'
with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as ar: ar.extractall(DEST)
import v15_patch,v16_patch,v17_patch,v18_patch,v19_patch,v20_patch,v21_patch,v22_patch,v23_patch,v24_patch,v25_patch,v26_patch,v27_patch,v28_patch,v29_patch,v30_patch,v31_patch,v32_patch,v33_patch,v34_patch,v35_patch,admin_copy_patch
for fn in [v15_patch.apply,v16_patch.apply,v17_patch.apply]: fn(DEST)
v18_patch.apply(DEST,ROOT/'v18_assets')
for mod in [v19_patch,v20_patch,v21_patch,v22_patch,v23_patch,v24_patch,v25_patch,v26_patch,v27_patch,v28_patch,v29_patch,v30_patch,v31_patch,v32_patch,v33_patch,v34_patch,v35_patch]: mod.apply(DEST)
admin=WORK/'admin_static';shutil.copytree(ROOT/'admin_static',admin);admin_copy_patch.apply(admin)
files=[DEST/'static/index.html',DEST/'static/app.js',admin/'index.html',admin/'admin.js',admin/'admin_delete.js']
seen=set(); out=[]
pat_q=re.compile(r"(['\"`])((?:\\.|(?!\1).){1,180})\1",re.S)
pat_html=re.compile(r'>([^<>]{1,120})<')
for p in files:
    text=p.read_text(encoding='utf-8');vals=[]
    vals += [m.group(2) for m in pat_q.finditer(text)]
    vals += [m.group(1) for m in pat_html.finditer(text)]
    for v in vals:
        v=re.sub(r'\\[nrt]',' ',v);v=re.sub(r'\s+',' ',v).strip()
        if not v or len(v)>160: continue
        if not (re.search(r'[ぁ-んァ-ン一-龯]',v) or re.search(r'\b(READY|Lobby|Rebuy|SIT OUT|ACTIVE|DELETE|CANCEL|SAVE|OPEN TABLE|HAND IN PROGRESS)\b',v,re.I)): continue
        key=(p.name,v)
        if key in seen: continue
        seen.add(key);out.append((p.name,v))
for name,v in out:print(f'{name}\t{v}',flush=True)
print(f'UI_LABEL_AUDIT_OK count={len(out)}',flush=True)
