from __future__ import annotations

from pathlib import Path

from tools.v2_contract_inventory import collect_contract

ROOT = Path(__file__).resolve().parent
MATERIALIZED = (ROOT / "materialized_v1244").resolve()


def main() -> None:
    payload = collect_contract("app")

    assert payload["entrypoint"] == "app"
    server_path = Path(payload["runtime_files"]["server"]).resolve()
    db_path = Path(payload["runtime_files"]["db"]).resolve()
    assert server_path.parent == MATERIALIZED, f"production server is not materialized: {server_path}"
    assert db_path.parent == MATERIALIZED, f"production db is not materialized: {db_path}"

    routes = payload["routes"]
    paths = [row["path"] for row in routes]
    assert "/api/health" in paths
    assert any(row["kind"] == "websocket" for row in routes)
    assert any(path.startswith("/api/quiz/") for path in paths)
    assert any(path.startswith("/api/analysis") for path in paths)
    assert any(path.startswith("/api/admin/console") for path in paths)

    migration_keys = {str(row["key"]) for row in payload["sqlite"].get("migrations", [])}
    assert "2026-09-10-clear-existing-online-results" in migration_keys

    print(
        "JJ_V2_PRODUCTION_CUTOVER_OK "
        f"routes={len(routes)} tables={len(payload['sqlite']['columns'])} "
        f"middleware={len(payload['middleware'])}"
    )


if __name__ == "__main__":
    main()
