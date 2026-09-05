"""Atomic production entrypoint for JJ Arena Live v1.4.1.

The verified v1.4 release bundle is checksum-validated first. A narrowly-scoped
runtime compatibility patch is then applied for legacy Render Postgres rows that
may contain NULL values from the beta schema. This keeps the verified release
intact while making the migration safe and preventing row-level database details
(such as email addresses) from being emitted on startup failures.
"""
from __future__ import annotations

import base64
import hashlib
import io
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

# Compatibility hotfix for the beta -> v1.4 Postgres migration.
db_file = DEST / "db.py"
db_text = db_file.read_text(encoding="utf-8")
legacy = '        if "chips" in cols: con.execute("UPDATE users SET arena_chips=chips WHERE arena_chips=0")\n'
fixed = '''        # Some partially-migrated beta rows have arena_chips=NULL. Normalize\n        # them before later code depends on NOT NULL semantics.\n        if "chips" in cols:\n            con.execute("UPDATE users SET arena_chips=COALESCE(NULLIF(arena_chips,0),chips,0) WHERE arena_chips IS NULL OR arena_chips=0")\n        else:\n            con.execute("UPDATE users SET arena_chips=0 WHERE arena_chips IS NULL")\n        if "xp" in cols:\n            con.execute("UPDATE users SET xp=0 WHERE xp IS NULL")\n        if "role" in cols:\n            con.execute("UPDATE users SET role='member' WHERE role IS NULL OR role='' ")\n        con.execute("ALTER TABLE users ALTER COLUMN arena_chips SET DEFAULT 0")\n        con.execute("ALTER TABLE users ALTER COLUMN arena_chips SET NOT NULL")\n        if "xp" in cols:\n            con.execute("ALTER TABLE users ALTER COLUMN xp SET DEFAULT 0")\n            con.execute("ALTER TABLE users ALTER COLUMN xp SET NOT NULL")\n'''
if legacy in db_text:
    db_text = db_text.replace(legacy, fixed)
elif "arena_chips=COALESCE(NULLIF(arena_chips,0),chips,0)" not in db_text:
    raise RuntimeError("JJ Arena migration hotfix target was not found")
db_file.write_text(db_text, encoding="utf-8")

# Prevent database drivers from placing a full failing row (including email) in
# the Render startup traceback. The original exception is deliberately hidden.
server_file = DEST / "server.py"
server_text = server_file.read_text(encoding="utf-8")
server_text = server_text.replace('version="1.4.0"', 'version="1.4.1"')
server_text = server_text.replace('"version":"1.4.0"', '"version":"1.4.1"')
plain_init = "app = FastAPI(title=\"JJ Arena Live\", version=\"1.4.1\", lifespan=lifespan, docs_url=None if os.getenv(\"RENDER\") else \"/docs\", redoc_url=None if os.getenv(\"RENDER\") else \"/redoc\", openapi_url=None if os.getenv(\"RENDER\") else \"/openapi.json\")\ndb.init_db()\n"
safe_init = "app = FastAPI(title=\"JJ Arena Live\", version=\"1.4.1\", lifespan=lifespan, docs_url=None if os.getenv(\"RENDER\") else \"/docs\", redoc_url=None if os.getenv(\"RENDER\") else \"/redoc\", openapi_url=None if os.getenv(\"RENDER\") else \"/openapi.json\")\ntry:\n    db.init_db()\nexcept Exception:\n    raise RuntimeError(\"database initialization failed\") from None\n"
if plain_init in server_text:
    server_text = server_text.replace(plain_init, safe_init)
server_file.write_text(server_text, encoding="utf-8")

sys.path.insert(0, str(DEST))
from server import app  # noqa: E402,F401
