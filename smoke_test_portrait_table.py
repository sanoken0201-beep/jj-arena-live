from __future__ import annotations

import base64
import hashlib
import io
import py_compile
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = Path(tempfile.mkdtemp(prefix='jj-portrait-smoke-'))
DEST = WORK / 'runtime'
DEST.mkdir(parents=True)

parts = sorted((ROOT / 'release_v14').glob('part*.b64'))
assert len(parts) == 62
raw = base64.b64decode(''.join(p.read_text(encoding='utf-8').strip() for p in parts), validate=True)
assert hashlib.sha256(raw).hexdigest() == '3ccb973f9ab146ce1c0d7da598242b0c1521a8ecc85c091caa10c1f1ebc9ddfd'
with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as ar:
    ar.extractall(DEST)

import v15_patch, v16_patch, v17_patch, v18_patch, v19_patch, v20_patch, v21_patch, v22_patch, v23_patch, v24_patch, v25_patch, v26_patch, v27_patch, v28_patch, v29_patch, v30_patch, v31_patch, v32_patch, v33_patch, v34_patch, v35_patch, v36_patch

for fn in [v15_patch.apply, v16_patch.apply, v17_patch.apply]:
    fn(DEST)
v18_patch.apply(DEST, ROOT / 'v18_assets')
for mod in [v19_patch, v20_patch, v21_patch, v22_patch, v23_patch, v24_patch, v25_patch, v26_patch, v27_patch, v28_patch, v29_patch, v30_patch, v31_patch, v32_patch, v33_patch, v34_patch, v35_patch, v36_patch]:
    mod.apply(DEST)

server = (DEST / 'server.py').read_text(encoding='utf-8')
appjs = (DEST / 'static' / 'app.js').read_text(encoding='utf-8')
css = (DEST / 'static' / 'styles.css').read_text(encoding='utf-8')
index = (DEST / 'static' / 'index.html').read_text(encoding='utf-8')
sw = (DEST / 'static' / 'sw.js').read_text(encoding='utf-8')

assert 'version="1.18.4"' in server or '"version":"1.18.4"' in server
assert '?v=36' in index
assert 'jj-arena-live-v36' in sw
assert 'v1.18.4 portrait-first table geometry' in appjs
assert "(max-width:760px) and (orientation:portrait)" in appjs
assert '{left:50,top:82}' in appjs
assert '{left:50,top:15}' in appjs
assert 'v1.18.4 portrait poker table' in css
assert '@media (max-width:760px) and (orientation:portrait)' in css
assert 'border-radius:48% / 37%' in css
assert 'left:9%!important' in css and 'right:9%!important' in css
assert 'max-height:184px!important' in css
assert 'min-height:430px!important' in css

py_compile.compile(str(ROOT / 'v36_patch.py'), doraise=True)
py_compile.compile(str(ROOT / 'app.py'), doraise=True)
print('PORTRAIT_TABLE_SMOKE_OK')
