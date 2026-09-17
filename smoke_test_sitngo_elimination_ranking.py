"""Regression tests for TDA-style Sit&Go simultaneous elimination ranking."""
from __future__ import annotations

import sitngo_chip_rules
import sitngo_runtime
import sitngo_tournament_rules


sitngo_tournament_rules.install(sitngo_runtime)
sitngo_chip_rules.install(sitngo_runtime)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def ranked_state(engine, *, button_stack: int, bb_stack: int, bb_ante: int = 5_000):
    state = engine.blank_table_state(
        table_id="tda-ranking",
        name="TDA ranking",
        max_seats=4,
        small_blind=2_500,
        big_blind=5_000,
        min_buyin=1,
        max_buyin=100_000,
    )
    stacks = {0: button_stack, 1: 20_000, 2: bb_stack, 3: 20_000}
    for seat, stack in stacks.items():
        engine.seat_player(
            state,
            user_id=seat + 1,
            name=f"P{seat + 1}",
            seat=seat,
            stack=stack,
        )
    state.update(status="waiting", button_seat=3, hand_no=0)
    state["tournament"] = {
        "level": 1,
        "bb_ante": bb_ante,
        "structure": [
            {
                "level": 1,
                "small_blind": 2_500,
                "big_blind": 5_000,
                "bb_ante": bb_ante,
                "minutes": 10,
            }
        ],
        "starting_stack": 20_000,
        "entrants": 4,
        "total_chips": sum(stacks.values()),
        "results": [],
        "status": "running",
    }
    engine.start_hand(state)
    require(state["button_seat"] == 0, f"unexpected first button: {state['button_seat']}")
    require(state["hand"]["big_blind_seat"] == 2, f"unexpected first BB: {state['hand']['big_blind_seat']}")
    return state


def finish_two_busts(state):
    # User 1 (button) and user 3 (BB) are treated as having busted in the same
    # hand. Users 2 and 4 remain alive, so the two bustouts compete for 3rd/4th.
    for player in state["seats"]:
        if player["user_id"] in {1, 3}:
            player["stack"] = 0
    state["status"] = "waiting"
    state["hand"]["phase"] = "complete"
    runtime = object.__new__(sitngo_runtime.TournamentRuntime)
    runtime.finish(state)
    return {row["user_id"]: row for row in state["tournament"]["results"]}


def test_bba_changes_same_hand_order(engine):
    # TDA 2026 BBA comparison example shape:
    # P1 starts 8k and pays no ante. P3 starts 10k as BB and pays a 5k BBA.
    # Comparison stacks are therefore 8k vs 5k, so P1 ranks higher even though
    # P3 had the larger raw stack before the hand.
    state = ranked_state(engine, button_stack=8_000, bb_stack=10_000)
    ranking = state["hand"]["elimination_stacks_after_ante"]
    require(ranking["1"] == 8_000, f"non-BB comparison stack changed: {ranking}")
    require(ranking["3"] == 5_000, f"BB BBA not deducted for ranking: {ranking}")
    require(state["hand"]["starting_stacks"]["3"] == 10_000, "raw starting stack was overwritten")
    require(state["hand"]["elimination_ranking_basis"] == "tda_2026_post_ante", "ranking basis missing")

    results = finish_two_busts(state)
    require(results[1]["place"] == 3, f"8k post-ante stack should finish 3rd: {results}")
    require(results[3]["place"] == 4, f"5k post-ante stack should finish 4th: {results}")
    require(results[3]["starting_stack"] == 10_000, "reported raw starting stack must remain 10k")
    require(results[3]["ranking_stack"] == 5_000, "reported comparison stack must be 5k")


def test_equal_comparison_stacks_tie(engine):
    # P1 begins with 5k. P3 begins with 10k but pays 5k BBA. Both comparison
    # stacks are 5k, so TDA-style simultaneous elimination records a shared 3rd.
    state = ranked_state(engine, button_stack=5_000, bb_stack=10_000)
    results = finish_two_busts(state)
    require(results[1]["place"] == 3 and results[3]["place"] == 3, f"equal stacks did not tie: {results}")
    require(results[1]["tie_size"] == 2 and results[3]["tie_size"] == 2, f"tie metadata wrong: {results}")


def test_short_bb_uses_actual_ante_paid(engine):
    # Big-blind-first: a 7.5k BB posts the 5k blind first, leaving only 2.5k for
    # a scheduled 5k BBA. Ranking deducts the 2.5k actually posted as ante, not
    # a fictional full 5k and not the live blind.
    state = ranked_state(engine, button_stack=5_000, bb_stack=7_500)
    ranking = state["hand"]["elimination_stacks_after_ante"]
    require(state["hand"]["bba_paid_for_ranking"]["3"] == 2_500, "actual short BBA payment not recorded")
    require(ranking["3"] == 5_000, f"short BB comparison stack should be 5k: {ranking}")
    results = finish_two_busts(state)
    require(results[1]["place"] == 3 and results[3]["place"] == 3, f"actual-ante tie not preserved: {results}")


def test_legacy_hand_falls_back_to_raw_starting_stack(engine):
    # A hand already in progress when the deployment occurs has no post-ante
    # snapshot. It must keep the previous ranking interpretation rather than be
    # retroactively changed in the middle of a tournament.
    state = ranked_state(engine, button_stack=8_000, bb_stack=10_000)
    state["hand"].pop("elimination_stacks_after_ante")
    state["hand"].pop("elimination_ranking_basis")
    state["hand"].pop("bba_paid_for_ranking")
    results = finish_two_busts(state)
    require(results[3]["place"] == 3 and results[1]["place"] == 4, f"legacy fallback changed old hand: {results}")


def main():
    engine = sitngo_runtime.make_engine()
    test_bba_changes_same_hand_order(engine)
    test_equal_comparison_stacks_tie(engine)
    test_short_bb_uses_actual_ante_paid(engine)
    test_legacy_hand_falls_back_to_raw_starting_stack(engine)
    print("JJ_SITNGO_TDA_ELIMINATION_RANKING_OK")


if __name__ == "__main__":
    main()
