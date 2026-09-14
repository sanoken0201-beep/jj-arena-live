from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import rake_settlement_fix as fix


ROOT = Path(__file__).resolve().parent


def _load_materialized_engine():
    path = ROOT / "materialized_v1244" / "poker_engine.py"
    spec = importlib.util.spec_from_file_location("jj_rake_test_engine", path)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load materialized poker engine")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _state(contributions: list[int], *, big_blind: int = 100) -> dict:
    seats = []
    for i, amount in enumerate(contributions):
        seats.append(
            {
                "user_id": i + 1,
                "name": f"P{i + 1}",
                "seat": i,
                "stack": 0,
                "in_hand": True,
                "folded": False,
                "all_in": True,
                "round_bet": amount,
                "contributed": amount,
                "cards": [],
            }
        )
    return {
        "big_blind": big_blind,
        "rake_percent": 0.10,
        "rake_cap": big_blind * 5,
        "max_seats": len(seats),
        "button_seat": 0,
        "seats": seats,
        "hand": {"board": ["2c", "3d", "4h"]},
    }


def _gross_and_rake(engine, state: dict) -> tuple[int, int, list[int]]:
    pots = engine._build_side_pots(state)
    amounts = [int(p["amount"]) for p in pots]
    gross = sum(amounts)
    return gross, int(engine._rake_amount(state, gross)), amounts


def test_heads_up_uncalled_allin(engine) -> None:
    state = _state([1000, 500])
    before = sum(int(p["stack"]) + int(p["contributed"]) for p in state["seats"])

    assert fix.refund_uncalled_contribution(state) == 500
    assert fix.refund_uncalled_contribution(state) == 0  # idempotent
    assert [int(p["contributed"]) for p in state["seats"]] == [500, 500]
    assert int(state["seats"][0]["stack"]) == 500
    assert state["seats"][0]["all_in"] is False

    gross, rake, pots = _gross_and_rake(engine, state)
    assert gross == 1000
    assert rake == 100
    assert pots == [1000]

    after = sum(int(p["stack"]) + int(p["contributed"]) for p in state["seats"])
    assert after == before


def test_three_way_sidepot(engine) -> None:
    state = _state([1500, 1000, 500])
    assert fix.refund_uncalled_contribution(state) == 500
    assert [int(p["contributed"]) for p in state["seats"]] == [1000, 1000, 500]

    gross, rake, pots = _gross_and_rake(engine, state)
    assert pots == [1500, 1000]
    assert gross == 2500
    assert rake == 250

    alloc = engine._allocate_rake(pots, rake)
    assert alloc == [150, 100]
    assert sum(alloc) == rake


def test_rake_cap_and_tied_top(engine) -> None:
    state = _state([6000, 6000])
    assert fix.refund_uncalled_contribution(state) == 0
    gross, rake, pots = _gross_and_rake(engine, state)
    assert pots == [12000]
    assert gross == 12000
    assert rake == 500  # 5bb cap at bb=100


def _install_on_fake_engine():
    observations: list[tuple[str, int, list[int]]] = []

    def original_showdown(state):
        observations.append(
            (
                "showdown",
                sum(int(p.get("contributed", 0)) for p in state["seats"]),
                [int(p.get("stack", 0)) for p in state["seats"]],
            )
        )

    def original_uncontested(state, *args, **kwargs):
        observations.append(
            (
                "uncontested",
                sum(int(p.get("contributed", 0)) for p in state["seats"]),
                [int(p.get("stack", 0)) for p in state["seats"]],
            )
        )

    fake = SimpleNamespace(
        _showdown=original_showdown,
        _award_uncontested=original_uncontested,
    )
    fix._INSTALLED = False
    fix.install(fake)
    return fake, observations


def test_runtime_wrappers() -> None:
    fake, observations = _install_on_fake_engine()

    showdown_state = _state([1000, 500])
    showdown_state["hand"]["board"] = ["2c", "3d", "4h", "5s", "9c"]
    fake._showdown(showdown_state)
    assert observations[-1] == ("showdown", 1000, [500, 0])

    postflop_fold = _state([200, 100])
    postflop_fold["seats"][1]["folded"] = True
    postflop_fold["seats"][0]["stack"] = 800
    postflop_fold["seats"][1]["stack"] = 900
    fake._award_uncontested(postflop_fold, postflop_fold["seats"][0])
    assert observations[-1] == ("uncontested", 200, [900, 900])

    # Preserve the existing preflop No Flop, No Drop result semantics.  The
    # blind imbalance remains represented inside the gross pot because rake is
    # zero there already; changing it would only alter displayed pot history.
    preflop_fold = _state([100, 50])
    preflop_fold["hand"]["board"] = []
    preflop_fold["seats"][0]["stack"] = 900
    preflop_fold["seats"][1]["stack"] = 950
    fake._award_uncontested(preflop_fold, preflop_fold["seats"][0])
    assert observations[-1] == ("uncontested", 150, [900, 950])


def main() -> None:
    engine = _load_materialized_engine()
    test_heads_up_uncalled_allin(engine)
    test_three_way_sidepot(engine)
    test_rake_cap_and_tied_top(engine)
    test_runtime_wrappers()
    print("rake settlement regression: ok")


if __name__ == "__main__":
    main()
