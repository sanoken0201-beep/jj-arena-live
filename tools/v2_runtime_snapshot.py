from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from runtime_builder import RUNTIME_VERSION, build_runtime


IGNORED_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache"}
IGNORED_SUFFIXES = {".pyc", ".pyo", ".db", ".sqlite", ".sqlite3", ".wal", ".shm"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_runtime_state(path: Path) -> bool:
    if any(part in IGNORED_DIRS for part in path.parts):
        return True
    return path.suffix.lower() in IGNORED_SUFFIXES


def collect_manifest(root: Path) -> dict[str, dict[str, Any]]:
    """Return a stable content manifest for source/static runtime files.

    Database/runtime-state files are intentionally excluded. The v2 materialization
    project treats the production database as an external compatibility boundary.
    """
    base = root.resolve()
    manifest: dict[str, dict[str, Any]] = {}
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(base)
        if _is_runtime_state(rel):
            continue
        manifest[rel.as_posix()] = {
            "size": path.stat().st_size,
            "sha256": _sha256(path),
        }
    return manifest


def current_git_commit(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def write_manifest(root: Path, output: Path, *, repo_root: Path | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "runtime_version": RUNTIME_VERSION,
        "source_commit": current_git_commit(repo_root or Path.cwd()),
        "files": collect_manifest(root),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def materialize_candidate(destination: Path, *, force: bool = False) -> tuple[Path, dict[str, dict[str, Any]]]:
    """Create a source-only copy of the reconstructed runtime.

    This helper is deliberately conservative. It does not modify app.py, Render,
    PostgreSQL, or the current production runtime. Runtime state files are not
    copied into the candidate tree.
    """
    dest = destination.resolve()
    if dest.exists():
        if not force:
            raise FileExistsError(f"destination already exists: {dest}")
        shutil.rmtree(dest)

    with tempfile.TemporaryDirectory(prefix="jj-v2-materialize-") as td:
        legacy_root = build_runtime(Path(td) / "legacy-runtime")
        for path in sorted(legacy_root.rglob("*")):
            rel = path.relative_to(legacy_root)
            if path.is_dir():
                if any(part in IGNORED_DIRS for part in rel.parts):
                    continue
                (dest / rel).mkdir(parents=True, exist_ok=True)
                continue
            if _is_runtime_state(rel):
                continue
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)

    return dest, collect_manifest(dest)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JJ Arena v2 runtime snapshot/materialization helper")
    sub = parser.add_subparsers(dest="command", required=True)

    snapshot = sub.add_parser("snapshot", help="reconstruct v1.24.4 and write a deterministic manifest")
    snapshot.add_argument("--output", type=Path, required=True)

    materialize = sub.add_parser("materialize", help="write a source-only reconstructed runtime candidate")
    materialize.add_argument("--destination", type=Path, required=True)
    materialize.add_argument("--manifest", type=Path)
    materialize.add_argument("--force", action="store_true")

    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    repo_root = Path(__file__).resolve().parents[1]

    if args.command == "snapshot":
        with tempfile.TemporaryDirectory(prefix="jj-v2-snapshot-") as td:
            root = build_runtime(Path(td) / "runtime")
            payload = write_manifest(root, args.output, repo_root=repo_root)
        print(f"JJ_V2_SNAPSHOT_OK version={payload['runtime_version']} files={len(payload['files'])}")
        return

    candidate, manifest = materialize_candidate(args.destination, force=args.force)
    if args.manifest:
        payload = {
            "runtime_version": RUNTIME_VERSION,
            "source_commit": current_git_commit(repo_root),
            "files": manifest,
        }
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(f"JJ_V2_MATERIALIZE_OK version={RUNTIME_VERSION} files={len(manifest)} dest={candidate}")


if __name__ == "__main__":
    main()
