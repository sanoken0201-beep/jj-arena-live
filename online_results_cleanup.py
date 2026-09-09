from __future__ import annotations

from typing import Any


MIGRATION_KEY = "2026-09-10-clear-existing-online-results"


def apply(db: Any) -> dict[str, int | bool]:
    """Delete the pre-cleanup online hand results exactly once.

    This migration intentionally touches only ``online_hand_results``. Club
    point entries, the point ledger, user accounts, table state, and other
    application data are left intact. The migration marker is inserted in the
    same transaction as the deletion so a failed cleanup can safely retry.

    Newly recorded online results after this migration are preserved on every
    later restart because the marker makes the migration a no-op.
    """
    with db.connect() as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS app_migrations("
            "key TEXT PRIMARY KEY,"
            "applied_at TEXT NOT NULL)"
        )
        marker = con.execute(
            "INSERT OR IGNORE INTO app_migrations(key,applied_at) VALUES (?,?)",
            (MIGRATION_KEY, db.utcnow()),
        )
        if int(getattr(marker, "rowcount", 0) or 0) == 0:
            return {"applied": False, "rows": 0, "users": 0}

        stats = con.execute(
            "SELECT COUNT(*) AS rows, COUNT(DISTINCT user_id) AS users "
            "FROM online_hand_results"
        ).fetchone()
        rows = int(stats["rows"] or 0)
        users = int(stats["users"] or 0)
        con.execute("DELETE FROM online_hand_results")

    print(f"JJ_ONLINE_RESULTS_PURGED rows={rows} users={users}")
    return {"applied": True, "rows": rows, "users": users}
