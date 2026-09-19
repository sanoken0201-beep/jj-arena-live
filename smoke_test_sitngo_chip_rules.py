"""Tournament-chip regression tests independent from production accounts."""
from __future__ import annotations

from pathlib import Path

import sitngo_admin_config
import sitngo_chip_rules
import sitngo_runtime


sitngo_chip_rules.install(sitngo_runtime)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def tournament_state(engine, stacks, *, unit, contributions=None, ante=0, button=0):
    total = sum(stacks)
    state = engine.blank_table_state(
        table_id="chip-rules",
        name="chip rules",
        max_seats=max(2, len(stacks)),
        small_blind=unit,
        big_blind=unit * 2,
        min_buyin=1,
        max_buyin=max(total, 1),
    )
    for index, stack in enumerate(stacks):
        engine.seat_player(state, user_id=index + 1, name=f"P{index + 1}", seat=index, stack=stack)
    state.update(status="waiting", button_seat=button, chip_unit=unit, _ante_paid=0)
    state["tournament"] = {
        "level": 1,
        "bb_ante": unit * 2,
        "structure": [{"level": 1, "small_blind": unit, "big_blind": unit * 2, "bb_ante": unit * 2, "minutes": 10}],
        "starting_stack": max(stacks),
        "entrants": len(stacks),
        "total_chips": total,
        "results": [],
        "status": "running",
    }
    if contributions is not None:
        state["status"] = "playing"
        state["_ante_paid"] = ante
        for player, amount in zip(state["seats"], contributions):
            player.update(
                in_hand=True,
                folded=False,
                all_in=False,
                round_bet=amount,
                contributed=amount,
                cards=["Kc", "Qd"] if player["seat"] == 0 else ["Kh", "Jd"] if player["seat"] == 1 else ["Qs", "Td"],
            )
        state["hand"] = {
            "id": "chip-rules-hand",
            "phase": "river",
            "deck": [],
            "board": ["2c", "3d", "4h", "5s", "6c"],
            "current_bet": max(contributions),
            "min_raise": unit * 2,
            "acted": [],
            "raise_closed_for": [],
            "action_seat": None,
            "small_blind_seat": 0,
            "big_blind_seat": 1,
            "log": [],
            "showdown": None,
            "starting_stacks": {str(p["user_id"]): p["stack"] + p["contributed"] for p in state["seats"]},
            "revealed_user_ids": [],
            "result_persisted": False,
        }
    return state


def main():
    engine = sitngo_runtime.make_engine()
    levels = sitngo_admin_config.DEFAULT_BLIND_STRUCTURE
    schedule_state = {
        "tournament": {
            "level": 1,
            "structure": levels,
            "starting_stack": 30_000,
            "entrants": 6,
            "total_chips": 180_000,
        },
        "seats": [],
    }
    # Online Sit&Go keeps exact 100-point accounting at every level. Physical
    # chip color-ups must never round or redistribute tournament value.
    for level in range(1, len(levels) + 1):
        require(
            sitngo_chip_rules.chip_unit_for_level(schedule_state, level - 1) == 100,
            f"online accounting unit drift at level {level}",
        )

    exact = tournament_state(engine, [23_100, 29_900, 37_000], unit=100)
    exact["tournament"].update(
        level=11,
        structure=levels,
        starting_stack=30_000,
        entrants=3,
        total_chips=90_000,
    )
    before_exact = [p["stack"] for p in exact["seats"]]
    adjustments = sitngo_chip_rules.color_up(exact, 5_000)
    require(adjustments == [], "online compatibility color-up must not redistribute stacks")
    require([p["stack"] for p in exact["seats"]] == before_exact, "online color-up changed player value")
    require(exact["chip_unit"] == 100, "online accounting unit must remain 100")

    # Regression for the former unfair conversion: 10k/40k must never become
    # 25k/25k simply because a physical 25k denomination was requested.
    non_multiple = tournament_state(engine, [10_000, 40_000], unit=100)
    before_non_multiple = [p["stack"] for p in non_multiple["seats"]]
    sitngo_chip_rules.color_up(non_multiple, 25_000)
    require(
        [p["stack"] for p in non_multiple["seats"]] == before_non_multiple,
        "online denomination request redistributed tournament chips",
    )


    # Normal raises are denomination-locked; all-in/call remain engine-driven.
    action = engine.blank_table_state(
        table_id="action-unit",
        name="action",
        max_seats=2,
        small_blind=500,
        big_blind=1_000,
        min_buyin=10_000,
        max_buyin=10_000,
    )
    engine.seat_player(action, user_id=1, name="A", seat=0, stack=10_000)
    engine.seat_player(action, user_id=2, name="B", seat=1, stack=10_000)
    action["tournament"] = {
        "level": 1,
        "bb_ante": 1_000,
        "structure": [{"level": 1, "small_blind": 500, "big_blind": 1_000, "bb_ante": 1_000, "minutes": 10}],
        "starting_stack": 10_000,
        "entrants": 2,
        "total_chips": 20_000,
        "results": [],
        "status": "running",
    }
    engine.start_hand(action)
    require(action["chip_unit"] == 100, "custom structure must keep exact 100-point accounting")
    actor = next(p for p in action["seats"] if p["seat"] == action["hand"]["action_seat"])
    try:
        engine.apply_action(action, actor["user_id"], "raise", 2_250)
    except ValueError as exc:
        require("100" in str(exc), "invalid-unit raise returned the wrong error")
    else:
        raise AssertionError("sub-100-point raise was accepted")

    # Two-way tied pot with a 5k odd chip: never create 2,500/50/1-point chips.
    split = tournament_state(engine, [10_000, 5_000], unit=5_000, contributions=[5_000, 5_000], ante=5_000, button=0)
    split["tournament"].update(starting_stack=15_000, entrants=2, total_chips=30_000, bb_ante=5_000)
    engine._showdown(split)
    awards = {w["user_id"]: w["amount"] for w in split["last_result"]["winners"]}
    require(awards == {1: 5_000, 2: 10_000}, f"odd chip was not awarded left of button: {awards}")
    require(all(p["stack"] % 5_000 == 0 for p in split["seats"]), "split generated sub-5k chips")

    # BBA is part of the main pot. Keeping it as a synthetic independent pot can
    # create two separate odd-chip decisions and change a three-way tied payout.
    bba = tournament_state(engine, [10_000, 10_000, 10_000, 10_000], unit=5_000, contributions=[5_000] * 4, ante=10_000, button=0)
    bba["tournament"].update(starting_stack=10_000, entrants=4, total_chips=40_000, bb_ante=10_000)
    cards = [["Tc", "3c"], ["Td", "4c"], ["Th", "5c"], ["9c", "8d"]]
    for player, hole in zip(bba["seats"], cards):
        player["cards"] = hole
    bba["hand"]["board"] = ["Ah", "Kd", "Qc", "Js", "2h"]
    engine._showdown(bba)
    bba_awards = {w["user_id"]: w["amount"] for w in bba["last_result"]["winners"]}
    require(bba_awards == {1: 10_000, 2: 10_000, 3: 10_000}, f"BBA was not merged into the main pot: {bba_awards}")
    require(len(bba["hand"]["showdown"]["pots"]) == 1, "BBA survived as a second logical pot")
    require(bba["hand"]["showdown"]["pots"][0]["amount"] == 30_000, "merged main-pot amount is wrong")

    # Main/side pots are settled separately and every award remains denomination-safe.
    side = tournament_state(engine, [10_000, 10_000, 10_000], unit=5_000, contributions=[10_000, 10_000, 5_000], ante=5_000, button=0)
    side["tournament"].update(starting_stack=20_000, entrants=3, total_chips=55_000, bb_ante=5_000)
    engine._showdown(side)
    require(all(p["stack"] % 5_000 == 0 for p in side["seats"]), "side-pot split generated an obsolete chip")
    require(all(a["amount"] % 5_000 == 0 for pot in side["hand"]["showdown"]["pots"] for a in pot.get("awards", [])), "side-pot award broke denomination")

    # Browser sizing and pot display must use chip_unit and include the dead BBA.
    built = Path(".jj_build/static/app.js")
    if built.exists():
        js = built.read_text(encoding="utf-8")
        require("jj sitngo chip unit ui 2026-09-18" in js, "chip-unit browser patch missing")
        require("tournament.ante_paid" in js, "BBA is still omitted from displayed pot")
        require("input.step=String(step)" in js, "raise input is not denomination-aware")

    print("JJ_SITNGO_CHIP_RULES_OK")


if __name__ == "__main__":
    main()
