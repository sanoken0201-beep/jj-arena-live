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

    catch_all_index = next(
        (i for i, path in enumerate(paths) if "path:path" in path or path == "/{path}"),
        None,
    )
    if catch_all_index is not None:
        for i, path in enumerate(paths):
            if (
                path in {"/admin", "/admin/", "/api/learning-content"}
                or path.startswith("/admin-static")
                or path.startswith("/api/admin/console")
                or path.startswith("/api/analysis")
                or path.startswith("/api/quiz/")
                or path.startswith("/api/home/")
            ):
                assert i < catch_all_index, f"extension route shadowed by SPA catch-all: {path}"

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
