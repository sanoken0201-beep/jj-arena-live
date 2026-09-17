from __future__ import annotations

import ast
import hashlib
import json
import tempfile
from pathlib import Path

import runtime_builder

ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT / "materialized_v1244").resolve()
MANIFEST = ROOT / "materialized_v1244.manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest(root: Path) -> dict[str, dict[str, object]]:
    root = root.resolve()
    result: dict[str, dict[str, object]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if "__pycache__" in rel.parts or path.suffix.lower() in {".pyc", ".pyo"}:
            continue
        result[rel.as_posix()] = {
            "size": path.stat().st_size,
            "sha256": _sha256(path),
        }
    return result


def _imported_modules() -> set[str]:
    tree = ast.parse((ROOT / "runtime_builder.py").read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def main() -> None:
    recorded = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert recorded["runtime_version"] == "1.24.4"
    assert runtime_builder.RUNTIME_VERSION == "1.24.4"
    assert runtime_builder.SOURCE_DIR == SOURCE
    assert runtime_builder.MANIFEST_PATH.resolve() == MANIFEST.resolve()

    # Historical release reconstruction must no longer be a runtime dependency.
    imports = _imported_modules()
    assert "mobile_poker_hotfix" not in imports
    assert not any(name.startswith("v") and "patch" in name for name in imports), imports

    expected = recorded["files"]
    runtime_builder.verify_materialized_source()
    assert _manifest(SOURCE) == expected

    with tempfile.TemporaryDirectory(prefix="jj-runtime-snapshot-") as td:
        target = Path(td) / "compat-runtime"
        built = runtime_builder.build_runtime(target)
        assert built.resolve() == target.resolve()
        assert built.resolve() != SOURCE
        assert _manifest(built) == expected

        # The compatibility copy must not alias or mutate the immutable source.
        source_server = (SOURCE / "server.py").read_bytes()
        with (built / "server.py").open("ab") as fh:
            fh.write(b"\n# compatibility-copy mutation probe\n")
        assert (SOURCE / "server.py").read_bytes() == source_server

        # A rebuild must discard stale target content and restore exact bytes.
        rebuilt = runtime_builder.build_runtime(target)
        assert _manifest(rebuilt) == expected
        assert (rebuilt / "server.py").read_bytes() == source_server

    try:
        runtime_builder.build_runtime(SOURCE / "unsafe-child")
    except RuntimeError:
        pass
    else:
        raise AssertionError("runtime builder accepted a destination inside materialized_v1244")

    print("JJ_RUNTIME_BUILDER_SNAPSHOT_OK")


if __name__ == "__main__":
    main()
