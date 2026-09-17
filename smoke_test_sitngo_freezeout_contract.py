"""Regression contract: JJ Sit&Go is always freezeout with no late entry.

This test intentionally treats both rules as product invariants rather than
administrator options. A tournament field is frozen at the scheduled start;
once a player's stack reaches zero there is no re-entry path.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

if not os.environ.get("DATABASE_URL"):
    _tmp = tempfile.TemporaryDirectory(prefix="jj-sng-freezeout-")
    os.environ["JJ_DB_PATH"] = str(Path(_tmp.name) / "freezeout.sqlite3")

from fastapi import HTTPException

from smoke_test_sitngo_phase1 import (
    add_member,
    production_app,
    registration_moment,
    require,
    sitngo,
)


def main() -> None:
    app = production_app.app
    db = production_app.db
    service = app.state.jj_sitngo

    routes = {
        (getattr(route, "path", ""), tuple(sorted(getattr(route, "methods", None) or ())))
        for route in app.router.routes
    }
    require(
        not any(path == "/api/sitngo/{event_id}/reentry" for path, _ in routes),
        "Sit&Go must not expose a re-entry endpoint",
    )

    with db.connect() as con:
        admin_id = int(con.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()["id"])

    users = [add_member(1200 + index) for index in range(3)]
    now = datetime.now(timezone.utc)
    starts = now + timedelta(minutes=10)
    event = service.create_event(
        sitngo.SitNGoCreateIn(name="Freezeout contract", starts_at=starts.isoformat()),
        admin_id,
    )

    require(event.get("reentry") is False, "Sit&Go payload must explicitly advertise re-entry=false")

    with patch.object(sitngo, "_utcnow", return_value=registration_moment(event)):
        service.register(event["id"], users[0])
        service.register(event["id"], users[1])

    service.reconcile(starts + timedelta(seconds=1))
    running = service._event_payload(service._row(event["id"]), users[2])
    require(running["status"] == "running", "fixture tournament did not start")
    require(not running["can_register"], "registration must close exactly when Sit&Go starts")
    require(running.get("reentry") is False, "running Sit&Go must remain freezeout")

    with patch.object(sitngo, "_utcnow", return_value=starts + timedelta(minutes=1)):
        try:
            service.register(event["id"], users[2])
        except HTTPException as exc:
            require(exc.status_code == 400, "post-start registration must fail closed")
        else:
            raise AssertionError("post-start player was incorrectly accepted")

    # Even a player whose registration has become 'finished' must not be able to
    # use the ordinary registration path as a disguised re-entry.
    with db.connect() as con:
        con.execute(
            "UPDATE sitngo_registrations SET status='finished' WHERE event_id=? AND user_id=?",
            (event["id"], users[0]),
        )
    with patch.object(sitngo, "_utcnow", return_value=starts + timedelta(minutes=2)):
        try:
            service.register(event["id"], users[0])
        except HTTPException as exc:
            require(exc.status_code == 400, "finished player must not re-enter through register")
        else:
            raise AssertionError("finished player re-entered through the registration endpoint")

    with db.connect() as con:
        count = int(
            con.execute(
                "SELECT COUNT(*) n FROM sitngo_registrations WHERE event_id=?",
                (event["id"],),
            ).fetchone()["n"]
        )
        require(count == 2, "freezeout must never create an additional registration after start")
        con.execute(
            "UPDATE sitngo_events SET status='finished',updated_at=? WHERE id=?",
            (db.utcnow(), event["id"]),
        )

    print("JJ_SITNGO_FREEZEOUT_CONTRACT_OK")


if __name__ == "__main__":
    main()
