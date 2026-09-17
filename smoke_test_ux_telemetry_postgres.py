from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.rows import dict_row

from db import PgConnection
from ux_telemetry import TelemetryEvent, ensure_schema, prune, record, summary


DATABASE_URL = os.environ.get("JJ_TEST_DATABASE_URL", "").strip()


class PostgresDB:
    IS_POSTGRES = True

    @contextmanager
    def connect(self):
        raw = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        con = PgConnection(raw)
        try:
            yield con
            raw.commit()
        except Exception:
            raw.rollback()
            raise
        finally:
            raw.close()


def main() -> None:
    if not DATABASE_URL:
        raise RuntimeError("JJ_TEST_DATABASE_URL is required")

    db = PostgresDB()
    now = datetime(2026, 9, 16, 7, 36, tzinfo=timezone.utc)

    with db.connect() as con:
        con.execute("DROP TABLE IF EXISTS ux_telemetry_events")

    try:
        ensure_schema(db)

        events = [
            TelemetryEvent(event="decision", detail="call", device="desktop", duration_ms=1800),
            TelemetryEvent(event="sizing", detail="preset", device="desktop"),
            TelemetryEvent(event="ui", detail="history", device="mobile"),
        ]
        assert record(db, events, now=now) == 3

        data = summary(db, days=1, now=now)
        assert data["totals"]["events"] == 3
        assert data["totals"]["decisions"] == 1
        assert data["decision_ms"]["average"] == 1800
        assert data["devices"] == [
            {"name": "desktop", "count": 2},
            {"name": "mobile", "count": 1},
        ]

        old_stamp = (now - timedelta(days=31)).isoformat()
        with db.connect() as con:
            con.execute(
                "INSERT INTO ux_telemetry_events(event_type,detail,device,duration_ms,created_at) VALUES (?,?,?,?,?)",
                ("ui", "settings", "desktop", None, old_stamp),
            )

        assert prune(db, now=now) == 1
        with db.connect() as con:
            count = con.execute("SELECT COUNT(*) AS n FROM ux_telemetry_events").fetchone()["n"]
        assert int(count) == 3
    finally:
        with db.connect() as con:
            con.execute("DROP TABLE IF EXISTS ux_telemetry_events")

    print("JJ_UX_TELEMETRY_POSTGRES_OK")


if __name__ == "__main__":
    main()
