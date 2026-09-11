from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MATERIALIZED = (ROOT / "materialized_v1244").resolve()


def main() -> None:
    if not os.environ.get("DATABASE_URL"):
        raise AssertionError("DATABASE_URL is required for production PostgreSQL cutover gate")

    os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"
    os.environ["JJ_ADMIN_NAME"] = "V2_PRODUCTION_PG_ADMIN"

    import app as production

    assert production.db.IS_POSTGRES, "production entrypoint did not select PostgreSQL"
    assert Path(production.runtime_server.__file__).resolve().parent == MATERIALIZED
    assert Path(production.db.__file__).resolve().parent == MATERIALIZED
    assert Path(production.runtime_poker_engine.__file__).resolve().parent == MATERIALIZED

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
        con.execute("SELECT COUNT(*) AS c FROM table_state_backups").fetchone()
        con.execute("SELECT COUNT(*) AS c FROM ops_error_log").fetchone()

    assert int(marker["c"] or 0) == 1, "historical migration marker missing on PostgreSQL"

    print(
        "JJ_V2_PRODUCTION_POSTGRES_OK "
        f"routes={len(paths)} core={MATERIALIZED.name}"
    )


if __name__ == "__main__":
    main()
