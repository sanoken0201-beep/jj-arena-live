"""Sit&Go full-history offline MDA safety/denominator fixture."""
from __future__ import annotations

import json
import sqlite3

from mda_sitngo_offline_audit import _private_rfi_from_snapshot, audit_all_sitngo_players


def _state(idx=0, size=6, *, btn_open=True, cards=None):
    by_size = {
        2: ("BTN/SB", "BB"),
        3: ("BTN", "SB", "BB"),
        4: ("BTN", "SB", "BB", "CO"),
        5: ("BTN", "SB", "BB", "UTG", "CO"),
        6: ("BTN", "SB", "BB", "UTG", "HJ", "CO"),
    }
    positions = by_size[size]
    players = [
        {
            "seat": n, "user_id": (idx + n) % 12 + 1,
            "name": f"Member_{(idx + n) % 12 + 1}",
            "cards": cards or (["Ks", "5d"] if size == 6 else ["Ac", "2d"]),
        }
        for n in range(size)
    ]
    starts = {str(p["user_id"]): 20000 for p in players}
    first = "BTN/SB" if size == 2 else "BTN"
    action_order = [p for p in ("UTG", "HJ", "CO", first, "SB", "BB") if p in positions]
    name_by_position = {positions[n]: players[n]["name"] for n in range(size)}
    log = [f"Hand #{idx} started"]
    for pos in action_order:
        if pos == first and btn_open:
            log.append(f"{name_by_position[pos]} raises to 2 bb")
        else:
            log.append(f"{name_by_position[pos]} folds")
    return {
        "id": f"sng-game-{idx % 20}", "max_seats": 6, "button_seat": 0,
        "tournament": {"event_id": f"sng-game-{idx % 20}"},
        "seats": players,
        "hand": {
            "id": f"sng:{size}:{idx}", "phase": "complete",
            "starting_stacks": starts, "log": log, "board": [],
        },
    }


def _db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        """CREATE TABLE sitngo_hands(
             hand_id TEXT PRIMARY KEY,event_id TEXT,
             state_json TEXT,created_at TEXT)"""
    )
    return db


def _save(db, state):
    db.execute(
        "INSERT INTO sitngo_hands VALUES(?,?,?,?)",
        (state["hand"]["id"], state["id"], json.dumps(state), "2026-10-15T09:00:00Z"),
    )


def run():
    s = _state()
    ev, size, error = _private_rfi_from_snapshot(
        s, expected_hand_id=s["hand"]["id"], expected_event_id=s["id"]
    )
    assert error is None and size == 6
    assert [(e.position, e.holding, e.opened) for e in ev] == [
        ("UTG", "K5o", False), ("HJ", "K5o", False),
        ("CO", "K5o", False), ("BTN", "K5o", True),
    ]

    hu = _state(size=2)
    ev, size, error = _private_rfi_from_snapshot(hu)
    assert (size, error) == (2, None)
    assert [(e.position, e.opened) for e in ev] == [("BTN/SB", True)]

    # A limp or all-in for chips closes RFI; never call these an observed raise.
    limp = _state()
    limp["hand"]["log"][1] = limp["seats"][3]["name"] + " calls 1 bb"
    ev, _, error = _private_rfi_from_snapshot(limp)
    assert error is None
    assert len(ev) == 1 and not ev[0].opened

    # On name collision or unexplained action, exclude the entire hand, not
    # guessed opponent actions and inferred ranger.
    dupe = _state()
    dupe["seats"][1]["name"] = dupe["seats"][0]["name"]
    assert _private_rfi_from_snapshot(dupe)[2] == "ambiguous_player_names"
    unknown = _state()
    unknown["hand"]["log"][2] = "Player unknown action ???"
    assert _private_rfi_from_snapshot(unknown)[2] == "unknown_or_ambiguous_log_action"
    not_complete = _state()
    not_complete["hand"]["phase"] = "flop"
    assert _private_rfi_from_snapshot(not_complete)[2] == "not_complete"
    missing_cards = _state(cards=[])
    missing_cards["seats"][0]["cards"] = []
    ev, _, error = _private_rfi_from_snapshot(missing_cards)
    assert error is None
    assert all(e.position != "BTN" for e in ev)
    assert _private_rfi_from_snapshot(s, expected_event_id="another-event")[2] == "event_mismatch"

    db = _db()
    try:
        for i in range(120):
            _save(db, _state(i, size=6))
            _save(db, _state(i + 1000, size=2))
        weird = _state(9999, size=6)
        weird["hand"]["log"] = ["Malformed"]
        _save(db, weird)
        results = audit_all_sitngo_players(db, batch_size=23)
        coverage = results["coverage"]
        assert coverage["complete_scan"] and coverage["hands_examined"] == 241
        assert coverage["hands_accepted"] == 240
        assert coverage["hands_rejected"] == 1
        assert coverage["rejection_reasons"]["invalid_start_marker"] == 1
        assert coverage["unique_players"] == 12
        assert results["user_role_filter"] == "none"
        six = results["cohorts_by_players_dealt_in"]["6"]["positions"]["BTN"]["rfi_range"]
        two = results["cohorts_by_players_dealt_in"]["2"]["positions"]["BTN/SB"]["rfi_range"]
        assert six["cells"]["K5o"]["open_frequency"] == 100.0
        assert two["cells"]["A2o"]["open_frequency"] == 100.0
        assert "K5o+" in [h["notation"] for h in six["hypotheses"]]
        assert two["cells"]["K5o"]["status"] == "unknown"
        assert coverage["eligible_rfi_opportunities_with_cards"] >= 240
        raw = json.dumps(results)
        for secret in ("Member_", '"user_id"', '"actor_id"', '"hand_id"', '"Ks"', '"5d"', "sng:6:"):
            assert secret not in raw, secret

        # Recompute in a new read-only pass; a previously 100% range can fall.
        for i in range(120, 240):
            _save(db, _state(i + 2000, size=6, btn_open=False))
        new = audit_all_sitngo_players(db, batch_size=19)
        btn = new["cohorts_by_players_dealt_in"]["6"]["positions"]["BTN"]["rfi_range"]["cells"]["K5o"]
        assert btn["opportunities"] == 240
        assert btn["open_frequency"] == 50.0
        partial = audit_all_sitngo_players(db, max_hands=50, batch_size=13)
        assert partial["coverage"]["scope"] == "bounded_partial_scan"
        assert not partial["coverage"]["complete_scan"]
        assert partial["coverage"]["hands_examined"] == 50
    finally:
        db.close()

    # A REAL canonical-engine completed snapshot has these log and identity
    # contracts; in case of a mismatch do not silently invent eligible RFI.
    from sitngo_runtime import make_engine
    engine = make_engine()
    state = engine.blank_table_state(
        table_id="sng-real", name="real", max_seats=6,
        small_blind=100, big_blind=200, min_buyin=10000, max_buyin=10000,
    )
    for uid, seat in [(1, 0), (2, 1), (3, 2)]:
        engine.seat_player(state, user_id=uid, name=f"Real_{uid}", seat=seat, stack=10000)
    state["tournament"] = {"event_id": "sng-real", "bb_ante": 200}
    engine.start_hand(state)
    for _ in range(10):
        if state["hand"]["phase"] == "complete":
            break
        acting = next(
            p for p in state["seats"] if p["seat"] == state["hand"]["action_seat"]
        )
        engine.apply_action(state, acting["user_id"], "fold")
    assert state["hand"]["phase"] == "complete"
    evidence, actual_size, error = _private_rfi_from_snapshot(
        state, expected_hand_id=state["hand"]["id"], expected_event_id="sng-real"
    )
    assert error is None, error
    assert actual_size == 3
    assert evidence
    assert all(not e.opened for e in evidence)
    print("smoke_test_mda_sitngo_ingest: PASS")


if __name__ == "__main__":
    run()
