from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

from runtime_builder import build_runtime


def load_runtime_engine():
    runtime = build_runtime(Path(tempfile.mkdtemp(prefix="jj-card-privacy-")) / "runtime")
    engine_path = runtime / "poker_engine.py"
    spec = importlib.util.spec_from_file_location("jj_privacy_runtime_engine", engine_path)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load reconstructed poker engine")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, engine_path.read_text(encoding="utf-8")


def cards_by_user(public: dict) -> dict[int, list[str]]:
    return {int(player["user_id"]): list(player.get("cards") or []) for player in public["seats"]}


def run() -> None:
    engine, source = load_runtime_engine()
    assert "v1.20.0 completed-hand card privacy" in source
    assert "reveal_all" not in source[source.index("def public_state"):]

    # Completed uncontested pot: nobody else's mucked cards become visible.
    uncontested = {
        "id": "jj-table-a",
        "name": "JJ Table A",
        "max_seats": 6,
        "small_blind": 50,
        "big_blind": 100,
        "status": "waiting",
        "button_seat": 0,
        "last_result": {
            "type": "uncontested",
            "winners": [{"user_id": 1, "name": "アリス", "amount": 450}],
        },
        "seats": [
            {"user_id": 1, "name": "アリス", "seat": 0, "stack": 15250, "cards": ["As", "Kd"], "in_hand": False, "folded": False},
            {"user_id": 2, "name": "ボブ", "seat": 1, "stack": 14950, "cards": ["Qc", "Jc"], "in_hand": False, "folded": False},
            {"user_id": 3, "name": "キャロル", "seat": 2, "stack": 14800, "cards": ["7h", "7s"], "in_hand": False, "folded": False},
        ],
        "hand": {
            "id": "jj-table-a-1",
            "phase": "complete",
            "board": [],
            "acted": [1, 2, 3],
            "showdown": None,
        },
    }
    view_2 = cards_by_user(engine.public_state(uncontested, 2))
    assert view_2[2] == ["Qc", "Jc"]  # own cards remain visible
    assert view_2[1] == []              # uncontested winner did not show
    assert view_2[3] == []              # folded/mucked cards stay private

    view_1 = cards_by_user(engine.public_state(uncontested, 1))
    assert view_1[1] == ["As", "Kd"]
    assert view_1[2] == [] and view_1[3] == []

    # Completed showdown: only players represented in showdown scores are public.
    showdown = {
        **uncontested,
        "last_result": {
            "type": "showdown",
            "winners": [{"user_id": 2, "name": "ボブ", "amount": 1200}],
        },
        "hand": {
            "id": "jj-table-a-2",
            "phase": "complete",
            "board": ["2c", "7d", "Kh", "3s", "9c"],
            "acted": [1, 2, 3],
            "showdown": {
                "scores": {"1": [1, 14], "2": [2, 12]},
                "pots": [],
            },
        },
    }
    spectator_participant = cards_by_user(engine.public_state(showdown, 3))
    assert spectator_participant[1] == ["As", "Kd"]
    assert spectator_participant[2] == ["Qc", "Jc"]
    assert spectator_participant[3] == ["7h", "7s"]  # own card exception

    # If player 3 is viewed by player 1, player 3's non-showdown hand stays hidden.
    view_1_showdown = cards_by_user(engine.public_state(showdown, 1))
    assert view_1_showdown[1] == ["As", "Kd"]
    assert view_1_showdown[2] == ["Qc", "Jc"]
    assert view_1_showdown[3] == []

    # During an active hand, existing behavior remains unchanged: own cards are
    # visible and live opponents are represented only as card backs.
    active = {
        **uncontested,
        "status": "playing",
        "hand": {
            "id": "jj-table-a-3",
            "phase": "flop",
            "board": ["2c", "7d", "Kh"],
            "current_bet": 0,
            "min_raise": 100,
            "action_seat": 1,
            "acted": [],
            "raise_closed_for": [],
            "showdown": None,
        },
        "seats": [
            {"user_id": 1, "name": "アリス", "seat": 0, "stack": 14700, "round_bet": 0, "cards": ["As", "Kd"], "in_hand": True, "folded": False, "all_in": False},
            {"user_id": 2, "name": "ボブ", "seat": 1, "stack": 14700, "round_bet": 0, "cards": ["Qc", "Jc"], "in_hand": True, "folded": False, "all_in": False},
            {"user_id": 3, "name": "キャロル", "seat": 2, "stack": 14700, "round_bet": 0, "cards": ["7h", "7s"], "in_hand": True, "folded": False, "all_in": False},
        ],
    }
    active_view = cards_by_user(engine.public_state(active, 1))
    assert active_view[1] == ["As", "Kd"]
    assert active_view[2] == ["??", "??"]
    assert active_view[3] == ["??", "??"]

    print("JJ_CARD_PRIVACY_SMOKE_OK")


if __name__ == "__main__":
    run()
