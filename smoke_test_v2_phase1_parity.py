from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from runtime_builder import build_runtime
from tools.v2_runtime_snapshot import collect_manifest

ROOT = Path(__file__).resolve().parent
MATERIALIZED = ROOT / "materialized_v1244"
MANIFEST = ROOT / "materialized_v1244.manifest.json"


def _run_contract(module_name: str, output: Path) -> dict:
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "v2_contract_inventory.py"),
            "--module",
            module_name,
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=True,
        timeout=60,
    )
    return json.loads(output.read_text(encoding="utf-8"))


def _migration_keys(payload: dict) -> list[str]:
    return sorted(str(row["key"]) for row in payload["sqlite"].get("migrations", []))


def main() -> None:
    assert MATERIALIZED.is_dir(), "materialized_v1244 directory is missing"
    assert MANIFEST.is_file(), "materialized_v1244.manifest.json is missing"

    recorded = json.loads(MANIFEST.read_text(encoding="utf-8"))
    recorded_files = recorded["files"]
    committed_files = collect_manifest(MATERIALIZED)
    assert committed_files == recorded_files, "committed materialized files do not match their recorded manifest"

    with tempfile.TemporaryDirectory(prefix="jj-v2-phase1-") as td:
        tmp = Path(td)
        legacy_root = build_runtime(tmp / "legacy-runtime")
        fresh_legacy_files = collect_manifest(legacy_root)
        assert fresh_legacy_files == recorded_files, "materialized core has drifted from reconstructed v1.24.4"

        legacy = _run_contract("app", tmp / "legacy-contract.json")
        candidate = _run_contract("app_materialized", tmp / "candidate-contract.json")

    assert legacy["routes"] == candidate["routes"], "HTTP/WebSocket route contract mismatch"
    assert legacy["middleware"] == candidate["middleware"], "middleware ordering mismatch"
    assert legacy["sqlite"]["columns"] == candidate["sqlite"]["columns"], "SQLite table/column schema mismatch"
    assert legacy["sqlite"]["objects"] == candidate["sqlite"]["objects"], "SQLite schema/index SQL mismatch"
    assert _migration_keys(legacy) == _migration_keys(candidate), "migration-key contract mismatch"

    legacy_server = Path(legacy["runtime_files"]["server"])
    candidate_server = Path(candidate["runtime_files"]["server"])
    candidate_db = Path(candidate["runtime_files"]["db"])
    assert legacy_server.parent != MATERIALIZED, "legacy inventory unexpectedly loaded materialized server"
    assert candidate_server.parent == MATERIALIZED, f"candidate server did not load from materialized core: {candidate_server}"
    assert candidate_db.parent == MATERIALIZED, f"candidate db did not load from materialized core: {candidate_db}"

    print(
        "JJ_V2_PHASE1_PARITY_OK "
        f"files={len(recorded_files)} routes={len(candidate['routes'])} "
        f"tables={len(candidate['sqlite']['columns'])} middleware={len(candidate['middleware'])}"
    )


if __name__ == "__main__":
    main()
