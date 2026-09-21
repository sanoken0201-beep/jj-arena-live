from __future__ import annotations

from pathlib import Path

import poker_timebank
from sitngo_runtime import make_engine

ROOT = Path(__file__).resolve().parent


def actor(state):
    seat = (state.get("hand") or {}).get("action_seat")
    return next(player for player in state["seats"] if player["seat"] == seat)


def main() -> None:
    assert poker_timebank.ACTION_SECONDS == 30
    assert poker_timebank.TIME_BANK_CARDS == 3

    engine = make_engine()
    state = engine.blank_table_state(
        table_id="timebank-test",
        name="Timebank Test",
        max_seats=6,
        small_blind=50,
        big_blind=100,
        min_buyin=1000,
        max_buyin=20000,
    )
    engine.seat_player(state, user_id=1, name="A", seat=0, stack=5000)
    engine.seat_player(state, user_id=2, name="B", seat=1, stack=5000)
    engine.start_hand(state)

    first = actor(state)
    first_id = first["user_id"]
    assert "timebank_cards" not in first

    for expected in (2, 1, 0):
        now = 1_800_000_000.0 + expected
        outcome = poker_timebank.settle_expired_turn(
            state, engine, now_epoch=now
        )
        assert outcome == "timebank"
        current = actor(state)
        assert current["user_id"] == first_id
        assert current["timebank_cards"] == expected
        assert not current["folded"]
        deadline = poker_timebank._deadline_epoch(state["hand"])
        assert deadline is not None
        assert 29.9 <= deadline - now <= 30.1

    current = actor(state)
    state["hand"]["current_bet"] = current["round_bet"]
    assert engine.legal_actions(state, current["user_id"])["can_check"] is True

    outcome = poker_timebank.settle_expired_turn(
        state, engine, now_epoch=1_800_000_100.0
    )
    assert outcome == "fold"
    persisted = next(player for player in state["seats"] if player["user_id"] == first_id)
    assert persisted["timebank_cards"] == 0
    assert persisted["folded"] is True
    assert any(
        poker_timebank.FORCED_FOLD_LOG_SUFFIX in str(line)
        for line in (state.get("hand") or {}).get("log", [])
    )

    # Time-bank inventory belongs to the seating/tournament, not to one hand.
    if state["status"] != "playing":
        engine.start_hand(state)
        carried = next(player for player in state["seats"] if player["user_id"] == first_id)
        assert carried["timebank_cards"] == 0

    # A normal voluntary action never spends a card.
    acting = actor(state)
    acting["timebank_cards"] = 2
    before = acting["timebank_cards"]
    engine.apply_action(state, acting["user_id"], "fold")
    after = next(player for player in state["seats"] if player["user_id"] == acting["user_id"])
    assert after["timebank_cards"] == before

    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "poker_timebank.install(runtime_server, runtime_poker_engine, sitngo_runtime)" in app_source
    simple_source = (ROOT / "poker_simple.py").read_text(encoding="utf-8")
    assert "TIME BANK" in simple_source
    assert "timebank_cards" in simple_source

    print("POKER_TIMEBANK_OK", flush=True)


if __name__ == "__main__":
    main()
