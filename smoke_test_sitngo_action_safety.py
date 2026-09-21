"""Regression coverage for Sit&Go turn tokens and timeout-boundary races."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import sitngo_action_safety
import sitngo_observability
from smoke_test_sitngo_phase1 import add_member, production_app, registration_moment, sitngo
from fastapi.testclient import TestClient


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    db = production_app.db
    service = production_app.app.state.jj_sitngo
    runtime = service.runtime

    with db.connect() as con:
        con.execute("UPDATE sitngo_events SET status='finished',updated_at=? WHERE status='running'", (db.utcnow(),))
        con.execute("DELETE FROM sitngo_runtime_metrics")
        admin = con.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()
    require(admin is not None, "test admin missing")
    admin_id = int(admin["id"])
    members = [add_member(5600 + i) for i in range(3)]

    starts = datetime.now(timezone.utc) + timedelta(minutes=20)
    event = service.create_event(
        sitngo.SitNGoCreateIn(name="turn safety", starts_at=starts.isoformat()),
        admin_id,
    )
    with patch.object(sitngo, "_utcnow", return_value=registration_moment(event)):
        for uid in members:
            service.register(event["id"], uid)
    service.reconcile(starts + timedelta(seconds=1))
    eid = event["id"]

    client = TestClient(production_app.app, base_url="https://testserver")

    def login(uid: int) -> None:
        token = db.create_session(uid)
        client.headers["Authorization"] = "Bearer " + token
        client.cookies.set("jj_session", token)

    state = runtime.load(eid)
    public = runtime.public(state, members[0])
    turn_id = public.get("turn_id")
    require(bool(turn_id), "first actionable turn is missing turn_id")
    require(public["hand"].get("turn_id") == turn_id, "public hand/top-level turn_id mismatch")
    require(bool(public["hand"].get("action_deadline")), "turn deadline missing")

    player_js = production_app._patched_app_js()
    require(sitngo_action_safety.TURN_UI_MARKER in player_js, "browser action payload safety marker missing")
    require("body.action_id=" in player_js, "browser does not send action_id")
    require("body.hand_id=tableState.hand?.id" in player_js, "browser does not send hand_id")
    require("body.turn_id=tableState.turn_id" in player_js, "browser does not send turn_id")

    actor = next(p for p in state["seats"] if p["seat"] == state["hand"]["action_seat"])
    login(actor["user_id"])
    missing = client.post(
        f"/api/tables/{eid}/action",
        json={"action": "fold", "action_id": "turn-missing-1", "hand_id": state["hand"]["id"]},
    )
    require(missing.status_code == 409, "missing turn_id must be rejected")

    first_body = {
        "action": "fold",
        "action_id": "turn-valid-0001",
        "hand_id": state["hand"]["id"],
        "turn_id": turn_id,
    }
    first = client.post(f"/api/tables/{eid}/action", json=first_body)
    require(first.status_code == 200, f"valid current-turn action failed: {first.text}")
    after_first = first.json()
    require(after_first.get("turn_id") and after_first["turn_id"] != turn_id, "next actor did not receive a fresh turn_id")

    # Exact request replay is idempotent even though its turn_id is now stale.
    repeat = client.post(f"/api/tables/{eid}/action", json=first_body)
    require(repeat.status_code == 200, "idempotent replay must return current state")
    require(repeat.json().get("turn_id") == after_first.get("turn_id"), "idempotent replay mutated the current turn")

    # A different receipt carrying the old token must never act on the next turn.
    stale = client.post(
        f"/api/tables/{eid}/action",
        json={**first_body, "action_id": "turn-stale-0002"},
    )
    require(stale.status_code == 409, "stale turn_id must be rejected")

    # Move the active deadline into the past and model a request that reached the
    # server just before that deadline but is still waiting on the table lock.
    state = runtime.load(eid)
    current_turn = state["hand"]["turn_id"]
    current_actor = next(p for p in state["seats"] if p["seat"] == state["hand"]["action_seat"])
    deadline = time.time() - 1.0
    state["hand"]["action_deadline"] = datetime.fromtimestamp(deadline, timezone.utc).isoformat()
    runtime.save(state)
    before_log = list(state["hand"].get("log") or [])
    before_seat = state["hand"]["action_seat"]

    pending_key = (eid, current_turn)
    runtime._pending_action_arrivals[pending_key] = {"earliest": deadline - 0.01, "count": 1}
    asyncio.run(
        runtime.tick(
            eid,
            now=deadline + sitngo_action_safety.TIMEOUT_SETTLEMENT_GRACE_SECONDS + 0.1,
        )
    )
    protected = runtime.load(eid)
    require(protected["hand"].get("turn_id") == current_turn, "pre-deadline pending action lost its turn")
    require(protected["hand"].get("action_seat") == before_seat, "timeout acted while a timely request was pending")
    require(list(protected["hand"].get("log") or []) == before_log, "protected timeout mutated the hand")
    runtime._pending_action_arrivals.pop(pending_key, None)

    # A request that reaches the server after the same deadline is rejected, not
    # granted the settlement grace. The scheduler then performs the timeout.
    login(current_actor["user_id"])
    late = client.post(
        f"/api/tables/{eid}/action",
        json={
            "action": "fold",
            "action_id": "turn-late-0003",
            "hand_id": protected["hand"]["id"],
            "turn_id": current_turn,
        },
    )
    require(late.status_code == 409, "post-deadline user action must be rejected")
    still = runtime.load(eid)
    require(still["hand"].get("turn_id") == current_turn, "late rejected request mutated the turn")

    asyncio.run(
        runtime.tick(
            eid,
            now=deadline + sitngo_action_safety.TIMEOUT_SETTLEMENT_GRACE_SECONDS + 1.0,
        )
    )
    timed_out = runtime.load(eid)
    require(timed_out.get("status") == "playing", "first timeout unexpectedly ended the hand")
    require(timed_out["hand"].get("turn_id") == current_turn, "time bank must keep the same decision turn")
    timed_actor = next(p for p in timed_out["seats"] if p["seat"] == timed_out["hand"]["action_seat"])
    require(int(timed_actor.get("timebank_cards", -1)) == 2, "first timeout did not consume exactly one time-bank card")

    for remaining in (1, 0):
        bank_deadline = datetime.fromisoformat(timed_out["hand"]["action_deadline"]).timestamp()
        asyncio.run(
            runtime.tick(
                eid,
                now=bank_deadline + sitngo_action_safety.TIMEOUT_SETTLEMENT_GRACE_SECONDS + 1.0,
            )
        )
        timed_out = runtime.load(eid)
        require(timed_out.get("status") == "playing", "time-bank extension unexpectedly ended the hand")
        require(timed_out["hand"].get("turn_id") == current_turn, "time-bank extension changed the decision turn")
        timed_actor = next(p for p in timed_out["seats"] if p["seat"] == timed_out["hand"]["action_seat"])
        require(int(timed_actor.get("timebank_cards", -1)) == remaining, "time-bank card count drifted")

    final_deadline = datetime.fromisoformat(timed_out["hand"]["action_deadline"]).timestamp()
    asyncio.run(
        runtime.tick(
            eid,
            now=final_deadline + sitngo_action_safety.TIMEOUT_SETTLEMENT_GRACE_SECONDS + 1.0,
        )
    )
    timed_out = runtime.load(eid)
    require(
        timed_out.get("status") != "playing" or timed_out["hand"].get("turn_id") != current_turn,
        "zero-card timeout did not force-fold the expired turn",
    )

    metrics=sitngo_observability.summary(db,days=7)["totals"]
    require(metrics["missing_tokens"] >= 1, "missing-token rejection was not observed")
    require(metrics["duplicate_action"] >= 1, "idempotent duplicate action was not observed")
    require(metrics["stale_turn"] >= 1, "stale turn rejection was not observed")
    require(metrics["late_action"] >= 1, "late action rejection was not observed")
    require(metrics["timeout_boundary_protected"] >= 1, "timeout boundary protection was not observed")
    require(metrics["timeout_auto_action"] >= 1, "automatic timeout action was not observed")

    login(admin_id)
    telemetry=client.get("/api/admin/sitngo/telemetry?days=7")
    require(telemetry.status_code == 200, "admin Sit&Go telemetry endpoint failed")
    require(telemetry.json()["privacy"]["stores_user_identity"] is False, "telemetry privacy contract drift")
    require(telemetry.json()["totals"]["duplicate_action"] >= 1, "admin telemetry lost aggregate metrics")
    require(telemetry.json()["alert_status"] in {"warning","critical","info"}, "admin telemetry alert status missing")
    require(isinstance(telemetry.json()["alerts"], list), "admin telemetry alert list missing")
    quiet=sitngo_observability.classify_alerts(
        {"missing_tokens":0,"stale_hand":0,"stale_turn":0,"restart_recovery":0,"duplicate_action":0,"timeout_boundary_protected":0},
        7,
    )
    require(quiet == [], "quiet telemetry produced an operator alert")
    warning=sitngo_observability.classify_alerts(
        {"missing_tokens":1,"stale_hand":2,"stale_turn":1,"restart_recovery":0,"duplicate_action":4,"timeout_boundary_protected":0},
        7,
    )
    require({a["code"] for a in warning} == {"missing_tokens","stale_action"}, "warning thresholds drifted")
    critical=sitngo_observability.classify_alerts(
        {"missing_tokens":5,"stale_hand":5,"stale_turn":5,"restart_recovery":0,"duplicate_action":0,"timeout_boundary_protected":0},
        7,
    )
    require(all(a["severity"]=="critical" for a in critical), "critical Sit&Go alert threshold drifted")
    require(
        not sitngo_observability.classify_alerts({"timeout_auto_action":999,"late_action":999},7),
        "normal player timeouts must not page operators",
    )

    # Ring action payloads and materialized core remain untouched; the safety
    # contract is selected only by the Sit&Go table id/state.
    ring = production_app.runtime_server.load_table("jj-table-a")
    require(not ring.get("tournament"), "ring table unexpectedly acquired tournament state")

    with db.connect() as con:
        con.execute(
            "UPDATE sitngo_events SET status='finished',updated_at=? WHERE id=?",
            (db.utcnow(), eid),
        )

    print("JJ_SITNGO_ACTION_SAFETY_OK")


if __name__ == "__main__":
    main()
