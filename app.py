"""Atomic production entrypoint for JJ Arena Live v1.4.1.

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
server_text = server_text.replace('version="1.4.0"', 'version="1.4.1"')
server_text = server_text.replace('"version":"1.4.0"', '"version":"1.4.1"')
plain_init = "app = FastAPI(title=\"JJ Arena Live\", version=\"1.4.1\", lifespan=lifespan, docs_url=None if os.getenv(\"RENDER\") else \"/docs\", redoc_url=None if os.getenv(\"RENDER\") else \"/redoc\", openapi_url=None if os.getenv(\"RENDER\") else \"/openapi.json\")\ndb.init_db()\n"
safe_init = "app = FastAPI(title=\"JJ Arena Live\", version=\"1.4.1\", lifespan=lifespan, docs_url=None if os.getenv(\"RENDER\") else \"/docs\", redoc_url=None if os.getenv(\"RENDER\") else \"/redoc\", openapi_url=None if os.getenv(\"RENDER\") else \"/openapi.json\")\ntry:\n    db.init_db()\nexcept Exception:\n    raise RuntimeError(\"database initialization failed\") from None\n"
if plain_init in server_text:
    server_text = server_text.replace(plain_init, safe_init)
server_file.write_text(server_text, encoding="utf-8")

# The original Render service has a legacy shell start command that prints a
# generated JJ_ADMIN_PASSWORD. Replace it in-process before application import,
# so the value visible in Render logs is never the credential used by the app.
os.environ["JJ_ADMIN_PASSWORD"] = secrets.token_urlsafe(32)

sys.path.insert(0, str(DEST))
from server import app  # noqa: E402,F401
