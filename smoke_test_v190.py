from __future__ import annotations

import base64
import hashlib
import io
import py_compile
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = Path(tempfile.mkdtemp(prefix="jj-v190-smoke-"))
DEST = WORK / "runtime"
DEST.mkdir(parents=True)

parts = sorted((ROOT / "release_v14").glob("part*.b64"))
assert len(parts) == 62
raw = base64.b64decode("".join(p.read_text(encoding="utf-8").strip() for p in parts), validate=True)
assert hashlib.sha256(raw).hexdigest() == "3ccb973f9ab146ce1c0d7da598242b0c1521a8ecc85c091caa10c1f1ebc9ddfd"
with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as ar:
    for member in ar.getmembers():
        target = (DEST / member.name).resolve()
        dest_root = DEST.resolve()
        assert target == dest_root or dest_root in target.parents
    ar.extractall(DEST)

import v15_patch, v16_patch, v17_patch, v18_patch, v19_patch, v20_patch, v21_patch, v22_patch
import v23_patch, v24_patch, v25_patch, v26_patch, v27_patch, v28_patch, v29_patch, v30_patch
import v31_patch, v32_patch, v33_patch, v34_patch, v35_patch, v36_patch, v37_patch, v38_patch, v39_patch

for fn in [v15_patch.apply, v16_patch.apply, v17_patch.apply]:
    fn(DEST)
v18_patch.apply(DEST, ROOT / "v18_assets")
for mod in [
    v19_patch, v20_patch, v21_patch, v22_patch, v23_patch, v24_patch, v25_patch,
    v26_patch, v27_patch, v28_patch, v29_patch, v30_patch, v31_patch, v32_patch,
    v33_patch, v34_patch, v35_patch, v36_patch, v37_patch, v38_patch, v39_patch,
]:
    mod.apply(DEST)

server = (DEST / "server.py").read_text(encoding="utf-8")
db = (DEST / "db.py").read_text(encoding="utf-8")
appjs = (DEST / "static" / "app.js").read_text(encoding="utf-8")

assert 'version="1.19.0"' in server or '"version":"1.19.0"' in server
assert 'JJ_QUIZ_REWARD = 10' in server
assert '@app.get("/api/quiz/question")' in server
assert '@app.post("/api/quiz/answer")' in server
assert 'WHERE id=? AND user_id=? AND answer IS NULL' in server
assert 'jjV186ActionPending' in appjs
assert 'jjActionClock' in appjs

# Regression that caused the 2026-09 administrator lockout recovery failure.
assert '# v1.19.0 deterministic administrator recovery' in db
assert "password_hash=? WHERE id=?" in db
assert 'DELETE FROM sessions WHERE user_id=?' in db
assert 'hash_password(pin)' in db

app_source = (ROOT / "app.py").read_text(encoding="utf-8")
assert 'import v39_patch' in app_source
assert 'v39_patch.apply(DEST)' in app_source
assert '/tmp/jj_arena_v39_runtime' in app_source

for filename in ["v39_patch.py", "v38_patch.py", "app.py"]:
    py_compile.compile(str(ROOT / filename), doraise=True)

print("JJ_ARENA_V190_STABILIZATION_OK")
