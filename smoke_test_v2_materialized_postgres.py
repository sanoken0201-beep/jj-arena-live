from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch


def main() -> None:
    if not os.environ.get("DATABASE_URL"):
        raise AssertionError("DATABASE_URL is required for materialized PostgreSQL startup gate")

    os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"
    os.environ["JJ_ADMIN_NAME"] = "V2_MATERIALIZED_PG_ADMIN"

    import app_materialized as production

    assert production.db.IS_POSTGRES, "materialized entrypoint did not select PostgreSQL"
    materialized = production.DEST.resolve()
    assert Path(production.runtime_server.__file__).resolve().parent == materialized
    assert Path(production.db.__file__).resolve().parent == materialized
    assert Path(production.runtime_poker_engine.__file__).resolve().parent == materialized

    paths = [str(getattr(route, "path", "") or "") for route in production.app.router.routes]
    assert "/api/health" in paths
    assert any(path.startswith("/api/quiz/") for path in paths)
    assert any(path.startswith("/api/analysis") for path in paths)
    assert any(path.startswith("/api/admin/console") for path in paths)
    assert any("ws" in path.lower() for path in paths), "WebSocket route missing"

    with production.db.connect() as con:
        marker = con.execute(
            "SELECT COUNT(*) AS c FROM app_migrations WHERE key=?",
            ("2026-09-10-clear-existing-online-results",),
        ).fetchone()
        backups = con.execute("SELECT COUNT(*) AS c FROM table_state_backups").fetchone()
        errors = con.execute("SELECT COUNT(*) AS c FROM ops_error_log").fetchone()

    # The production schema now exists. A second legacy migration pass must
    # be pure DML/metadata reads: no no-op ALTER may take AccessExclusiveLock
    # while another instance is serving authentication reads during rollout.
    observed_alters: list[str] = []
    original_execute = production.db.PgConnection.execute

    def observe_execute(connection, sql, params=()):
        if sql.strip().upper().startswith("ALTER TABLE"):
            observed_alters.append(sql)
        return original_execute(connection, sql, params)

    with patch.object(production.db.PgConnection, "execute", observe_execute):
        with production.db.connect() as con:
            production.db._migrate_legacy_beta(con)
        production.db.ensure_profile_columns()
    assert not observed_alters, f"repeated startup DDL on current PG schema: {observed_alters}"

    assert int(marker["c"] or 0) == 1, "historical migration marker missing on PostgreSQL"
    assert int(backups["c"] or 0) >= 0
    assert int(errors["c"] or 0) >= 0

    print(
        "JJ_V2_MATERIALIZED_POSTGRES_OK "
        f"routes={len(paths)} core={materialized.name}"
    )


if __name__ == "__main__":
    main()
