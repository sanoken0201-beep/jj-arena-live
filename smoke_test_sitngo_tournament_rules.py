"""Regression tests for tournament-only blind/button and betting rules."""
from __future__ import annotations

import sitngo_chip_rules
import sitngo_runtime
import sitngo_tournament_rules


# Installation order is intentional: tournament dealing replaces the cash-table
# hand starter, then chip rules wrap that tournament starter with color-up and
# denomination validation.
sitngo_tournament_rules.install(sitngo_runtime)
sitngo_chip_rules.install(sitngo_runtime)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def waiting_state(engine, stacks_by_seat, *, previous_button=0, previous_sb=1, previous_bb=2):
    state = engine.blank_table_state(
        table_id="tournament-rules",
        name="rules",
        max_seats=6,
        small_blind=100,
        big_blind=200,
        min_buyin=1,
        max_buyin=100_000,
    )
    for seat, stack in sorted(stacks_by_seat.items()):
        engine.seat_player(state, user_id=seat + 1, name=f"P{seat + 1}", seat=seat, stack=stack)
    state.update(
        status="waiting",
        button_seat=previous_button,
        hand_no=1,
        chip_unit=100,
        _ante_paid=0,
        tournament={
            "level": 1,
            "bb_ante": 200,
            "structure": [{"level": 1, "small_blind": 100, "big_blind": 200, "bb_ante": 200, "minutes": 10}],
            "starting_stack": 10_000,
            "entrants": len(stacks_by_seat),
            "total_chips": sum(stacks_by_seat.values()),
            "results": [],
            "status": "running",
        },
        hand={
            "id": "previous",
            "phase": "complete",
            "small_blind_seat": previous_sb,
            "big_blind_seat": previous_bb,
            "starting_stacks": {},
        },
    )
    return state


def positions(state):
    hand = state["hand"]
    return state["button_seat"], hand["small_blind_seat"], hand["big_blind_seat"]


def test_dead_button(engine):
    # Previous layout: BTN 0 / SB 1 / BB 2.
    # If the SB busts, its empty seat becomes the dead button; prior BB becomes
    # SB and the BB advances to the next live player.
    sb_bust = waiting_state(engine, {0: 10_000, 1: 0, 2: 10_000, 3: 10_000, 4: 10_000})
    engine.start_hand(sb_bust)
    require(positions(sb_bust) == (1, 2, 3), f"SB-bust dead button wrong: {positions(sb_bust)}")
    require(sb_bust["hand"]["button_dead"], "busted SB seat should hold the dead button")

    # If the previous BB busts, the old BB position is the dead SB.  The next
    # live player must post the BB; nobody is promoted into an artificial SB.
    bb_bust = waiting_state(engine, {0: 10_000, 1: 10_000, 2: 0, 3: 10_000, 4: 10_000})
    engine.start_hand(bb_bust)
    require(positions(bb_bust) == (1, 2, 3), f"BB-bust dead blind wrong: {positions(bb_bust)}")
    require(bb_bust["hand"]["small_blind_dead"], "busted BB position should be a dead SB")
    require(next(p for p in bb_bust["seats"] if p["seat"] == 3)["round_bet"] == 200, "next live player did not post BB")
    require(all(p["round_bet"] == 0 for p in bb_bust["seats"] if p["seat"] != 3), "a live SB was incorrectly invented")

    # If the next physical seat after the BB is empty, BB skips the empty seat,
    # but the previous BB still becomes SB and the previous SB becomes button.
    utg_bust = waiting_state(engine, {0: 10_000, 1: 10_000, 2: 10_000, 3: 0, 4: 10_000})
    engine.start_hand(utg_bust)
    require(positions(utg_bust) == (1, 2, 4), f"BB did not skip empty UTG correctly: {positions(utg_bust)}")


def test_three_to_heads_up(engine):
    # Previous three-handed layout is BTN 0 / SB 1 / BB 2.  Test every possible
    # elimination.  The next BB is always the first surviving seat clockwise
    # from previous BB; the other survivor is BTN/SB.  A surviving previous BB
    # can therefore never pay the BB twice in a row.
    cases = [
        ({0: 0, 1: 10_000, 2: 10_000}, (2, 2, 1), "button busted"),
        ({0: 10_000, 1: 0, 2: 10_000}, (2, 2, 0), "small blind busted"),
        ({0: 10_000, 1: 10_000, 2: 0}, (1, 1, 0), "big blind busted"),
    ]
    for stacks, expected, label in cases:
        state = waiting_state(engine, stacks)
        engine.start_hand(state)
        require(positions(state) == expected, f"3->2 transition wrong when {label}: {positions(state)}")
        require(state["button_seat"] == state["hand"]["small_blind_seat"], "HU button must be the SB")
        require(not state["hand"]["small_blind_dead"], "HU cannot have a dead small blind")


def test_deal_order(engine):
    original_deck = engine.new_deck
    try:
        engine.new_deck = lambda: [f"X{i}" for i in range(52)]
        state = engine.blank_table_state(
            table_id="deal-three",
            name="deal",
            max_seats=3,
            small_blind=100,
            big_blind=200,
            min_buyin=1,
            max_buyin=10_000,
        )
        for seat in range(3):
            engine.seat_player(state, user_id=seat + 1, name=f"P{seat + 1}", seat=seat, stack=10_000)
        state["tournament"] = {
            "level": 1, "bb_ante": 200,
            "structure": [{"level": 1, "small_blind": 100, "big_blind": 200, "bb_ante": 200, "minutes": 10}],
            "starting_stack": 10_000, "entrants": 3, "total_chips": 30_000,
            "results": [], "status": "running",
        }
        engine.start_hand(state)
        button = next(p for p in state["seats"] if p["seat"] == state["button_seat"])
        require(button["cards"][-1] == "X46", f"three-handed button was not dealt last: {button['cards']}")

        engine.new_deck = lambda: [f"H{i}" for i in range(52)]
        hu = engine.blank_table_state(
            table_id="deal-hu", name="deal", max_seats=2,
            small_blind=100, big_blind=200, min_buyin=1, max_buyin=10_000,
        )
        for seat in range(2):
            engine.seat_player(hu, user_id=seat + 1, name=f"H{seat + 1}", seat=seat, stack=10_000)
        hu["tournament"] = {
            "level": 1, "bb_ante": 200,
            "structure": [{"level": 1, "small_blind": 100, "big_blind": 200, "bb_ante": 200, "minutes": 10}],
            "starting_stack": 10_000, "entrants": 2, "total_chips": 20_000,
            "results": [], "status": "running",
        }
        engine.start_hand(hu)
        button = next(p for p in hu["seats"] if p["seat"] == hu["button_seat"])
        require(button["cards"][-1] == "H48", f"HU BTN/SB was not dealt the final card: {button['cards']}")
    finally:
        engine.new_deck = original_deck


def test_cumulative_short_allins(engine):
    state = engine.blank_table_state(
        table_id="reopen", name="reopen", max_seats=5,
        small_blind=100, big_blind=200, min_buyin=1, max_buyin=10_000,
    )
    stacks = [5_000, 500, 5_000, 800, 5_000]
    for seat, stack in enumerate(stacks):
        engine.seat_player(state, user_id=seat + 1, name=f"R{seat + 1}", seat=seat, stack=stack)
    for p in state["seats"]:
        p.update(in_hand=True, folded=False, all_in=False, round_bet=0, contributed=0, cards=["Ac", "Kd"])
    state.update(status="playing", button_seat=4, chip_unit=100, _ante_paid=0)
    state["tournament"] = {
        "level": 1, "bb_ante": 200,
        "structure": [{"level": 1, "small_blind": 100, "big_blind": 200, "bb_ante": 200, "minutes": 10}],
        "starting_stack": 5_000, "entrants": 5, "total_chips": sum(stacks),
        "results": [], "status": "running",
    }
    state["hand"] = {
        "id": "reopen-hand", "phase": "flop", "deck": [], "board": ["2c", "3d", "4h"],
        "current_bet": 0, "min_raise": 200, "acted": [], "raise_closed_for": [],
        "action_seat": 0, "small_blind_seat": 3, "big_blind_seat": 4,
        "log": [], "showdown": None,
        "starting_stacks": {str(p["user_id"]): p["stack"] for p in state["seats"]},
        "revealed_user_ids": [], "result_persisted": False,
    }

    # A opens to 400, then two short all-ins add 100 and 300.  A now faces a
    # cumulative 400 increase, equal to the last full raise, so A's raise rights
    # must reopen.  C, who called 500, faces only 300 and must remain closed.
    engine.apply_action(state, 1, "raise", 400)
    engine.apply_action(state, 2, "allin")       # 500 total: +100 short
    engine.apply_action(state, 3, "call")        # 500
    engine.apply_action(state, 4, "allin")       # 800 total: +300 short
    engine.apply_action(state, 5, "call")        # 800

    legal_a = engine.legal_actions(state, 1)
    require(legal_a.get("can_raise"), f"cumulative short all-ins did not reopen A: {legal_a}")
    require(legal_a.get("reopened_by_cumulative_short_allins"), "reopen reason marker missing")

    engine.apply_action(state, 1, "call")
    legal_c = engine.legal_actions(state, 3)
    require(not legal_c.get("can_raise"), f"C incorrectly reopened facing only 300: {legal_c}")


def main():
    engine = sitngo_runtime.make_engine()
    test_dead_button(engine)
    test_three_to_heads_up(engine)
    test_deal_order(engine)
    test_cumulative_short_allins(engine)
    print("JJ_SITNGO_TOURNAMENT_RULES_OK")


if __name__ == "__main__":
    main()
