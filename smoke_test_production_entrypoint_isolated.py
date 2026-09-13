from __future__ import annotations

from tools.v2_contract_inventory import collect_contract


REQUIRED_TABLES = {
    "users",
    "sessions",
    "tables",
    "app_migrations",
    "ops_error_log",
    "table_state_backups",
}


def main() -> None:
    payload = collect_contract()
    routes = payload["routes"]
    paths = [row["path"] for row in routes]

    assert "/api/health" in paths
    assert any(path.startswith("/api/quiz/") for path in paths)
    assert any(path.startswith("/api/analysis") for path in paths)
    assert any(path.startswith("/api/admin/console") for path in paths)
    assert "/api/learning-content" in paths
    assert any(path in {"/admin", "/admin/"} for path in paths)
    assert any(row["kind"] == "websocket" for row in routes), "WebSocket route missing after production startup"

    catch_all_indexes = [i for i, path in enumerate(paths) if path == "/{path:path}"]
    assert len(catch_all_indexes) == 1, f"expected exactly one SPA catch-all, got {catch_all_indexes}"
    catch_all_index = catch_all_indexes[0]
    assert catch_all_index == len(routes) - 1, (
        "SPA catch-all must be the final production route so future extension "
        f"endpoints cannot be shadowed: index={catch_all_index} routes={len(routes)}"
    )

    tables = set(payload["sqlite"]["columns"])
    missing_tables = sorted(REQUIRED_TABLES - tables)
    assert not missing_tables, f"startup schema missing required tables: {missing_tables}"

    migration_keys = {str(row["key"]) for row in payload["sqlite"]["migrations"]}
    assert "2026-09-10-clear-existing-online-results" in migration_keys

    print(
        "JJ_PRODUCTION_ENTRYPOINT_ISOLATED_OK "
        f"routes={len(routes)} tables={len(tables)} middleware={len(payload['middleware'])}"
    )


if __name__ == "__main__":
    main()
