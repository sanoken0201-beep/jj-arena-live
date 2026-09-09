from __future__ import annotations

import py_compile
import tempfile
from pathlib import Path

from runtime_builder import RUNTIME_VERSION, build_runtime

ROOT = Path(__file__).resolve().parent
WORK = Path(tempfile.mkdtemp(prefix="jj-current-smoke-"))
DEST = build_runtime(WORK / "runtime")

server = (DEST / "server.py").read_text(encoding="utf-8")
db = (DEST / "db.py").read_text(encoding="utf-8")
appjs = (DEST / "static" / "app.js").read_text(encoding="utf-8")
css = (DEST / "static" / "styles.css").read_text(encoding="utf-8")
index = (DEST / "static" / "index.html").read_text(encoding="utf-8")
sw = (DEST / "static" / "sw.js").read_text(encoding="utf-8")

assert RUNTIME_VERSION == "1.19.1"
assert 'version="1.19.1"' in server or '"version":"1.19.1"' in server

# Quiz/ledger regression coverage from v1.18.6.
assert 'JJ_QUIZ_REWARD = 10' in server
assert 'CREATE TABLE IF NOT EXISTS quiz_attempts' in server
assert '@app.get("/api/quiz/question")' in server
assert '@app.post("/api/quiz/answer")' in server
assert '"quiz_reward"' in server
assert 'INSERT INTO point_ledger' in server
assert 'WHERE id=? AND user_id=? AND answer IS NULL' in server

# Mobile poker reliability regression coverage.
assert 'jjV186PreflopBaseBb' in appjs
assert 'base*multiplier' in appjs
assert 'jjV186ActionPending' in appjs
assert 'jjActionClock' in appjs
assert 'v1.18.6 poker interaction reliability' in css

# Tournament point-entry stacks must be consistent across desktop UI, quick UI,
# and server-side validation. Default remains 400 for backwards familiarity.
for value in (300, 400, 500, 600, 800, 1000):
    assert f"value:{value},label:'{value} / tournament'" in appjs
    assert f"value:{value},label:'{value} · Tournament'" in appjs
    assert f'{value}: "{value} / tournament"' in server
assert "else sel.value=String(game==='ring'?450:400)" in appjs

# Asset cache version is bumped whenever app.js changes.
assert '?v=40' in index
assert 'jj-arena-live-v40' in sw
assert 'request.url.query == "v=40"' in server

# Regression that caused the 2026-09 administrator lockout recovery failure.
assert '# v1.19.0 deterministic administrator recovery' in db
assert 'password_hash=? WHERE id=?' in db
assert 'DELETE FROM sessions WHERE user_id=?' in db
assert 'hash_password(pin)' in db

app_source = (ROOT / "app.py").read_text(encoding="utf-8")
assert 'from runtime_builder import build_runtime' in app_source
assert 'DEST = build_runtime()' in app_source
assert 'admin_ledger_stabilization.install(app, admin_console)' in app_source

ledger_patch = (ROOT / "admin_ledger_stabilization.py").read_text(encoding="utf-8")
assert "l.kind='quiz_reward'" in ledger_patch
assert "l.kind IN ('credit','collection','reversal')" in ledger_patch
assert '管理者による振込・回収だけを取消できます' in ledger_patch
assert 'row.update(categories)' in ledger_patch

for filename in [
    "runtime_builder.py",
    "v40_patch.py",
    "v39_patch.py",
    "v38_patch.py",
    "admin_ledger_stabilization.py",
    "app.py",
]:
    py_compile.compile(str(ROOT / filename), doraise=True)

print("JJ_ARENA_CURRENT_SMOKE_OK")
