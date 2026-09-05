"""Atomic production entrypoint for JJ Arena Live v1.4.2.

The verified v1.4 release bundle is checksum-validated first. Narrow runtime
compatibility patches are then applied for legacy Render Postgres data and a
PostgreSQL-specific numeric expression used by the beta-to-v1.4 migration.
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
import secrets
import shutil
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEASE_DIR = ROOT / "release_v14"
EXPECTED_SHA256 = "3ccb973f9ab146ce1c0d7da598242b0c1521a8ecc85c091caa10c1f1ebc9ddfd"
DEST = Path("/tmp/jj_arena_v14")

parts = sorted(RELEASE_DIR.glob("part*.b64"))
if len(parts) != 62:
    raise RuntimeError(f"JJ Arena release bundle incomplete: expected 62 parts, found {len(parts)}")

encoded = "".join(part.read_text(encoding="utf-8").strip() for part in parts)
raw = base64.b64decode(encoded, validate=True)
actual_sha256 = hashlib.sha256(raw).hexdigest()
if actual_sha256 != EXPECTED_SHA256:
    raise RuntimeError(f"JJ Arena release bundle checksum mismatch: {actual_sha256}")

marker = DEST / ".sha256"
if not marker.exists() or marker.read_text(encoding="utf-8").strip() != EXPECTED_SHA256:
    shutil.rmtree(DEST, ignore_errors=True)
    DEST.mkdir(parents=True, exist_ok=True)
    dest_root = DEST.resolve()
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for member in archive.getmembers():
            target = (DEST / member.name).resolve()
            if target != dest_root and dest_root not in target.parents:
                raise RuntimeError("Unsafe path detected in JJ Arena release bundle")
        archive.extractall(DEST)
    marker.write_text(EXPECTED_SHA256, encoding="utf-8")

# Compatibility hotfixes for the beta -> v1.4 Postgres migration.
db_file = DEST / "db.py"
db_text = db_file.read_text(encoding="utf-8")
legacy = '        if "chips" in cols: con.execute("UPDATE users SET arena_chips=chips WHERE arena_chips=0")\n'
fixed = '''        # Some partially-migrated beta rows have arena_chips=NULL. Normalize\n        # them before later code depends on NOT NULL semantics.\n        if "chips" in cols:\n            con.execute("UPDATE users SET arena_chips=COALESCE(NULLIF(arena_chips,0),chips,0) WHERE arena_chips IS NULL OR arena_chips=0")\n        else:\n            con.execute("UPDATE users SET arena_chips=0 WHERE arena_chips IS NULL")\n        if "xp" in cols:\n            con.execute("UPDATE users SET xp=0 WHERE xp IS NULL")\n        if "role" in cols:\n            con.execute("UPDATE users SET role='member' WHERE role IS NULL OR role='' ")\n        con.execute("ALTER TABLE users ALTER COLUMN arena_chips SET DEFAULT 0")\n        con.execute("ALTER TABLE users ALTER COLUMN arena_chips SET NOT NULL")\n        if "xp" in cols:\n            con.execute("ALTER TABLE users ALTER COLUMN xp SET DEFAULT 0")\n            con.execute("ALTER TABLE users ALTER COLUMN xp SET NOT NULL")\n'''
if legacy in db_text:
    db_text = db_text.replace(legacy, fixed)
elif "arena_chips=COALESCE(NULLIF(arena_chips,0),chips,0)" not in db_text:
    raise RuntimeError("JJ Arena migration hotfix target was not found")

db_text = db_text.replace("ONLINE_POINTS_PER_BB = 3.0", "ONLINE_POINTS_PER_BB = 3")
db_text = db_text.replace(
    'con.execute("UPDATE online_hand_results SET points=ROUND(result_bb * ?, 2)", (ONLINE_POINTS_PER_BB,))',
    'con.execute("UPDATE online_hand_results SET points=result_bb * ?", (ONLINE_POINTS_PER_BB,))',
)
db_file.write_text(db_text, encoding="utf-8")

server_file = DEST / "server.py"
server_text = server_file.read_text(encoding="utf-8")
server_text = server_text.replace('version="1.4.0"', 'version="1.4.2"')
server_text = server_text.replace('"version":"1.4.0"', '"version":"1.4.2"')
plain_init = "app = FastAPI(title=\"JJ Arena Live\", version=\"1.4.2\", lifespan=lifespan, docs_url=None if os.getenv(\"RENDER\") else \"/docs\", redoc_url=None if os.getenv(\"RENDER\") else \"/redoc\", openapi_url=None if os.getenv(\"RENDER\") else \"/openapi.json\")\ndb.init_db()\n"
safe_init = "app = FastAPI(title=\"JJ Arena Live\", version=\"1.4.2\", lifespan=lifespan, docs_url=None if os.getenv(\"RENDER\") else \"/docs\", redoc_url=None if os.getenv(\"RENDER\") else \"/redoc\", openapi_url=None if os.getenv(\"RENDER\") else \"/openapi.json\")\ntry:\n    db.init_db()\nexcept Exception:\n    raise RuntimeError(\"database initialization failed\") from None\n"
if plain_init in server_text:
    server_text = server_text.replace(plain_init, safe_init)
server_file.write_text(server_text, encoding="utf-8")

# The original Render service has a legacy shell start command that prints a
# generated JJ_ADMIN_PASSWORD. Replace it in-process before application import,
# so the value visible in Render logs is never the credential used by the app.
os.environ["JJ_ADMIN_PASSWORD"] = secrets.token_urlsafe(32)

sys.path.insert(0, str(DEST))

# One-time, secret-backed admin recovery. The recovery password lives only in
# Render Environment, never in GitHub or logs. A marker stored in Postgres makes
# the reset idempotent, so changing the password in the app later is not undone
# by ordinary restarts/deploys using the same recovery value.
import db as _db  # noqa: E402
_db.init_db()
_recovery_password = os.environ.get("JJ_ADMIN_LOGIN_PASSWORD", "")
_recovery_email = os.environ.get("JJ_ADMIN_LOGIN_EMAIL", "admin@jj.local").strip().lower()
if _recovery_password:
    _reset_marker = hashlib.sha256(
        ("jj-admin-recovery-v1|" + _recovery_email + "|" + _recovery_password).encode()
    ).hexdigest()
    with _db.connect() as con:
        con.execute("CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        seen = con.execute("SELECT value FROM app_meta WHERE key=?", ("admin_recovery_marker",)).fetchone()
        if not seen or seen["value"] != _reset_marker:
            row = con.execute("SELECT id,name FROM users WHERE lower(email)=?", (_recovery_email,)).fetchone()
            if row:
                admin_id = row["id"]
                admin_name = row["name"] or os.environ.get("JJ_ADMIN_NAME", "ケンイチロウ")
                con.execute(
                    "UPDATE users SET password_hash=?,role='admin',approved=1,disabled=0,ranking_name=COALESCE(NULLIF(ranking_name,''),?) WHERE id=?",
                    (_db.hash_password(_recovery_password), admin_name, admin_id),
                )
            else:
                admin_name = os.environ.get("JJ_ADMIN_NAME", "ケンイチロウ")
                admin_id = _db.insert_returning_id(
                    con,
                    "INSERT INTO users(name,email,password_hash,role,arena_chips,xp,approved,disabled,ranking_name,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (admin_name,_recovery_email,_db.hash_password(_recovery_password),"admin",0,0,1,0,admin_name,_db.utcnow()),
                )
            con.execute("DELETE FROM sessions WHERE user_id=?", (admin_id,))
            con.execute("DELETE FROM app_meta WHERE key=?", ("admin_recovery_marker",))
            con.execute("INSERT INTO app_meta(key,value) VALUES (?,?)", ("admin_recovery_marker", _reset_marker))
    os.environ.pop("JJ_ADMIN_LOGIN_PASSWORD", None)

from server import app  # noqa: E402,F401
