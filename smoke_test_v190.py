from __future__ import annotations

import py_compile
import tempfile
from pathlib import Path

from runtime_builder import RUNTIME_VERSION, build_runtime

ROOT = Path(__file__).resolve().parent
WORK = Path(tempfile.mkdtemp(prefix="jj-v190-smoke-"))
DEST = build_runtime(WORK / "runtime")

server = (DEST / "server.py").read_text(encoding="utf-8")
db = (DEST / "db.py").read_text(encoding="utf-8")
appjs = (DEST / "static" / "app.js").read_text(encoding="utf-8")
css = (DEST / "static" / "styles.css").read_text(encoding="utf-8")
index = (DEST / "static" / "index.html").read_text(encoding="utf-8")
sw = (DEST / "static" / "sw.js").read_text(encoding="utf-8")

assert RUNTIME_VERSION == "1.19.0"
assert 'version="1.19.0"' in server or '"version":"1.19.0"' in server

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
assert '?v=38' in index
assert 'jj-arena-live-v38' in sw

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

# Temporary feature-branch diagnostics: print source context around the current
# tournament stack values so the next patch can target the real production
# runtime without guessing.
for label, text in (("INDEX", index), ("APPJS", appjs), ("SERVER", server)):
    seen = set()
    for needle in ("1000", "400"):
        start = 0
        while True:
            pos = text.find(needle, start)
            if pos < 0:
                break
            snippet = text[max(0, pos - 220): min(len(text), pos + 260)].replace("\n", "\\n")
            if snippet not in seen:
                print(f"STACK_DIAG {label} {needle}: {snippet}")
                seen.add(snippet)
            start = pos + len(needle)

for filename in [
    "runtime_builder.py",
    "v39_patch.py",
    "v38_patch.py",
    "admin_ledger_stabilization.py",
    "app.py",
]:
    py_compile.compile(str(ROOT / filename), doraise=True)

print("JJ_ARENA_V190_STABILIZATION_OK")
