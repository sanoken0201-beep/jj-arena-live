"""Ensure one survivor does not close an advertised late-registration window."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from smoke_test_sitngo_entry_rules import fake_bust, fold_to_waiting
from smoke_test_sitngo_phase1 import add_member, production_app, registration_moment, require, sitngo


def main() -> None:
    service = production_app.app.state.jj_sitngo
    runtime = service.runtime
    db = production_app.db
    with db.connect() as con:
        admin_id = int(con.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()["id"])
    users = [add_member(900 + i) for i in range(3)]
    now = datetime.now(timezone.utc)
    start = now + timedelta(minutes=10)
    event = service.create_event(
        sitngo.SitNGoCreateIn(
            name="Late window survives early HU finish",
            starts_at=start.isoformat(),
            late_registration_minutes=10,
            max_reentries=0,
        ),
        admin_id,
    )
    with patch.object(sitngo, "_utcnow", return_value=registration_moment(event)):
        service.register(event["id"], users[0])
        service.register(event["id"], users[1])
    service.reconcile(start + timedelta(seconds=1))
    fold_to_waiting(runtime, event["id"])
    fake_bust(runtime, event["id"], users[0], "early-finish")
    state = runtime.load(event["id"])
    tournament = state["tournament"]
    require(tournament["status"] == "running", "tournament finalized while late registration was still open")
    require(not state["session_active"], "one-survivor table must wait for late entrant")
    require(
        abs(float(tournament["reentry_grace_until_epoch"]) - float(tournament["entry_window_deadline_epoch"])) < 0.01,
        "early finish did not wait until the configured late-registration deadline",
    )
    with patch.object(sitngo, "_utcnow", return_value=start + timedelta(minutes=2)):
        pending = service.register(event["id"], users[2])
    require(pending["entry_pending"], "late entrant could not join the waiting one-survivor tournament")
    asyncio.run(runtime.tick(event["id"], now=time.time()))
    state = runtime.load(event["id"])
    require(any(int(p["user_id"]) == users[2] for p in state["seats"]), "queued late entrant was not activated immediately")
    require(state["session_active"], "tournament did not resume after late entrant activation")
    require("reentry_grace_until_epoch" not in state["tournament"], "finish-wait marker survived tournament resume")

    with db.connect() as con:
        con.execute("UPDATE sitngo_events SET status='finished',updated_at=? WHERE id=?", (db.utcnow(), event["id"]))
        con.execute("UPDATE sitngo_registrations SET status='finished' WHERE event_id=? AND status<>'cancelled'", (event["id"],))

    print("JJ_SITNGO_ENTRY_FINISH_OK")


if __name__ == "__main__":
    main()
