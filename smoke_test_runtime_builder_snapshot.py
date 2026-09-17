from __future__ import annotations

import json
import tempfile
from pathlib import Path

import runtime_builder
from tools.v2_runtime_snapshot import collect_manifest


ROOT = Path(__file__).resolve().parent


def main() -> None:
    source = (ROOT / "runtime_builder.py").read_text(encoding="utf-8")

    # Stage 7 contract: compatibility runtime construction no longer imports or
    # replays the historical v15-v55 patch chain or the old release_v14 bundle.
    assert "import v15_patch" not in source
    assert "v55_post_patch.apply" not in source
    assert "release_v14" not in source
    assert "materialized_v1244" in source
    assert "materialized_v1244.manifest.json" in source

    recorded = json.loads((ROOT / "materialized_v1244.manifest.json").read_text(encoding="utf-8"))
    assert recorded["runtime_version"] == runtime_builder.RUNTIME_VERSION == "1.24.4"
    canonical = collect_manifest(ROOT / "materialized_v1244")
    assert canonical == recorded["files"], "canonical materialized tree drifted from its manifest"

    with tempfile.TemporaryDirectory(prefix="jj-runtime-snapshot-") as td:
        destination = runtime_builder.build_runtime(Path(td) / "runtime")
        copied = collect_manifest(destination)
        assert copied == recorded["files"], "snapshot builder did not reproduce the canonical manifest"
        assert destination.resolve() != (ROOT / "materialized_v1244").resolve()
        assert (destination / "server.py").is_file()
        assert (destination / "db.py").is_file()
        assert (destination / "poker_engine.py").is_file()

    print("JJ_RUNTIME_BUILDER_SNAPSHOT_OK")


if __name__ == "__main__":
    main()
