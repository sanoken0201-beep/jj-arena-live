from __future__ import annotations

"""Build an isolated v1.24.4 compatibility runtime from the immutable snapshot.

Production has used ``materialized_v1244`` directly since the v2 cutover.  The
former compatibility builder still replayed the entire v15-v55 patch history,
which made old release fragments and patch modules runtime dependencies even
though their final output had already been materialized and checksum-recorded.

This module now copies only the files named by ``materialized_v1244.manifest.json``
into an isolated directory and verifies SHA-256/size before and after the copy.
That preserves the independent import path used by ``app_legacy`` and parity
checks without reconstructing history at runtime.
"""

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SOURCE_DIR = (ROOT / "materialized_v1244").resolve()
MANIFEST_PATH = ROOT / "materialized_v1244.manifest.json"
RUNTIME_VERSION = "1.24.4"
DEFAULT_DEST = Path("/tmp/jj_arena_v1244_compat_runtime")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _recorded_files() -> dict[str, dict[str, Any]]:
    if not MANIFEST_PATH.is_file():
        raise RuntimeError(f"JJ Arena materialized manifest is missing: {MANIFEST_PATH}")
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if str(payload.get("runtime_version")) != RUNTIME_VERSION:
        raise RuntimeError(
            "JJ Arena materialized manifest version mismatch: "
            f"expected={RUNTIME_VERSION} actual={payload.get('runtime_version')!r}"
        )
    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        raise RuntimeError("JJ Arena materialized manifest has no files")
    return files


def _verify_tree(root: Path, recorded: dict[str, dict[str, Any]]) -> None:
    root = root.resolve()
    expected = set(recorded)
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.relative_to(root).parts
        and path.suffix.lower() not in {".pyc", ".pyo"}
    }
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise RuntimeError(
            f"JJ Arena materialized runtime file-set mismatch: missing={missing} extra={extra}"
        )

    for rel, meta in recorded.items():
        path = root / rel
        expected_size = int(meta["size"])
        actual_size = path.stat().st_size
        if actual_size != expected_size:
            raise RuntimeError(
                f"JJ Arena materialized runtime size mismatch: {rel} "
                f"expected={expected_size} actual={actual_size}"
            )
        expected_sha = str(meta["sha256"])
        actual_sha = _sha256(path)
        if actual_sha != expected_sha:
            raise RuntimeError(
                f"JJ Arena materialized runtime checksum mismatch: {rel} actual={actual_sha}"
            )


def verify_materialized_source() -> dict[str, dict[str, Any]]:
    """Validate the immutable source tree against its committed manifest."""
    if not SOURCE_DIR.is_dir():
        raise RuntimeError(f"JJ Arena materialized v1.24.4 core is missing: {SOURCE_DIR}")
    recorded = _recorded_files()
    _verify_tree(SOURCE_DIR, recorded)
    return recorded


def build_runtime(dest: Path | None = None) -> Path:
    """Create an isolated exact copy of the verified v1.24.4 runtime."""
    target = (Path(dest) if dest is not None else DEFAULT_DEST).resolve()
    if target == SOURCE_DIR or target in SOURCE_DIR.parents or SOURCE_DIR in target.parents:
        raise RuntimeError(f"unsafe JJ Arena compatibility runtime destination: {target}")

    recorded = verify_materialized_source()
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True, exist_ok=True)

    for rel in sorted(recorded):
        source = SOURCE_DIR / rel
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    _verify_tree(target, recorded)
    return target
