"""Ensure a terminal HU bust gets a short re-entry decision window."""
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
    users = [add_member(950 + i) for i in range(2)]
    now = datetime.now(timezone.utc)
    start = now + timedelta(minutes=10)
    event = service.create_event(
        sitngo.SitNGoCreateIn(
            name="Terminal bust re-entry grace",
            starts_at=start.isoformat(),
            late_registration_minutes=10,
            max_reentries=1,
        ),
        admin_id,
    )
    with patch.object(sitngo, "_utcnow", return_value=registration_moment(event)):
        for uid in users:
            service.register(event["id"], uid)
    service.reconcile(start + timedelta(seconds=1))
    fold_to_waiting(runtime, event["id"])

    before = time.time()
    fake_bust(runtime, event["id"], users[0], "terminal-hu")
    state = runtime.load(event["id"])
    tournament = state["tournament"]
    require(tournament["status"] == "running", "HU winner finalized before re-entry decision window")
    require(not state["session_active"], "terminal HU table should pause during re-entry grace")
    grace = float(tournament.get("reentry_grace_until_epoch") or 0)
    require(before < grace <= before + 31, f"terminal re-entry grace is not approximately 30 seconds: {grace-before}")
    require(grace <= float(tournament["entry_window_deadline_epoch"]), "re-entry grace exceeded configured entry deadline")

    with patch.object(sitngo, "_utcnow", return_value=start + timedelta(minutes=2)):
        offer = service._event_payload(service._row(event["id"]), users[0])
        require(offer["can_reenter"], "newly busted HU player did not receive a re-entry offer")
        service.reenter(event["id"], users[0])
    asyncio.run(runtime.tick(event["id"], now=time.time()))
    state = runtime.load(event["id"])
    require(any(int(p["user_id"]) == users[0] and int(p["stack"]) > 0 for p in state["seats"]), "HU player did not re-enter")
    require(state["session_active"], "tournament did not resume after HU re-entry")
    require(all(int(x["user_id"]) != users[0] for x in state["tournament"]["results"]), "stale HU elimination survived re-entry")

    with db.connect() as con:
        con.execute("UPDATE sitngo_events SET status='finished',updated_at=? WHERE id=?", (db.utcnow(), event["id"]))
        con.execute("UPDATE sitngo_registrations SET status='finished' WHERE event_id=? AND status<>'cancelled'", (event["id"],))

    print("JJ_SITNGO_REENTRY_DEADLINE_OK")


if __name__ == "__main__":
    main()
