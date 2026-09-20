"""Operational acceptance: two independent member sessions share one Sit&Go safely."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.pop("DATABASE_URL", None)
_tmp = tempfile.TemporaryDirectory(prefix="jj-sng-multisession-")
os.environ["JJ_DB_PATH"] = str(Path(_tmp.name) / "multi.sqlite3")

from fastapi.testclient import TestClient
from smoke_test_sitngo_phase1 import add_member, production_app as prod, registration_moment, sitngo
from unittest.mock import patch


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def client_for(uid: int) -> TestClient:
    client = TestClient(prod.app, base_url="https://testserver")
    token = prod.db.create_session(uid)
    client.headers["Authorization"] = "Bearer " + token
    client.cookies.set("jj_session", token)
    return client


def main() -> None:
    service = prod.app.state.jj_sitngo
    with prod.db.connect() as con:
        admin = int(con.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()["id"])

    users = [add_member(6100 + i) for i in range(2)]
    starts = datetime.now(timezone.utc) + timedelta(minutes=10)
    event = service.create_event(
        sitngo.SitNGoCreateIn(name="multi-session acceptance", starts_at=starts.isoformat()),
        admin,
    )
    with patch.object(sitngo, "_utcnow", return_value=registration_moment(event)):
        for uid in users:
            service.register(event["id"], uid)
    service.reconcile(starts + timedelta(seconds=1))
    eid = event["id"]

    clients = {uid: client_for(uid) for uid in users}
    snapshots = {uid: clients[uid].get(f"/api/tables/{eid}").json()["state"] for uid in users}
    revisions = {int(s["_revision"]) for s in snapshots.values()}
    turns = {s["turn_id"] for s in snapshots.values()}
    require(len(revisions) == 1 and len(turns) == 1, "independent sessions did not converge on one authoritative state")

    state = snapshots[users[0]]
    actor = next(p for p in state["seats"] if p["seat"] == state["hand"]["action_seat"])
    actor_client = clients[int(actor["user_id"])]
    body = {
        "action": "fold",
        "action_id": "multi-device-action-1",
        "hand_id": state["hand"]["id"],
        "turn_id": state["turn_id"],
    }
    acted = actor_client.post(f"/api/tables/{eid}/action", json=body)
    require(acted.status_code == 200, f"first device action failed: {acted.text}")

    after = {uid: clients[uid].get(f"/api/tables/{eid}").json()["state"] for uid in users}
    after_revisions = {int(s["_revision"]) for s in after.values()}
    after_turns = {s["turn_id"] for s in after.values()}
    require(len(after_revisions) == 1, "two sessions observed different revisions after action")
    require(len(after_turns) == 1, "two sessions observed different turns after action")
    require(next(iter(after_revisions)) > next(iter(revisions)), "authoritative revision did not advance")
    require(next(iter(after_turns)) != state["turn_id"], "turn token did not advance after action")

    replay = actor_client.post(f"/api/tables/{eid}/action", json=body)
    require(replay.status_code == 200, "same-device retry must remain idempotent")
    replay_state = replay.json()
    require(int(replay_state["_revision"]) == next(iter(after_revisions)), "idempotent replay changed revision")

    current = after[users[0]]
    next_actor = next(p for p in current["seats"] if p["seat"] == current["hand"]["action_seat"])
    second_client = clients[int(next_actor["user_id"])]
    second_body = {
        "action": "fold",
        "action_id": "multi-device-action-2",
        "hand_id": current["hand"]["id"],
        "turn_id": current["turn_id"],
    }
    second = second_client.post(f"/api/tables/{eid}/action", json=second_body)
    require(second.status_code == 200, f"second device action failed: {second.text}")

    final_a = clients[users[0]].get(f"/api/tables/{eid}").json()["state"]
    final_b = clients[users[1]].get(f"/api/tables/{eid}").json()["state"]
    require(final_a["_revision"] == final_b["_revision"], "sessions diverged after second device action")
    require(final_a["hand"]["id"] == final_b["hand"]["id"], "sessions disagree on current hand")
    require(
        [p["stack"] for p in final_a["seats"]] == [p["stack"] for p in final_b["seats"]],
        "sessions disagree on tournament stacks",
    )

    for client in clients.values():
        client.close()
    print("JJ_SITNGO_MULTI_SESSION_OK")


if __name__ == "__main__":
    main()
