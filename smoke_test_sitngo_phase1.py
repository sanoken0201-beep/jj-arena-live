from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

# The release gate deliberately strips production secrets. Create a cheap local
# administrator before importing the production entrypoint so this test remains
# isolated from production and fast in CI/Render builds.
os.environ.setdefault("JJ_ADMIN_NAME", "シットゴーテスト")
os.environ["JJ_ADMIN_PIN"] = "123456"
os.environ["JJ_PBKDF2_ROUNDS"] = "1000"

from fastapi import HTTPException

import app as production_app
import sitngo


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def add_member(index: int) -> int:
    db = production_app.db
    name = f"テストプレイヤー{index}"
    with db.connect() as con:
        return db.insert_returning_id(
            con,
            "INSERT INTO users(name,email,password_hash,role,arena_chips,xp,approved,disabled,ranking_name,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                name,
                f"sitngo-test-{index}@jj.invalid",
                db.hash_password("111111"),
                "member",
                0,
                0,
                1,
                0,
                name,
                db.utcnow(),
            ),
        )


def registration_moment(event: dict) -> datetime:
    return datetime.fromisoformat(event["registration_opens_at"]) + timedelta(seconds=1)


def main() -> None:
    app = production_app.app
    db = production_app.db
    service = getattr(app.state, "jj_sitngo", None)
    require(service is not None, "Sit&Go service was not installed on production app")

    route_contract = {(getattr(r, "path", ""), tuple(sorted(getattr(r, "methods", None) or ()))) for r in app.router.routes}
    require(("/api/sitngo/next", ("GET",)) in route_contract, "player Sit&Go route missing")
    require(("/api/admin/sitngo", ("GET",)) in route_contract, "admin Sit&Go list route missing")
    require(("/api/admin/sitngo", ("POST",)) in route_contract, "admin Sit&Go create route missing")

    levels = sitngo.BLIND_STRUCTURE
    require(len(levels) == 15, "prepared default Sit&Go structure must contain 150 minutes")
    require(all(int(x["minutes"]) == 10 for x in levels), "legacy timing metadata must remain 10 minutes per default level")
    require(all(int(x["big_blind"]) == int(x["bb_ante"]) for x in levels), "default BB ante must equal BB")
    require(
        all(int(x[k]) % 100 == 0 for x in levels for k in ("small_blind", "big_blind", "bb_ante")),
        "Sit&Go chips/blinds must remain in 100-point units",
    )
    require(levels[0]["big_blind"] == 400 and levels[8]["big_blind"] == 10_000, "30k default structure drift")

    with db.connect() as con:
        admin = con.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()
    require(admin is not None, "isolated test admin was not created")
    admin_id = int(admin["id"])
    members = [add_member(i) for i in range(1, 10)]

    now = datetime.now(timezone.utc)
    starts = now + timedelta(minutes=30)
    event = service.create_event(
        sitngo.SitNGoCreateIn(name="JJ Sit&Go Phase 1", starts_at=starts.isoformat()),
        admin_id,
    )
    require(event["max_players"] == 6 and event["min_players"] == 2, "6-max/minimum-player contract drift")
    require(event["starting_stack"] == 30_000, "new default starting stack must be 30,000")
    require(event["structure"][0]["small_blind"] == 200 and event["structure"][0]["big_blind"] == 400, "event default structure not persisted")
    require(event["prepared_minutes"] == 150 and event["target_minutes"] == 90, "legacy timing metadata drift")
    open_at = datetime.fromisoformat(event["registration_opens_at"])
    require(open_at < starts, "registration must open before the event")

    # Simulate the actual registration window explicitly so the test remains
    # correct across JST midnight, where registration is never opened on the
    # preceding calendar date.
    with patch.object(sitngo, "_utcnow", return_value=registration_moment(event)):
        for order, uid in enumerate(members[:6], start=1):
            registered = service.register(event["id"], uid)
            require(registered["is_registered"], f"member {uid} registration not persisted")
            require(registered["registration_order"] == order, "registration must remain first-come-first-served")
        full = service._event_payload(service._row(event["id"]), members[0])
        require(full["participant_count"] == 6 and full["full"], "event must close at six registrations")
        try:
            service.register(event["id"], members[6])
        except HTTPException as exc:
            require(exc.status_code == 409, "seventh registration should be a conflict/full response")
        else:
            raise AssertionError("seventh registration was incorrectly accepted")

        cancelled = service.cancel_registration(event["id"], members[2])
        require(cancelled["participant_count"] == 5, "registration cancellation did not reopen one seat")
        replacement = service.register(event["id"], members[6])
        require(replacement["registration_order"] == 6, "replacement registration should become sixth active entrant")

    service.reconcile(starts + timedelta(seconds=1))
    running = service._event_payload(service._row(event["id"]), members[0], admin=True)
    require(running["status"] == "running", "2-6 entrants must auto-start at scheduled time")
    active = [p for p in running["participants"] if p["status"] == "active"]
    seats = [int(p["seat"]) for p in active]
    require(len(active) == 6, "all registered entrants must become active at start")
    require(len(set(seats)) == 6 and all(0 <= seat <= 5 for seat in seats), "random seats must be unique 6-max seats")
    table_state = service.runtime.load(event["id"])
    require(table_state["small_blind"] == 200 and table_state["big_blind"] == 400, "level 1 custom/default blinds must apply to the first hand")
    require(table_state["tournament"]["bb_ante"] == 400, "level 1 BBA must apply to the first hand")
    require(sum(p["stack"] + p["contributed"] for p in table_state["seats"]) + table_state.get("_ante_paid", 0) == 6 * 30_000, "30k chip conservation failed at launch")

    # A running tournament must not hide the next registration window. The next
    # due tournament still waits behind the single-running-Sit&Go guard.
    queued_start = now + timedelta(minutes=35)
    queued = service.create_event(
        sitngo.SitNGoCreateIn(name="Queued after running", starts_at=queued_start.isoformat()),
        admin_id,
    )
    with patch.object(sitngo, "_utcnow", return_value=registration_moment(queued)):
        service.register(queued["id"], members[7])
        service.register(queued["id"], members[8])
    with patch.object(sitngo, "_utcnow", return_value=registration_moment(queued)):
        lobby = service.next_event(members[7])
    require(lobby["event"]["id"] == event["id"], "running Sit&Go must remain the primary lobby event")
    require(lobby["upcoming"] and lobby["upcoming"]["id"] == queued["id"],
            "running Sit&Go hid the next registration event")

    service.reconcile(queued_start + timedelta(seconds=1))
    require(service._row(queued["id"])["status"] == "starting",
            "overdue queued Sit&Go must expose an explicit starting/wait state")

    # Release the single-running guard; the queued tournament may now start.
    with db.connect() as con:
        con.execute(
            "UPDATE sitngo_events SET status='finished',updated_at=? WHERE id=?",
            (db.utcnow(), event["id"]),
        )
    service.reconcile(queued_start + timedelta(seconds=2))
    require(service._row(queued["id"])["status"] == "running",
            "queued Sit&Go did not start after the previous tournament finished")
    with db.connect() as con:
        con.execute(
            "UPDATE sitngo_events SET status='finished',updated_at=? WHERE id=?",
            (db.utcnow(), queued["id"]),
        )

    short_start = now + timedelta(minutes=40)
    short = service.create_event(
        sitngo.SitNGoCreateIn(name="Minimum players check", starts_at=short_start.isoformat()),
        admin_id,
    )
    with patch.object(sitngo, "_utcnow", return_value=registration_moment(short)):
        service.register(short["id"], members[0])
    service.reconcile(short_start + timedelta(seconds=1))
    short_row = service._row(short["id"])
    require(short_row["status"] == "cancelled", "one-player event must auto-cancel at start")
    require(short_row["cancel_reason"] == "minimum_players_not_met", "auto-cancel reason drift")

    editable_start = now + timedelta(hours=2)
    custom_structure = [
        {"small_blind": 300, "big_blind": 600, "bb_ante": 600, "minutes": 8},
        {"small_blind": 500, "big_blind": 1_000, "bb_ante": 1_000, "minutes": 12},
        {"small_blind": 1_000, "big_blind": 2_000, "bb_ante": 2_000, "minutes": 15},
    ]
    editable = service.create_event(
        sitngo.SitNGoCreateIn(name="Editable", starts_at=editable_start.isoformat(), starting_stack=45_000, structure=custom_structure),
        admin_id,
    )
    require(editable["starting_stack"] == 45_000, "custom starting stack was not persisted")
    require([x["minutes"] for x in editable["structure"]] == [8, 12, 15], "legacy custom level-duration metadata was not persisted")
    require(editable["prepared_minutes"] == 35 and editable["target_minutes"] == 35, "legacy custom timing metadata must derive from structure")
    moved = editable_start + timedelta(minutes=20)
    edited_structure = [
        {"small_blind": 400, "big_blind": 800, "bb_ante": 800, "minutes": 7},
        {"small_blind": 800, "big_blind": 1_600, "bb_ante": 1_600, "minutes": 9},
    ]
    edited = service.update_event(
        editable["id"],
        sitngo.SitNGoUpdateIn(name="Edited Sit&Go", starts_at=moved.isoformat(), starting_stack=50_000, structure=edited_structure),
        admin_id,
    )
    require(edited["name"] == "Edited Sit&Go", "admin rename failed")
    require(abs((datetime.fromisoformat(edited["starts_at"]) - moved).total_seconds()) < 1, "admin reschedule failed")
    require(edited["starting_stack"] == 50_000 and edited["structure"][0]["big_blind"] == 800, "admin tournament settings update failed")
    require(edited["config_editable"], "pre-start event must report editable configuration")

    with patch.object(sitngo, "_utcnow", return_value=registration_moment(edited)):
        service.register(editable["id"], members[0])
        service.register(editable["id"], members[1])
    service.reconcile(moved + timedelta(seconds=1))
    locked = service._event_payload(service._row(editable["id"]), admin_id, admin=True)
    require(not locked["config_editable"], "running event must report locked configuration")
    custom_state = service.runtime.load(editable["id"])
    require(custom_state["small_blind"] == 400 and custom_state["big_blind"] == 800, "edited level-1 blinds were not applied to the first hand")
    require(custom_state["tournament"]["bb_ante"] == 800, "edited level-1 BBA was not applied to the first hand")
    try:
        service.update_event(editable["id"], sitngo.SitNGoUpdateIn(starting_stack=60_000), admin_id)
    except HTTPException as exc:
        require(exc.status_code == 400, "running event settings must be rejected")
    else:
        raise AssertionError("running event settings were incorrectly editable")

    # Keep shared CI databases reusable for the following full-game regression.
    # This changes only disposable test rows; production never executes this test.
    with db.connect() as con:
        con.execute(
            "UPDATE sitngo_events SET status='finished',updated_at=? WHERE id=?",
            (db.utcnow(), editable["id"]),
        )

    index = production_app._patched_index()
    js = production_app._patched_app_js()
    css = production_app._patched_styles()
    require('id="sitngoPanel"' in index and 'data-play-mode="sitngo"' in index, "player Sit&Go panel missing")
    require(sitngo_ui_marker() in js, "player Sit&Go JavaScript marker missing")
    require(sitngo_ui_marker() in css, "player Sit&Go CSS marker missing")
    require("10,000点" not in js and "12 HAND LEVELS" in index and "12ハンド/レベル" in js, "player Sit&Go 12-hand structure copy missing")

    print("JJ_SITNGO_PHASE1_OK")


def sitngo_ui_marker() -> str:
    # Keep the test independent from implementation details beyond the stable marker.
    return "jj sitngo phase1 ui 2026-09-15"


if __name__ == "__main__":
    main()
