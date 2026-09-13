from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from collections import defaultdict
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


def _strip_phase4c_extensions(payload: dict) -> dict:
    """Remove only the explicitly audited post-materialization Phase 4C surface.

    app_legacy remains the immutable v1.24.4 parity oracle. New root-level
    production extensions are allowed only when this gate names their exact
    routes/schema; everything else must still match legacy byte-for-contract.
    """
    clone = json.loads(json.dumps(payload))
    allowed_routes = {
        ("http", "/api/ux-telemetry", ("POST",)),
        ("http", "/api/admin/console/ux-telemetry", ("GET",)),
    }
    present = {
        (str(r.get("kind")), str(r.get("path")), tuple(r.get("methods") or []))
        for r in clone["routes"]
        if str(r.get("path")) in {"/api/ux-telemetry", "/api/admin/console/ux-telemetry"}
    }
    assert present == allowed_routes, f"unexpected Phase 4C route contract: {present}"
    clone["routes"] = [
        r for r in clone["routes"]
        if str(r.get("path")) not in {"/api/ux-telemetry", "/api/admin/console/ux-telemetry"}
    ]

    columns = clone["sqlite"]["columns"]
    assert set(columns.get("ux_telemetry_events", [{}])[0].keys()) >= {"cid", "name", "type", "notnull", "dflt_value", "pk"}
    names = [str(row["name"]) for row in columns.get("ux_telemetry_events", [])]
    assert names == ["id", "event_type", "detail", "device", "duration_ms", "created_at"], names
    columns.pop("ux_telemetry_events", None)

    allowed_objects = {
        "ux_telemetry_events",
        "idx_ux_telemetry_created",
        "idx_ux_telemetry_event",
    }
    telemetry_objects = {
        str(row.get("name"))
        for row in clone["sqlite"]["objects"]
        if str(row.get("tbl_name")) == "ux_telemetry_events"
    }
    assert telemetry_objects == allowed_objects, f"unexpected Phase 4C SQLite objects: {telemetry_objects}"
    clone["sqlite"]["objects"] = [
        row for row in clone["sqlite"]["objects"]
        if str(row.get("tbl_name")) != "ux_telemetry_events"
    ]
    return clone


def _route_contract(rows: list[dict]) -> list[tuple[str, str, tuple[str, ...], str]]:
    """Compare the complete route multiset independent of global registration order."""
    return sorted(
        (
            str(row.get("kind") or ""),
            str(row.get("path") or ""),
            tuple(str(method) for method in (row.get("methods") or [])),
            str(row.get("name") or ""),
        )
        for row in rows
    )


def _duplicate_route_precedence(rows: list[dict]) -> dict[tuple[str, str, tuple[str, ...]], list[str]]:
    """Keep endpoint precedence strict where order can actually change dispatch."""
    groups: dict[tuple[str, str, tuple[str, ...]], list[str]] = defaultdict(list)
    for row in rows:
        key = (
            str(row.get("kind") or ""),
            str(row.get("path") or ""),
            tuple(str(method) for method in (row.get("methods") or [])),
        )
        groups[key].append(str(row.get("name") or ""))
    return {key: names for key, names in groups.items() if len(names) > 1}


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

        legacy = _run_contract("app_legacy", tmp / "legacy-contract.json")
        materialized = _run_contract("app_materialized", tmp / "materialized-contract.json")

    comparable = _strip_phase4c_extensions(materialized)
    assert _route_contract(legacy["routes"]) == _route_contract(comparable["routes"]), (
        "HTTP/WebSocket route contract mismatch outside audited Phase 4C extensions"
    )
    assert _duplicate_route_precedence(legacy["routes"]) == _duplicate_route_precedence(comparable["routes"]), (
        "duplicate route dispatch precedence changed outside audited Phase 4C extensions"
    )
    assert legacy["middleware"] == comparable["middleware"], "middleware ordering mismatch"
    assert legacy["sqlite"]["columns"] == comparable["sqlite"]["columns"], "SQLite table/column schema mismatch outside audited Phase 4C extensions"
    assert legacy["sqlite"]["objects"] == comparable["sqlite"]["objects"], "SQLite schema/index SQL mismatch outside audited Phase 4C extensions"
    assert _migration_keys(legacy) == _migration_keys(materialized), "migration-key contract mismatch"

    legacy_server = Path(legacy["runtime_files"]["server"])
    materialized_server = Path(materialized["runtime_files"]["server"])
    materialized_db = Path(materialized["runtime_files"]["db"])
    assert legacy_server.parent != MATERIALIZED, "legacy inventory unexpectedly loaded materialized server"
    assert materialized_server.parent == MATERIALIZED, f"materialized server did not load from committed core: {materialized_server}"
    assert materialized_db.parent == MATERIALIZED, f"materialized db did not load from committed core: {materialized_db}"

    print(
        "JJ_V2_PHASE1_PARITY_OK "
        f"files={len(recorded_files)} routes={len(materialized['routes'])} "
        f"tables={len(materialized['sqlite']['columns'])} middleware={len(materialized['middleware'])}"
    )


if __name__ == "__main__":
    main()
