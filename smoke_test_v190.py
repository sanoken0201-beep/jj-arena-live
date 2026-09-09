from __future__ import annotations

import py_compile
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path

import online_results_cleanup
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

# The requested ranking cleanup is a DB migration, not a permanent startup
# delete. Existing online results are removed once, while future results survive
# subsequent restarts.
class _CleanupTestDB:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    @staticmethod
    def utcnow() -> str:
        return "2026-09-10T00:00:00+00:00"


cleanup_db = _CleanupTestDB(WORK / "cleanup.sqlite")
with cleanup_db.connect() as con:
    con.execute("CREATE TABLE online_hand_results(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL)")
    con.executemany(
        "INSERT INTO online_hand_results(id,user_id) VALUES (?,?)",
        [(1, 101), (2, 101), (3, 202)],
    )
first_cleanup = online_results_cleanup.apply(cleanup_db)
assert first_cleanup == {"applied": True, "rows": 3, "users": 2}
with cleanup_db.connect() as con:
    assert con.execute("SELECT COUNT(*) AS c FROM online_hand_results").fetchone()["c"] == 0
    con.execute("INSERT INTO online_hand_results(id,user_id) VALUES (?,?)", (4, 303))
second_cleanup = online_results_cleanup.apply(cleanup_db)
assert second_cleanup == {"applied": False, "rows": 0, "users": 0}
with cleanup_db.connect() as con:
    assert con.execute("SELECT COUNT(*) AS c FROM online_hand_results").fetchone()["c"] == 1

app_source = (ROOT / "app.py").read_text(encoding="utf-8")
assert 'from runtime_builder import build_runtime' in app_source
assert 'DEST = build_runtime()' in app_source
assert 'online_results_cleanup.apply(db)' in app_source
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
    "online_results_cleanup.py",
    "admin_delete.py",
    "smoke_test_user_management.py",
    "app.py",
]:
    py_compile.compile(str(ROOT / filename), doraise=True)

# Exercise the real reconstructed PIN-auth and account-deletion routes against a
# temporary SQLite database. This verifies deletion visibility and same-name
# re-registration behavior rather than relying only on source-string checks.
import smoke_test_user_management

smoke_test_user_management.run()

print("JJ_ARENA_CURRENT_SMOKE_OK")
