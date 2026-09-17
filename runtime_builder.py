from __future__ import annotations

"""Build the rollback/parity runtime from the immutable v1.24.4 snapshot.

Historically this module reconstructed v1.24.4 by unpacking the v1.14 release
bundle and replaying every patch from v15 through v55. Production has already
cut over to the committed ``materialized_v1244`` core, so replaying that chain
is now unnecessary runtime debt.

The compatibility builder intentionally copies only files recorded in
``materialized_v1244.manifest.json`` and verifies their size/hash before and
after copying. This keeps ``app_legacy`` isolated in a separate directory while
making the committed materialized snapshot the single canonical v1.24.4 source.
"""

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MATERIALIZED_DIR = ROOT / "materialized_v1244"
MANIFEST_PATH = ROOT / "materialized_v1244.manifest.json"
RUNTIME_VERSION = "1.24.4"
DEFAULT_DEST = Path("/tmp/jj_arena_v56_runtime")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_files() -> dict[str, dict[str, object]]:
    if not MANIFEST_PATH.is_file():
        raise RuntimeError(f"JJ Arena materialized manifest missing: {MANIFEST_PATH}")
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if str(payload.get("runtime_version")) != RUNTIME_VERSION:
        raise RuntimeError(
            "JJ Arena materialized runtime version mismatch: "
            f"expected={RUNTIME_VERSION} actual={payload.get('runtime_version')}"
        )
    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        raise RuntimeError("JJ Arena materialized manifest has no files")
    return files


def _verify_file(path: Path, expected: dict[str, object], rel: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"JJ Arena materialized file missing: {rel}")
    expected_size = int(expected.get("size", -1))
    actual_size = path.stat().st_size
    if actual_size != expected_size:
        raise RuntimeError(
            f"JJ Arena materialized size mismatch: {rel} expected={expected_size} actual={actual_size}"
        )
    expected_hash = str(expected.get("sha256") or "")
    actual_hash = _sha256(path)
    if actual_hash != expected_hash:
        raise RuntimeError(
            f"JJ Arena materialized checksum mismatch: {rel} actual={actual_hash}"
        )


def build_runtime(dest: Path | None = None) -> Path:
    """Copy the verified canonical v1.24.4 snapshot to an isolated runtime dir."""
    target = Path(dest) if dest is not None else DEFAULT_DEST
    files = _manifest_files()

    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True, exist_ok=True)

    for rel, expected in sorted(files.items()):
        rel_path = Path(rel)
        if rel_path.is_absolute() or ".." in rel_path.parts:
            raise RuntimeError(f"Unsafe path in JJ Arena materialized manifest: {rel}")
        source = MATERIALIZED_DIR / rel_path
        _verify_file(source, expected, rel)
        destination = target / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        _verify_file(destination, expected, rel)

    return target
