from __future__ import annotations

import base64
import hashlib
import io
import shutil
import tarfile
from pathlib import Path

import v15_patch
import v16_patch
import v17_patch
import v18_patch
import v19_patch
import v20_patch
import v21_patch
import v22_patch
import v23_patch
import v24_patch
import v25_patch
import v26_patch
import v27_patch
import v28_patch
import v29_patch
import v30_patch
import v31_patch
import v32_patch
import v33_patch
import v34_patch
import v35_patch
import v36_patch
import v37_patch
import v38_patch
import v39_patch
import v40_patch
import v41_patch
import v42_patch
import v43_patch
import v44_patch
import v45_patch
import v46_patch
import v47_patch

ROOT = Path(__file__).resolve().parent
RELEASE_DIR = ROOT / "release_v14"
EXPECTED_PARTS = 62
EXPECTED_SHA256 = "3ccb973f9ab146ce1c0d7da598242b0c1521a8ecc85c091caa10c1f1ebc9ddfd"
RUNTIME_VERSION = "1.20.2"
DEFAULT_DEST = Path("/tmp/jj_arena_v47_runtime")


def _release_bytes() -> bytes:
    parts = sorted(RELEASE_DIR.glob("part*.b64"))
    if len(parts) != EXPECTED_PARTS:
        raise RuntimeError(
            f"JJ Arena release bundle incomplete: expected {EXPECTED_PARTS} parts, found {len(parts)}"
        )
    encoded = "".join(part.read_text(encoding="utf-8").strip() for part in parts)
    raw = base64.b64decode(encoded, validate=True)
    actual = hashlib.sha256(raw).hexdigest()
    if actual != EXPECTED_SHA256:
        raise RuntimeError(f"JJ Arena release bundle checksum mismatch: {actual}")
    return raw


def _safe_extract(raw: bytes, dest: Path) -> None:
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        for member in archive.getmembers():
            target = (dest / member.name).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError("Unsafe path detected in JJ Arena release bundle")
        archive.extractall(dest)


def _apply_patches(dest: Path) -> None:
    v15_patch.apply(dest)
    v16_patch.apply(dest)
    v17_patch.apply(dest)
    v18_patch.apply(dest, ROOT / "v18_assets")
    for module in (
        v19_patch,
        v20_patch,
        v21_patch,
        v22_patch,
        v23_patch,
        v24_patch,
        v25_patch,
        v26_patch,
        v27_patch,
        v28_patch,
        v29_patch,
        v30_patch,
        v31_patch,
        v32_patch,
        v33_patch,
        v34_patch,
        v35_patch,
        v36_patch,
        v37_patch,
        v38_patch,
        v39_patch,
        v40_patch,
        v41_patch,
        v42_patch,
        v43_patch,
        v44_patch,
        v45_patch,
        v46_patch,
        v47_patch,
    ):
        module.apply(dest)


def build_runtime(dest: Path | None = None) -> Path:
    """Reconstruct the exact production runtime and return its directory."""
    target = Path(dest) if dest is not None else DEFAULT_DEST
    _safe_extract(_release_bytes(), target)
    _apply_patches(target)
    return target
