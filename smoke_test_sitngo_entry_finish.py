"""Ensure an unused late-registration slot never keeps a finished Sit&Go alive."""
from __future__ import annotations

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
            name="Unused late slot does not delay finish",
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
    require(tournament["status"] == "finished", "unused late-registration capacity kept the tournament alive")
    require(not state["session_active"], "finished one-survivor table remained active")
    require("reentry_grace_until_epoch" not in tournament, "freezeout finish created an unnecessary grace period")
    require(sum(1 for x in tournament["results"] if int(x.get("place") or 0) == 1) == 1, "winner was not finalized")

    # Once the tournament is over, a merely unused seat does not permit a new
    # entrant to revive it, even if the configured wall-clock window remains.
    with patch.object(sitngo, "_utcnow", return_value=start + timedelta(minutes=2)):
        try:
            service.register(event["id"], users[2])
        except Exception as exc:
            require("受付" in str(exc) or "終了" in str(exc), "late join after finish returned an unexpected error")
        else:
            raise AssertionError("late join revived a finished Sit&Go")

    print("JJ_SITNGO_ENTRY_FINISH_OK")


if __name__ == "__main__":
    main()
