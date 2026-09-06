"""Atomic production entrypoint for JJ Arena Live v1.10.

The verified v1.4 release bundle remains the immutable base. v1.5 upgrades
authentication, v1.6 upgrades official point entry to chip counts, v1.7
separates Fall 2026/27 rankings from archived Summer totals, v1.8 delivers
the public-launch UI/performance polish, v1.9 adds the weekly Cash/MTT study
spotlight, and v1.10 redesigns smartphone operations and removes duplicate
non-admin ケンイチロウ accounts without changing club rules.
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

import v15_patch
import v16_patch
import v17_patch
import v18_patch
import v19_patch
import v20_patch

ROOT = Path(__file__).resolve().parent
RELEASE_DIR = ROOT / "release_v14"
EXPECTED_SHA256 = "3ccb973f9ab146ce1c0d7da598242b0c1521a8ecc85c091caa10c1f1ebc9ddfd"
DEST = Path("/tmp/jj_arena_v20_runtime")

parts = sorted(RELEASE_DIR.glob("part*.b64"))
if len(parts) != 62:
    raise RuntimeError(f"JJ Arena release bundle incomplete: expected 62 parts, found {len(parts)}")

encoded = "".join(part.read_text(encoding="utf-8").strip() for part in parts)
raw = base64.b64decode(encoded, validate=True)
actual_sha256 = hashlib.sha256(raw).hexdigest()
if actual_sha256 != EXPECTED_SHA256:
    raise RuntimeError(f"JJ Arena release bundle checksum mismatch: {actual_sha256}")

shutil.rmtree(DEST, ignore_errors=True)
DEST.mkdir(parents=True, exist_ok=True)
dest_root = DEST.resolve()
with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
    for member in archive.getmembers():
        target = (DEST / member.name).resolve()
        if target != dest_root and dest_root not in target.parents:
            raise RuntimeError("Unsafe path detected in JJ Arena release bundle")
    archive.extractall(DEST)

v15_patch.apply(DEST)
v16_patch.apply(DEST)
v17_patch.apply(DEST)
v18_patch.apply(DEST, ROOT / "v18_assets")
v19_patch.apply(DEST)
v20_patch.apply(DEST)

# The legacy Render shell command still exports/logs JJ_ADMIN_PASSWORD. v1.10 does
# not use that credential, but overwrite it anyway so the logged value can never
authenticate to the application. Old email/password recovery is also disabled.
os.environ["JJ_ADMIN_PASSWORD"] = secrets.token_urlsafe(32)
os.environ.pop("JJ_ADMIN_LOGIN_PASSWORD", None)
os.environ.pop("JJ_ADMIN_LOGIN_EMAIL", None)

sys.path.insert(0, str(DEST))
from server import app  # noqa: E402,F401
