"""Regression coverage for Sit&Go late registration and re-entry."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import HTTPException

from smoke_test_sitngo_phase1 import add_member, production_app, registration_moment, require, sitngo


def fold_to_waiting(runtime, event_id: str) -> None:
    state = runtime.load(event_id)
    for _ in range(12):
        if state["status"] != "playing":
            break
        seat = state["hand"].get("action_seat")
        player = next(p for p in state["seats"] if p["seat"] == seat)
        legal = runtime.engine.legal_actions(state, player["user_id"])
        if legal.get("can_fold"):
            runtime.engine.apply_action(state, player["user_id"], "fold")
        elif legal.get("can_check"):
            runtime.engine.apply_action(state, player["user_id"], "check")
        else:
            runtime.engine.apply_action(state, player["user_id"], "call")
    require(state["status"] == "waiting", "test hand did not finish")
    runtime.save(state)


def fake_bust(runtime, event_id: str, user_id: int, hand_suffix: str) -> None:
    state = runtime.load(event_id)
    require(state["status"] == "waiting", "fake bust requires a between-hand state")
    target = next(p for p in state["seats"] if int(p["user_id"]) == int(user_id))
    require(int(target["stack"]) > 0, "target must have chips before fake bust")
    recipient = next(p for p in state["seats"] if int(p["user_id"]) != int(user_id) and int(p["stack"]) > 0)
    starting = {str(p["user_id"]): int(p["stack"]) for p in state["seats"]}
    recipient["stack"] += target["stack"]
    target["stack"] = 0
    target.update(in_hand=False, folded=False, all_in=False, round_bet=0, contributed=0, cards=[])
    state["hand"] = {
        "id": f"entry-rules-{hand_suffix}",
        "phase": "complete",
        "board": [],
        "action_seat": None,
        "starting_stacks": starting,
        "revealed_user_ids": [],
    }
    state.pop("_ranked_hand", None)
    state["status"] = "waiting"
    runtime.save(state)


def main() -> None:
    service = production_app.app.state.jj_sitngo
    runtime = service.runtime
    db = production_app.db
    with db.connect() as con:
        admin_id = int(con.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()["id"])
    users = [add_member(800 + i) for i in range(8)]
    now = datetime.now(timezone.utc)

    routes = {(getattr(r, "path", ""), tuple(sorted(getattr(r, "methods", None) or ()))) for r in production_app.app.router.routes}
    require(("/api/sitngo/{event_id}/reentry", ("POST",)) in routes, "re-entry API route missing")

    # Default remains the old freezeout contract.
    freeze_start = now + timedelta(minutes=15)
    freeze = service.create_event(sitngo.SitNGoCreateIn(name="Freezeout default", starts_at=freeze_start.isoformat()), admin_id)
    require(freeze["late_registration_minutes"] == 0 and freeze["max_reentries"] == 0, "default must remain freezeout")
    with patch.object(sitngo, "_utcnow", return_value=registration_moment(freeze)):
        service.register(freeze["id"], users[0])
        service.register(freeze["id"], users[1])
    service.reconcile(freeze_start + timedelta(seconds=1))
    with patch.object(sitngo, "_utcnow", return_value=freeze_start + timedelta(minutes=1)):
        try:
            service.register(freeze["id"], users[2])
        except HTTPException as exc:
            require(exc.status_code == 400, "freezeout late-registration rejection status drift")
        else:
            raise AssertionError("freezeout incorrectly accepted a late entrant")
    with db.connect() as con:
        con.execute("UPDATE sitngo_events SET status='finished',updated_at=? WHERE id=?", (db.utcnow(), freeze["id"]))

    # Enabled event: 20-minute late registration and one re-entry per player.
    start = now + timedelta(minutes=25)
    event = service.create_event(
        sitngo.SitNGoCreateIn(
            name="Late + reentry",
            starts_at=start.isoformat(),
            late_registration_minutes=20,
            max_reentries=1,
        ),
        admin_id,
    )
    require(event["late_registration_minutes"] == 20 and event["max_reentries"] == 1, "entry policy not persisted")
    with patch.object(sitngo, "_utcnow", return_value=registration_moment(event)):
        for uid in users[:3]:
            service.register(event["id"], uid)
    service.reconcile(start + timedelta(seconds=1))
    state = runtime.load(event["id"])
    require(state["tournament"]["entrants"] == 3 and state["tournament"]["total_entries"] == 3, "initial entry accounting drift")
    initial_deadline = state["tournament"]["entry_window_deadline_epoch"]

    # A late registrant may request entry during a live hand but cannot be seated mid-hand.
    late_now = start + timedelta(minutes=2)
    with patch.object(sitngo, "_utcnow", return_value=late_now):
        pending = service.register(event["id"], users[3])
    require(pending["entry_pending"], "late entrant must be queued during live hand")
    state = runtime.load(event["id"])
    require(all(int(p["user_id"]) != users[3] for p in state["seats"]), "late entrant was seated mid-hand")
    fold_to_waiting(runtime, event["id"])
    asyncio.run(runtime.tick(event["id"], now=time.time()))
    state = runtime.load(event["id"])
    require(any(int(p["user_id"]) == users[3] for p in state["seats"]), "late entrant was not seated between hands")
    require(state["tournament"]["entrants"] == 4 and state["tournament"]["total_entries"] == 4, "late-entry counters wrong")
    require(state["tournament"]["entry_window_deadline_epoch"] == initial_deadline, "late entry reset the blind/entry clock")
    with db.connect() as con:
        reg = con.execute("SELECT status FROM sitngo_registrations WHERE event_id=? AND user_id=?", (event["id"], users[3])).fetchone()
    require(reg["status"] == "active", "late entrant registration did not become active")

    # Bust one original player. Their place is based on the now four-player field.
    fake_bust(runtime, event["id"], users[0], "bust-a")
    state = runtime.load(event["id"])
    first_result = next(x for x in state["tournament"]["results"] if int(x["user_id"]) == users[0])
    require(first_result["place"] == 4, f"late entrant did not renumber prior field correctly: {first_result}")
    with patch.object(sitngo, "_utcnow", return_value=start + timedelta(minutes=3)):
        offer = service._event_payload(service._row(event["id"]), users[0])
        require(offer["can_reenter"], "busted player was not offered re-entry")
        service.reenter(event["id"], users[0])
    asyncio.run(runtime.tick(event["id"], now=time.time()))
    state = runtime.load(event["id"])
    player = next(p for p in state["seats"] if int(p["user_id"]) == users[0])
    require(player["stack"] == state["tournament"]["starting_stack"], "re-entry did not restore the full starting stack")
    require(all(int(x["user_id"]) != users[0] for x in state["tournament"]["results"]), "old elimination survived re-entry")
    require(state["tournament"]["total_entries"] == 5, "re-entry did not increment total entry count")
    require(state["tournament"]["entry_window_deadline_epoch"] == initial_deadline, "re-entry reset the tournament clock")
    with db.connect() as con:
        reg = con.execute("SELECT status,reentry_count FROM sitngo_registrations WHERE event_id=? AND user_id=?", (event["id"], users[0])).fetchone()
    require(reg["status"] == "active" and int(reg["reentry_count"]) == 1, "re-entry count/status not persisted")

    # A second bust may not exceed the configured one-re-entry cap.
    fake_bust(runtime, event["id"], users[0], "bust-a2")
    with patch.object(sitngo, "_utcnow", return_value=start + timedelta(minutes=4)):
        try:
            service.reenter(event["id"], users[0])
        except HTTPException as exc:
            require(exc.status_code == 409, "re-entry cap rejection status drift")
        else:
            raise AssertionError("second re-entry exceeded configured cap")

    # New unique late entrants stop at six total players; re-entry does not consume a unique-player slot.
    with patch.object(sitngo, "_utcnow", return_value=start + timedelta(minutes=5)):
        service.register(event["id"], users[4])
        service.register(event["id"], users[5])
        try:
            service.register(event["id"], users[6])
        except HTTPException as exc:
            require(exc.status_code == 409, "seventh unique entrant should be blocked")
        else:
            raise AssertionError("seventh unique entrant was accepted")

    # Entry window closes independently of tournament continuation.
    with patch.object(sitngo, "_utcnow", return_value=start + timedelta(minutes=21)):
        try:
            service.register(event["id"], users[6])
        except HTTPException as exc:
            require(exc.status_code == 400, "expired late-registration window should reject")
        else:
            raise AssertionError("expired late-registration window remained open")

    defaults = service.admin_events(admin_id)["defaults"]
    require(defaults["late_registration_minutes"] == 0 and defaults["max_reentries"] == 0, "admin defaults must preserve freezeout")
    js = production_app._patched_app_js()
    require("jj sitngo late registration reentry ui 2026-09-18" in js, "player late-reg/re-entry UI missing")
    require("data-sng-reentry" in js and "途中参加する" in js, "player entry actions missing")

    # Shared PostgreSQL CI runs the legacy full-game regression immediately
    # after this test. Leave no synthetic event in the single-running slot.
    with db.connect() as con:
        con.execute("UPDATE sitngo_events SET status='finished',updated_at=? WHERE id=?", (db.utcnow(), event["id"]))
        con.execute(
            "UPDATE sitngo_registrations SET status='finished' WHERE event_id=? AND status IN ('active','pending_late','pending_reentry')",
            (event["id"],),
        )

    print("JJ_SITNGO_ENTRY_RULES_OK")


if __name__ == "__main__":
    main()
