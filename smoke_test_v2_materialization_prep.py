from __future__ import annotations

import tempfile
from pathlib import Path

from runtime_builder import RUNTIME_VERSION, build_runtime
from tools.v2_runtime_snapshot import collect_manifest, materialize_candidate


REQUIRED_RUNTIME_FILES = {
    "server.py",
    "db.py",
    "poker_engine.py",
    "static/app.js",
    "static/styles.css",
    "static/index.html",
    "static/sw.js",
}


def main() -> None:
    assert RUNTIME_VERSION == "1.24.4", RUNTIME_VERSION

    with tempfile.TemporaryDirectory(prefix="jj-v2-prep-") as td:
        base = Path(td)
        compat_a = build_runtime(base / "compat-a")
        compat_b = build_runtime(base / "compat-b")

        manifest_a = collect_manifest(compat_a)
        manifest_b = collect_manifest(compat_b)

        assert manifest_a, "compatibility runtime manifest is empty"
        assert manifest_a == manifest_b, "compatibility runtime copy is not content-deterministic"

        missing = sorted(REQUIRED_RUNTIME_FILES - set(manifest_a))
        assert not missing, f"required compatibility runtime files missing: {missing}"

        candidate, candidate_manifest = materialize_candidate(base / "candidate")
        assert candidate.exists()
        assert candidate_manifest == manifest_a, "source-only materialization changed compatibility runtime content"

        for rel in candidate_manifest:
            lower = rel.lower()
            assert "__pycache__" not in lower
            assert not lower.endswith((".pyc", ".pyo", ".db", ".sqlite", ".sqlite3", ".wal", ".shm")), rel

        server = (candidate / "server.py").read_text(encoding="utf-8")
        index = (candidate / "static" / "index.html").read_text(encoding="utf-8")
        sw = (candidate / "static" / "sw.js").read_text(encoding="utf-8")

        assert 'version="1.24.4"' in server or '"version":"1.24.4"' in server
        assert "?v=56" in index
        assert "jj-arena-live-v56" in sw

    print("JJ_V2_MATERIALIZATION_PREP_OK")


if __name__ == "__main__":
    main()
