from __future__ import annotations

import base64
import hashlib
import io
import py_compile
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = Path(tempfile.mkdtemp(prefix='jj-mobile-ux-smoke-'))
DEST = WORK / 'runtime'
DEST.mkdir(parents=True)

parts = sorted((ROOT / 'release_v14').glob('part*.b64'))
assert len(parts) == 62
raw = base64.b64decode(''.join(p.read_text(encoding='utf-8').strip() for p in parts), validate=True)
assert hashlib.sha256(raw).hexdigest() == '3ccb973f9ab146ce1c0d7da598242b0c1521a8ecc85c091caa10c1f1ebc9ddfd'
with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as ar:
    ar.extractall(DEST)

import v15_patch, v16_patch, v17_patch, v18_patch, v19_patch, v20_patch, v21_patch, v22_patch, v23_patch, v24_patch, v25_patch, v26_patch, v27_patch, v28_patch, v29_patch, v30_patch, v31_patch, v32_patch, v33_patch, v34_patch, v35_patch, v36_patch, v37_patch

for fn in [v15_patch.apply, v16_patch.apply, v17_patch.apply]:
    fn(DEST)
v18_patch.apply(DEST, ROOT / 'v18_assets')
for mod in [v19_patch, v20_patch, v21_patch, v22_patch, v23_patch, v24_patch, v25_patch, v26_patch, v27_patch, v28_patch, v29_patch, v30_patch, v31_patch, v32_patch, v33_patch, v34_patch, v35_patch, v36_patch, v37_patch]:
    mod.apply(DEST)

server = (DEST / 'server.py').read_text(encoding='utf-8')
appjs = (DEST / 'static' / 'app.js').read_text(encoding='utf-8')
css = (DEST / 'static' / 'styles.css').read_text(encoding='utf-8')
index = (DEST / 'static' / 'index.html').read_text(encoding='utf-8')
sw = (DEST / 'static' / 'sw.js').read_text(encoding='utf-8')

assert 'version="1.18.5"' in server or '"version":"1.18.5"' in server
assert '?v=37' in index
assert 'jj-arena-live-v37' in sw
assert 'v1.18.4 portrait-first table geometry' in appjs
assert 'v1.18.5 mobile poker action ergonomics' in appjs
assert "if(!l.can_check)actions.push" in appjs
assert 'data-allin-size' in appjs
assert 'コール額' in appjs
assert 'id="jjRaiseAction"' in appjs
assert 'jj-actions-${actions.length}' in appjs
assert 'v1.18.5 mobile poker usability polish' in css
assert 'grid-template-columns:repeat(5,minmax(0,1fr))' in css
assert 'min-height:56px!important' in css
assert '@media (prefers-reduced-motion:reduce)' in css
assert 'min-height:44px!important' in css

py_compile.compile(str(ROOT / 'v37_patch.py'), doraise=True)
py_compile.compile(str(ROOT / 'app.py'), doraise=True)
print('MOBILE_POKER_UX_SMOKE_OK')
