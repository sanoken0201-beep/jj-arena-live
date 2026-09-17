"""Ensure an earlier busted player keeps re-entry rights until the entry deadline."""
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
    users = [add_member(950 + i) for i in range(6)]
    now = datetime.now(timezone.utc)
    start = now + timedelta(minutes=10)
    event = service.create_event(
        sitngo.SitNGoCreateIn(
            name="Earlier bust keeps re-entry right",
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

    # Bust player 0 first, then continue reducing the field without using that
    # player's still-valid re-entry. When one survivor remains, all six unique
    # seats have been consumed so only the preserved re-entry right can keep the
    # tournament open.
    for index, uid in enumerate(users[:5]):
        fake_bust(runtime, event["id"], uid, f"reentry-deadline-{index}")
    state = runtime.load(event["id"])
    tournament = state["tournament"]
    require(tournament["entrants"] == 6, "fixture must consume all six unique seats")
    require(tournament["status"] == "running", "tournament finalized while an earlier re-entry right remained")
    require(not state["session_active"], "single survivor should wait for a valid re-entry right")
    require(
        abs(float(tournament["reentry_grace_until_epoch"]) - float(tournament["entry_window_deadline_epoch"])) < 0.01,
        "valid re-entry right was not preserved through the configured deadline",
    )

    with patch.object(sitngo, "_utcnow", return_value=start + timedelta(minutes=2)):
        offer = service._event_payload(service._row(event["id"]), users[0])
        require(offer["can_reenter"], "earlier busted player lost re-entry offer before deadline")
        service.reenter(event["id"], users[0])
    asyncio.run(runtime.tick(event["id"], now=time.time()))
    state = runtime.load(event["id"])
    require(any(int(p["user_id"]) == users[0] and int(p["stack"]) > 0 for p in state["seats"]), "earlier busted player did not re-enter")
    require(state["session_active"], "tournament did not resume after preserved re-entry")
    require(all(int(x["user_id"]) != users[0] for x in state["tournament"]["results"]), "stale earlier elimination survived re-entry")

    with db.connect() as con:
        con.execute("UPDATE sitngo_events SET status='finished',updated_at=? WHERE id=?", (db.utcnow(), event["id"]))
        con.execute("UPDATE sitngo_registrations SET status='finished' WHERE event_id=? AND status<>'cancelled'", (event["id"],))

    print("JJ_SITNGO_REENTRY_DEADLINE_OK")


if __name__ == "__main__":
    main()
