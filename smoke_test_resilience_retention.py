from __future__ import annotations

import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import resilience


class _SQLiteDB:
    IS_POSTGRES = False

    def __init__(self, path: Path):
        self.path = path

    def connect(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        return con


def main() -> None:
    assert resilience.ERROR_RETENTION_DAYS == 90
    with tempfile.TemporaryDirectory(prefix="jj-resilience-retention-") as directory:
        db = _SQLiteDB(Path(directory) / "resilience.sqlite3")
        with db.connect() as con:
            con.execute("CREATE TABLE users(id INTEGER PRIMARY KEY)")
            con.execute("CREATE TABLE tables(id TEXT PRIMARY KEY,state_json TEXT NOT NULL,updated_at TEXT)")
        resilience._ensure_schema(db)

        with db.connect() as con:
            con.execute(
                "INSERT INTO ops_error_log(id,event_type,method,path,detail,created_at) VALUES (?,?,?,?,?,?)",
                ("old", "test", "GET", "/old", "old", "2026-05-01T00:00:00+00:00"),
            )
            con.execute(
                "INSERT INTO ops_error_log(id,event_type,method,path,detail,created_at) VALUES (?,?,?,?,?,?)",
                ("recent", "test", "GET", "/recent", "recent", "2026-09-12T00:00:00+00:00"),
            )

        resilience.prune_error_log(db, datetime(2026, 9, 13, tzinfo=timezone.utc))
        with db.connect() as con:
            rows = con.execute("SELECT id FROM ops_error_log ORDER BY id").fetchall()
        assert [str(row["id"]) for row in rows] == ["recent"]

    print("JJ_RESILIENCE_RETENTION_OK")


if __name__ == "__main__":
    main()
