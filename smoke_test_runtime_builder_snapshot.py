from __future__ import annotations

import ast
import json
import tempfile
from pathlib import Path

import runtime_builder
from tools.v2_runtime_snapshot import collect_manifest


ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT / "materialized_v1244").resolve()
MANIFEST = ROOT / "materialized_v1244.manifest.json"


def _imported_modules() -> set[str]:
    tree = ast.parse((ROOT / "runtime_builder.py").read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _assert_unsafe_target(path: Path) -> None:
    try:
        runtime_builder._resolve_safe_target(path)
    except RuntimeError:
        return
    raise AssertionError(f"runtime builder accepted unsafe destination: {path}")


def main() -> None:
    recorded = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert recorded["runtime_version"] == runtime_builder.RUNTIME_VERSION == "1.24.4"
    assert runtime_builder.SOURCE_DIR == SOURCE
    assert runtime_builder.MANIFEST_PATH.resolve() == MANIFEST.resolve()

    # Historical release reconstruction must not return as a runtime dependency.
    imports = _imported_modules()
    assert "mobile_poker_hotfix" not in imports
    assert not any(name.startswith("v") and "patch" in name for name in imports), imports

    expected = recorded["files"]
    runtime_builder.verify_materialized_source()
    canonical = collect_manifest(SOURCE)
    assert canonical == expected, "canonical materialized tree drifted from its manifest"

    # Validate all destructive-overlap directions without invoking rmtree on them.
    _assert_unsafe_target(SOURCE)
    _assert_unsafe_target(SOURCE / "unsafe-child")
    _assert_unsafe_target(ROOT)

    with tempfile.TemporaryDirectory(prefix="jj-runtime-snapshot-") as td:
        target = Path(td) / "compat-runtime"
        destination = runtime_builder.build_runtime(target)
        assert destination.resolve() == target.resolve()
        assert destination.resolve() != SOURCE
        copied = collect_manifest(destination)
        assert copied == expected, "snapshot builder did not reproduce the canonical manifest"
        assert (destination / "server.py").is_file()
        assert (destination / "db.py").is_file()
        assert (destination / "poker_engine.py").is_file()

        # The compatibility copy must never alias or mutate the canonical source.
        source_server = (SOURCE / "server.py").read_bytes()
        with (destination / "server.py").open("ab") as fh:
            fh.write(b"\n# compatibility-copy mutation probe\n")
        assert (SOURCE / "server.py").read_bytes() == source_server

        # Rebuilding the same destination must remove stale content and restore
        # byte-for-byte manifest parity.
        rebuilt = runtime_builder.build_runtime(target)
        assert collect_manifest(rebuilt) == expected
        assert (rebuilt / "server.py").read_bytes() == source_server

    print("JJ_RUNTIME_BUILDER_SNAPSHOT_OK")


if __name__ == "__main__":
    main()
