"""Ensure terminal re-entry grace is short and limited to the latest bust."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import HTTPException

from smoke_test_sitngo_entry_rules import fake_bust, fold_to_waiting
from smoke_test_sitngo_phase1 import add_member, production_app, registration_moment, require, sitngo


def main() -> None:
    service = production_app.app.state.jj_sitngo
    runtime = service.runtime
    db = production_app.db
    with db.connect() as con:
        admin_id = int(con.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()["id"])
    users = [add_member(950 + i) for i in range(3)]
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

    # First bust occurs while two players remain, so the earlier player may still
    # re-enter while the tournament naturally continues.
    fake_bust(runtime, event["id"], users[0], "earlier-bust")
    with patch.object(sitngo, "_utcnow", return_value=start + timedelta(minutes=1)):
        earlier_offer = service._event_payload(service._row(event["id"]), users[0])
        require(earlier_offer["can_reenter"], "earlier bust unexpectedly lost normal re-entry right")

    # The second bust would end heads-up. Only this newly busted player receives
    # the short terminal grace; the older elimination may not use it to revive
    # the tournament indefinitely.
    before = time.time()
    fake_bust(runtime, event["id"], users[1], "terminal-hu")
    state = runtime.load(event["id"])
    tournament = state["tournament"]
    require(tournament["status"] == "running", "HU winner finalized before re-entry decision window")
    require(not state["session_active"], "terminal HU table should pause during re-entry grace")
    grace = float(tournament.get("reentry_grace_until_epoch") or 0)
    require(before < grace <= before + 31, f"terminal re-entry grace is not approximately 30 seconds: {grace-before}")
    require(grace <= float(tournament["entry_window_deadline_epoch"]), "re-entry grace exceeded configured entry deadline")
    require(tournament.get("terminal_reentry_user_ids") == [users[1]], "terminal grace was not limited to the latest bust")

    with patch.object(sitngo, "_utcnow", return_value=start + timedelta(minutes=2)):
        old_offer = service._event_payload(service._row(event["id"]), users[0])
        new_offer = service._event_payload(service._row(event["id"]), users[1])
        require(not old_offer["can_reenter"], "earlier bust could re-enter during terminal grace")
        require(new_offer["can_reenter"], "newly busted HU player did not receive terminal re-entry offer")
        try:
            service.reenter(event["id"], users[0])
        except HTTPException as exc:
            require(exc.status_code == 409, "earlier-bust terminal rejection status drift")
        else:
            raise AssertionError("earlier bust used another player's terminal re-entry grace")
        service.reenter(event["id"], users[1])

    asyncio.run(runtime.tick(event["id"], now=time.time()))
    state = runtime.load(event["id"])
    require(any(int(p["user_id"]) == users[1] and int(p["stack"]) > 0 for p in state["seats"]), "HU player did not re-enter")
    require(state["session_active"], "tournament did not resume after HU re-entry")
    require(all(int(x["user_id"]) != users[1] for x in state["tournament"]["results"]), "stale HU elimination survived re-entry")

    with db.connect() as con:
        con.execute("UPDATE sitngo_events SET status='finished',updated_at=? WHERE id=?", (db.utcnow(), event["id"]))
        con.execute("UPDATE sitngo_registrations SET status='finished' WHERE event_id=? AND status<>'cancelled'", (event["id"],))

    print("JJ_SITNGO_REENTRY_DEADLINE_OK")


if __name__ == "__main__":
    main()
