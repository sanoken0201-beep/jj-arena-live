from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

from runtime_builder import RUNTIME_VERSION, build_runtime


def _load_engine(root: Path):
    path = root / "poker_engine.py"
    spec = importlib.util.spec_from_file_location("jj_v124_engine_integration", path)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load reconstructed poker engine")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _new_table(engine, table_id: str, stacks: list[int]):
    state = engine.blank_table_state(
        table_id=table_id,
        name=table_id,
        max_seats=len(stacks),
        small_blind=50,
        big_blind=100,
        min_buyin=100,
        max_buyin=5000,
    )
    names = ["アリス", "ボブ", "キャロル"]
    for seat, stack in enumerate(stacks):
        engine.seat_player(state, user_id=100 + seat, name=names[seat], seat=seat, stack=stack)
    engine.start_hand(state)
    return state


def _advance_all_runout_frames(engine, state: dict) -> list[int]:
    board_lengths: list[int] = []
    for _ in range(4):
        hand = state.get("hand") or {}
        if state.get("status") != "playing":
            break
        assert hand.get("forced_runout") is True
        hand["runout_due_at_epoch"] = engine.time.time() - 1
        assert engine.advance_forced_runout(state) is True
        board_lengths.append(len((state.get("hand") or {}).get("board") or []))
    return board_lengths


def test_real_no_flop_no_drop(engine) -> None:
    state = _new_table(engine, "v124-nfnd", [1000, 1000])
    actor_seat = int(state["hand"]["action_seat"])
    actor = next(p for p in state["seats"] if int(p["seat"]) == actor_seat)
    engine.apply_action(state, int(actor["user_id"]), "fold")
    assert state["status"] == "waiting"
    assert len((state.get("hand") or {}).get("board") or []) == 0
    assert int((state.get("hand") or {}).get("rake") or 0) == 0
    result = state.get("last_result") or {}
    assert result.get("type") == "uncontested"
    winners = result.get("winners") or []
    assert len(winners) == 1
    assert int(winners[0].get("amount") or 0) == 150
    assert sum(int(p.get("stack", 0) or 0) for p in state["seats"]) == 2000
    assert all(int(p.get("contributed", 0) or 0) == 0 for p in state["seats"])


def test_real_three_way_sidepot_runout(engine) -> None:
    state = _new_table(engine, "v124-sidepot", [500, 1000, 1500])
    assert int(state["hand"]["action_seat"]) == 0
    engine.apply_action(state, 100, "allin")
    assert int(state["hand"]["action_seat"]) == 1
    engine.apply_action(state, 101, "allin")
    assert int(state["hand"]["action_seat"]) == 2
    engine.apply_action(state, 102, "call")

    hand = state.get("hand") or {}
    assert hand.get("forced_runout") is True
    assert len(hand.get("board") or []) == 0
    assert [int(p.get("contributed", 0) or 0) for p in state["seats"]] == [500, 1000, 1000]
    assert [int(p.get("round_bet", 0) or 0) for p in state["seats"]] == [0, 0, 0]
    assert int(state["seats"][2].get("stack") or 0) == 500

    board_lengths = _advance_all_runout_frames(engine, state)
    assert board_lengths[:3] == [3, 4, 5]
    assert state["status"] == "waiting"
    assert (state.get("last_result") or {}).get("type") == "showdown"
    showdown = (state.get("hand") or {}).get("showdown") or {}
    pots = showdown.get("pots") or []
    assert len(pots) >= 2, "unequal all-in contributions must create a side pot"
    assert all(int(p.get("contributed", 0) or 0) == 0 for p in state["seats"])
    assert not (state.get("hand") or {}).get("forced_runout")
    assert float(state.get("showdown_hold_until_epoch") or 0) > engine.time.time()


def main() -> None:
    assert RUNTIME_VERSION == "1.24.2"
    with tempfile.TemporaryDirectory() as td:
        root = build_runtime(Path(td) / "runtime")
        engine = _load_engine(root)
        test_real_no_flop_no_drop(engine)
        test_real_three_way_sidepot_runout(engine)
    print("v1.24 real engine integration: ok")


if __name__ == "__main__":
    main()
