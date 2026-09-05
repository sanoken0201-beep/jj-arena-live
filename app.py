"""Atomic production entrypoint for JJ Arena Live v1.4.

The verified release bundle is stored as small base64 chunks so Render always
checks out a complete application revision instead of a partially-updated tree.
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
    raise RuntimeError(
        f"JJ Arena release bundle checksum mismatch: {actual_sha256}"
    )

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

sys.path.insert(0, str(DEST))
from server import app  # noqa: E402,F401
