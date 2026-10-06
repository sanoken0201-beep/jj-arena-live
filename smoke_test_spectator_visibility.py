from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path
from types import SimpleNamespace

from runtime_builder import build_runtime
from spectator_visibility import MARKER, install


ROOT = Path(__file__).resolve().parent


def load_runtime_engine():
    runtime = build_runtime(Path(tempfile.mkdtemp(prefix="jj-spectator-visibility-")) / "runtime")
    engine_path = runtime / "poker_engine.py"
    spec = importlib.util.spec_from_file_location("jj_spectator_runtime_engine", engine_path)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load materialized poker engine")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cards_by_user(public: dict) -> dict[int, list[str]]:
    return {
        int(player["user_id"]): list(player.get("cards") or [])
        for player in public.get("seats", [])
    }


def run() -> None:
    engine = load_runtime_engine()
    server = SimpleNamespace(public_state=engine.public_state)

    original = engine.public_state
    install(server, engine)
    assert MARKER == "spectator all-hole-card visibility 2026-10-06"
    assert server.public_state is engine.public_state
    assert engine.public_state is not original

    state = {
        "id": "jj-table-a",
        "name": "JJ Ring",
        "max_seats": 6,
        "small_blind": 50,
        "big_blind": 100,
        "status": "playing",
        "button_seat": 0,
        "seats": [
            {
                "user_id": 1, "name": "Alice", "seat": 0, "stack": 14800,
                "round_bet": 100, "contributed": 100, "cards": ["As", "Kd"],
                "in_hand": True, "folded": False, "all_in": False,
            },
            {
                "user_id": 2, "name": "Bob", "seat": 1, "stack": 14700,
                "round_bet": 200, "contributed": 200, "cards": ["Qc", "Jc"],
                "in_hand": True, "folded": False, "all_in": False,
            },
            {
                "user_id": 3, "name": "Carol", "seat": 2, "stack": 15000,
                "round_bet": 0, "contributed": 0, "cards": ["7h", "7s"],
                "in_hand": False, "folded": True, "all_in": False,
            },
        ],
        "hand": {
            "id": "spectator-hand",
            "phase": "flop",
            "board": ["2c", "7d", "Kh"],
            "current_bet": 200,
            "min_raise": 200,
            "action_seat": 0,
            "acted": [],
            "raise_closed_for": [],
            "showdown": None,
        },
    }

    # A seated player keeps the established privacy model.
    player_view = cards_by_user(server.public_state(state, 1))
    assert player_view[1] == ["As", "Kd"]
    assert player_view[2] == ["??", "??"]
    assert player_view[3] == []

    # A true spectator remains outside seats/actions but sees every stored hand.
    spectator = server.public_state(state, 99)
    spectator_cards = cards_by_user(spectator)
    assert spectator["viewer_mode"] == "spectator"
    assert spectator["legal"] == {"can_act": False}
    assert spectator_cards == {
        1: ["As", "Kd"],
        2: ["Qc", "Jc"],
        3: ["7h", "7s"],
    }
    assert len(spectator["seats"]) == 3
    assert all(int(player["user_id"]) != 99 for player in spectator["seats"])
    assert all(int(player["user_id"]) != 99 for player in state["seats"])

    # Internal calls without an authenticated viewer keep the core privacy rule.
    anonymous = cards_by_user(server.public_state(state, None))
    assert anonymous[1] == ["??", "??"]
    assert anonymous[2] == ["??", "??"]
    assert anonymous[3] == []

    # Installing twice must not stack wrappers.
    wrapped = server.public_state
    install(server, engine)
    assert server.public_state is wrapped
    assert engine.public_state is wrapped

    # The browser's "観戦する" path only opens state + WebSocket. It must never
    # invoke a seat mutation implicitly.
    app_js = (ROOT / "materialized_v1244" / "static" / "app.js").read_text(encoding="utf-8")
    start = app_js.index("async function openTable")
    end = app_js.index("function disconnectTable", start)
    open_table = app_js[start:end]
    assert "/seat" not in open_table
    assert "/join" not in open_table
    assert "api('/tables/'+id)" in open_table
    assert "connectTable(id)" in open_table

    print("JJ_SPECTATOR_VISIBILITY_OK")


if __name__ == "__main__":
    run()
