"""Regression for Ring BB-to-next-BB inactivity eviction."""

import os
import tempfile
from pathlib import Path

os.environ.pop("DATABASE_URL", None)
os.environ["JJ_DB_PATH"] = tempfile.mkdtemp(prefix="jj-ring-inactivity-") + "/test.db"
os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"

import app as production
import ring_inactivity_eviction as inactivity


def player(uid: int, seat: int, name: str) -> dict:
    return {
        "user_id": uid,
        "name": name,
        "seat": seat,
        "stack": 1500,
        "in_hand": True,
        "folded": False,
        "all_in": False,
        "round_bet": 0,
        "contributed": 0,
        "cards": ["As", "Kd"],
        "ready": False,
        "sitting_out": False,
        "sit_out_next": False,
    }


def state_for(uid: int = 2) -> dict:
    return {
        "id": "jj-table-a",
        "name": "audit",
        "max_seats": 6,
        "small_blind": 5,
        "big_blind": 10,
        "min_buyin": 500,
        "max_buyin": 5000,
        "status": "playing",
        "session_active": True,
        "next_hand_at_epoch": None,
        "button_seat": 0,
        "seats": [
            player(1, 0, "A"),
            player(uid, 1, "B"),
            player(3, 2, "C"),
        ],
        "hand": {
            "id": "h1",
            "phase": "preflop",
            "big_blind_seat": 1,
            "small_blind_seat": 0,
            "action_seat": 2,
            "acted": [],
            "log": [],
            "board": [],
        },
    }


def finish(state: dict) -> None:
    state["status"] = "waiting"
    state["hand"]["phase"] = "complete"
    state["hand"]["action_seat"] = None
    for p in state["seats"]:
        p["in_hand"] = False


def next_bb(state: dict, hand_id: str) -> None:
    state["status"] = "playing"
    state["hand"] = {
        "id": hand_id,
        "phase": "preflop",
        "big_blind_seat": 1,
        "small_blind_seat": 0,
        "action_seat": 2,
        "acted": [],
        "log": [],
        "board": [],
    }
    for p in state["seats"]:
        p["in_hand"] = True
    inactivity.on_hand_started(state)


def main() -> None:
    s = production.runtime_server
    e = production.runtime_poker_engine
    assert getattr(s, "_jj_ring_inactivity_eviction_installed", False)

    # No accepted manual action from one BB through the end of the next BB hand:
    # the seat is removed only after that second BB hand completes.
    state = state_for()
    inactivity.on_hand_started(state)
    assert len(state["seats"]) == 3
    next_bb(state, "h2")
    assert len(state["seats"]) == 3
    finish(state)
    removed = inactivity.finalize_inactive_removals(state)
    assert removed == [2]
    assert [p["user_id"] for p in state["seats"]] == [1, 3]

    # A successful action anywhere between the two BB checkpoints starts a new
    # window; the second BB is not enough to eject the player.
    state = state_for()
    inactivity.on_hand_started(state)
    inactivity.record_manual_action(state, 2)
    next_bb(state, "h2")
    finish(state)
    assert inactivity.finalize_inactive_removals(state) == []
    assert any(p["user_id"] == 2 for p in state["seats"])

    # Even when the player reaches the second BB with no prior action, acting
    # during that BB hand cancels the pending end-of-hand removal.
    state = state_for()
    inactivity.on_hand_started(state)
    next_bb(state, "h2")
    inactivity.record_manual_action(state, 2)
    finish(state)
    assert inactivity.finalize_inactive_removals(state) == []
    assert any(p["user_id"] == 2 for p in state["seats"])

    # Internal counters are persisted server-side but never exposed in public
    # player/spectator state.
    state = state_for()
    inactivity.on_hand_started(state)
    public = e.public_state(state, 1)
    seat = next(p for p in public["seats"] if p["user_id"] == 2)
    assert not any(key.startswith("_jj_inactivity_") for key in seat)

    # Only the accepted manual HTTP action path may increment the activity
    # counter. Timeout/timebank engine calls intentionally bypass this hook.
    safety_source = Path("ring_action_safety.py").read_text(encoding="utf-8")
    assert "ring_inactivity_eviction.record_manual_action(state,user['id'])" in safety_source

    print("JJ_RING_INACTIVITY_EVICTION_OK bb-window/manual-only/end-of-hand")


if __name__ == "__main__":
    main()
