from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError

from ux_telemetry import TelemetryBatch, TelemetryEvent, ensure_schema, record, summary


class FakeDB:
    IS_POSTGRES = False

    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

    @contextmanager
    def connect(self):
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise


def main() -> None:
    db = FakeDB()
    ensure_schema(db)

    cols = {r["name"] for r in db.conn.execute("PRAGMA table_info(ux_telemetry_events)").fetchall()}
    assert cols == {"id", "event_type", "detail", "device", "duration_ms", "created_at"}
    for forbidden in ("user_id", "name", "table_id", "hand_id", "cards", "amount", "chat", "ip", "user_agent", "session_id"):
        assert forbidden not in cols

    now = datetime(2026, 9, 13, 5, 0, tzinfo=timezone.utc)
    events = [
        TelemetryEvent(event="decision", detail="fold", device="mobile", duration_ms=1000),
        TelemetryEvent(event="decision", detail="call", device="mobile", duration_ms=2000),
        TelemetryEvent(event="decision", detail="raise", device="desktop", duration_ms=9000),
        TelemetryEvent(event="timeout", detail="fold", device="mobile"),
        TelemetryEvent(event="fallback", detail="ws_close", device="desktop"),
        TelemetryEvent(event="reconnect", detail="ws_open", device="desktop"),
        TelemetryEvent(event="sizing", detail="preset", device="mobile"),
        TelemetryEvent(event="preaction", detail="check_fold", device="mobile"),
        TelemetryEvent(event="ui", detail="history", device="mobile"),
    ]
    assert record(db, events, now=now) == len(events)

    data = summary(db, days=7, now=now)
    assert data["totals"]["decisions"] == 3
    assert data["totals"]["timeouts"] == 1
    assert data["totals"]["timeout_rate_pct"] == 25.0
    assert data["totals"]["fallbacks"] == 1
    assert data["totals"]["reconnects"] == 1
    assert data["decision_ms"]["average"] == 4000
    assert data["decision_ms"]["p50"] == 2000
    assert data["decision_ms"]["p90"] == 9000
    assert data["privacy"] == {
        "stores_user_identity": False,
        "stores_hand_or_cards": False,
        "stores_chip_amounts": False,
        "stores_free_text": False,
    }

    db.conn.execute(
        "INSERT INTO ux_telemetry_events(event_type,detail,device,duration_ms,created_at) VALUES (?,?,?,?,?)",
        ("ui", "settings", "desktop", None, (now - timedelta(days=31)).isoformat()),
    )
    db.conn.commit()
    record(db, [TelemetryEvent(event="ui", detail="focus", device="desktop")], now=now)
    assert db.conn.execute("SELECT COUNT(*) n FROM ux_telemetry_events WHERE detail='settings'").fetchone()["n"] == 0

    for payload in (
        {"event": "decision", "detail": "call", "device": "mobile"},
        {"event": "ui", "detail": "settings", "device": "mobile", "duration_ms": 12},
        {"event": "ui", "detail": "free_text", "device": "mobile"},
        {"event": "ui", "detail": "settings", "device": "mobile", "user_id": 123},
        {"event": "ui", "detail": "settings", "device": "mobile", "hand_id": "abc"},
        {"event": "ui", "detail": "settings", "device": "mobile", "amount": 100},
    ):
        try:
            TelemetryEvent(**payload)
        except ValidationError:
            pass
        else:
            raise AssertionError(f"unsafe telemetry payload accepted: {payload}")

    try:
        TelemetryBatch(events=[TelemetryEvent(event="ui", detail="settings", device="mobile")] * 31)
    except ValidationError:
        pass
    else:
        raise AssertionError("oversized telemetry batch accepted")

    print("JJ_UX_TELEMETRY_OK")


if __name__ == "__main__":
    main()
