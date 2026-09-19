from __future__ import annotations

"""Build the rollback/parity runtime from the immutable v1.24.4 snapshot.

Historically this module reconstructed v1.24.4 by unpacking the v1.14 release
bundle and replaying every patch from v15 through v55. Production has already
cut over to the committed ``materialized_v1244`` core, so replaying that chain
is now unnecessary runtime debt.

The compatibility builder intentionally copies only files recorded in
``materialized_v1244.manifest.json`` and verifies the complete source/copy tree,
including file-set parity plus size/hash integrity. Narrow Python/SQLite cache
artifacts are ignored because isolated runtime tests can create them locally.
This keeps ``app_legacy`` isolated in a separate directory while making the
committed materialized snapshot the single canonical v1.24.4 source.
"""

import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MATERIALIZED_DIR = ROOT / "materialized_v1244"
SOURCE_DIR = MATERIALIZED_DIR.resolve()
MANIFEST_PATH = ROOT / "materialized_v1244.manifest.json"
RUNTIME_VERSION = "1.24.4"
DEFAULT_DEST = Path("/tmp/jj_arena_v56_runtime")

_TRANSIENT_DIR_NAMES = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache"})
_TRANSIENT_SUFFIXES = frozenset({".pyc", ".pyo", ".db", ".sqlite", ".sqlite3", ".wal", ".shm"})
_SQLITE_SIDECAR_ENDINGS = ("-wal", "-shm", "-journal")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_runtime_transient(relative: Path) -> bool:
    if any(part in _TRANSIENT_DIR_NAMES for part in relative.parts):
        return True
    name = relative.name.lower()
    if relative.suffix.lower() in _TRANSIENT_SUFFIXES:
        return True
    return name.endswith(_SQLITE_SIDECAR_ENDINGS)


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
    for rel, expected in files.items():
        rel_path = Path(rel)
        if rel_path.is_absolute() or ".." in rel_path.parts:
            raise RuntimeError(f"Unsafe path in JJ Arena materialized manifest: {rel}")
        if not isinstance(expected, dict):
            raise RuntimeError(f"Invalid JJ Arena materialized manifest entry: {rel}")
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


def _verify_tree(root: Path, files: dict[str, dict[str, object]]) -> None:
    resolved_root = root.resolve()
    expected_paths = set(files)
    actual_paths: set[str] = set()

    for path in resolved_root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(resolved_root)
        if _is_runtime_transient(relative):
            continue
        actual_paths.add(relative.as_posix())

    if actual_paths != expected_paths:
        missing = sorted(expected_paths - actual_paths)
        extra = sorted(actual_paths - expected_paths)
        raise RuntimeError(
            f"JJ Arena materialized file-set mismatch: missing={missing} extra={extra}"
        )

    for rel, expected in files.items():
        _verify_file(resolved_root / rel, expected, rel)


def verify_materialized_source() -> dict[str, dict[str, object]]:
    """Verify the canonical materialized tree exactly matches its manifest."""
    if not SOURCE_DIR.is_dir():
        raise RuntimeError(f"JJ Arena materialized source missing: {SOURCE_DIR}")
    files = _manifest_files()
    _verify_tree(SOURCE_DIR, files)
    return files


def _resolve_safe_target(dest: Path | None = None) -> Path:
    """Resolve and reject any destination that can overlap the canonical source."""
    target = (Path(dest) if dest is not None else DEFAULT_DEST).resolve()
    if target == SOURCE_DIR or target in SOURCE_DIR.parents or SOURCE_DIR in target.parents:
        raise RuntimeError(f"Unsafe JJ Arena compatibility runtime destination: {target}")
    return target


def build_runtime(dest: Path | None = None) -> Path:
    """Copy the verified canonical v1.24.4 snapshot to an isolated runtime dir."""
    target = _resolve_safe_target(dest)
    files = verify_materialized_source()

    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True, exist_ok=True)

    for rel in sorted(files):
        source = SOURCE_DIR / rel
        destination = target / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    _verify_tree(target, files)
    return target
