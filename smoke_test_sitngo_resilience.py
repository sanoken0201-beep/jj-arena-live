"""Sit&Go persisted-state generation backup and corruption recovery regression."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import sitngo_resilience
from smoke_test_sitngo_phase1 import add_member, production_app as prod, registration_moment, sitngo


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    db = prod.db
    service = prod.app.state.jj_sitngo
    runtime = service.runtime
    with db.connect() as con:
        admin = int(con.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()["id"])

    users = [add_member(7300 + i) for i in range(2)]
    starts = datetime.now(timezone.utc) + timedelta(minutes=10)
    event = service.create_event(
        sitngo.SitNGoCreateIn(name="resilience", starts_at=starts.isoformat()),
        admin,
    )
    with patch.object(sitngo, "_utcnow", return_value=registration_moment(event)):
        for uid in users:
            service.register(event["id"], uid)
    service.reconcile(starts + timedelta(seconds=1))
    eid = event["id"]

    state = runtime.load(eid)
    with db.connect() as con:
        initial = int(con.execute(
            "SELECT COUNT(*) c FROM sitngo_state_backups WHERE event_id=?",
            (eid,),
        ).fetchone()["c"])
    require(initial >= 1, "tournament creation did not create a recovery snapshot")

    # Heartbeat-only fields and revision increments must not churn retention.
    heartbeat = runtime.load(eid)
    heartbeat["tournament"]["elapsed_seconds"] = float(heartbeat["tournament"].get("elapsed_seconds") or 0) + 5
    heartbeat["tournament"]["clock_at_epoch"] = float(heartbeat["tournament"].get("clock_at_epoch") or 0) + 5
    runtime.save(heartbeat)
    with db.connect() as con:
        after_heartbeat = int(con.execute(
            "SELECT COUNT(*) c FROM sitngo_state_backups WHERE event_id=?",
            (eid,),
        ).fetchone()["c"])
    require(after_heartbeat == initial, "heartbeat-only save consumed a backup generation")

    # A meaningful persisted change must create a new generation.
    meaningful = runtime.load(eid)
    meaningful["_resilience_test_marker"] = "meaningful"
    runtime.save(meaningful)
    with db.connect() as con:
        after_meaningful = int(con.execute(
            "SELECT COUNT(*) c FROM sitngo_state_backups WHERE event_id=?",
            (eid,),
        ).fetchone()["c"])
        current = con.execute(
            "SELECT revision FROM sitngo_games WHERE event_id=?",
            (eid,),
        ).fetchone()
    require(after_meaningful == initial + 1, "meaningful state change did not create a backup generation")
    corrupt_revision = int(current["revision"])

    # Corrupt only the authoritative JSON. load() must atomically restore the
    # newest valid same-event generation and keep revision/state in agreement.
    with db.connect() as con:
        con.execute(
            "UPDATE sitngo_games SET state_json=? WHERE event_id=?",
            ('{"broken":', eid),
        )
    restored = runtime.load(eid)
    require(restored.get("_resilience_test_marker") == "meaningful", "latest valid generation was not restored")
    with db.connect() as con:
        row = con.execute(
            "SELECT state_json,revision FROM sitngo_games WHERE event_id=?",
            (eid,),
        ).fetchone()
    persisted = json.loads(row["state_json"])
    require(int(persisted["_revision"]) == int(row["revision"]), "restored state/database revision diverged")
    require(int(row["revision"]) <= corrupt_revision, "recovery advanced a corrupt revision instead of restoring a snapshot")

    # Retention remains bounded even if many meaningful generations exist.
    probe = dict(restored)
    for index in range(sitngo_resilience.KEEP_PER_EVENT + 7):
        probe = json.loads(json.dumps(probe))
        probe["_resilience_test_marker"] = f"generation-{index}"
        sitngo_resilience.backup_state(db, probe)
    with db.connect() as con:
        kept = int(con.execute(
            "SELECT COUNT(*) c FROM sitngo_state_backups WHERE event_id=?",
            (eid,),
        ).fetchone()["c"])
        recovery_log = con.execute(
            "SELECT event_type FROM ops_error_log WHERE event_type='sitngo_state_auto_restore' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    require(kept <= sitngo_resilience.KEEP_PER_EVENT, "Sit&Go backup retention exceeded its bound")
    require(recovery_log is not None, "automatic recovery was not recorded operationally")

    print("JJ_SITNGO_RESILIENCE_OK")


if __name__ == "__main__":
    main()
