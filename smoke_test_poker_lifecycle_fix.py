from __future__ import annotations

from types import SimpleNamespace

import poker_lifecycle_fix
from app_materialized import runtime_poker_engine


class FakeRuntimeServer:
    TABLE_IDLE_SECONDS = 15 * 60

    def __init__(self) -> None:
        self.table_presence: dict[tuple[str, int], float] = {}
        self.hub = SimpleNamespace(connections={})

        def prune_idle_players(state: dict, table_id: str, now_ts: float | None = None) -> bool:
            now = float(0 if now_ts is None else now_ts)
            cutoff = now - self.TABLE_IDLE_SECONDS
            before = list(state.get("seats", []))
            state["seats"] = [
                player
                for player in before
                if self.table_presence.get((table_id, int(player["user_id"])), 0) >= cutoff
            ]
            return len(state["seats"]) != len(before)

        self.prune_idle_players = prune_idle_players


def player(user_id: int, name: str, seat: int, contributed: int, cards: list[str], *, folded: bool = False) -> dict:
    return {
        "user_id": user_id,
        "name": name,
        "seat": seat,
        "stack": 0,
        "in_hand": True,
        "folded": folded,
        "all_in": not folded,
        "round_bet": 0,
        "contributed": contributed,
        "cards": cards,
        "ready": False,
        "sitting_out": False,
        "sit_out_next": False,
    }


def test_connected_presence_survives_waiting_cleanup() -> None:
    server = FakeRuntimeServer()
    poker_lifecycle_fix.install(server)
    wrapped = server.prune_idle_players
    poker_lifecycle_fix.install(server)
    assert server.prune_idle_players is wrapped, "install must be idempotent"

    state = {
        "status": "waiting",
        "seats": [
            {"user_id": 1, "name": "A"},
            {"user_id": 2, "name": "B"},
            {"user_id": 3, "name": "C"},
        ],
    }
    now = 10_000.0
    server.table_presence = {
        ("table-a", 1): now - 2_000,
        ("table-a", 2): now - 2_000,
        ("table-a", 3): now - 2_000,
    }
    server.hub.connections["table-a"] = [(object(), 1), (object(), 2)]

    changed = server.prune_idle_players(state, "table-a", now_ts=now)
    assert changed is True, "the genuinely disconnected stale player should still be pruned"
    assert [p["user_id"] for p in state["seats"]] == [1, 2]
    assert server.table_presence[("table-a", 1)] == now
    assert server.table_presence[("table-a", 2)] == now


def test_sidepot_chop_keeps_winners_seated() -> None:
    # A and B are all-in for 1000, C contributed 500 then folded. This creates
    # a 1500 main pot and 1000 side pot. A royal flush on the board makes A/B
    # chop both pots, reproducing the reported side-pot split condition.
    state = runtime_poker_engine.blank_table_state(
        table_id="sidepot-chop",
        name="Sidepot Chop",
        max_seats=3,
        small_blind=50,
        big_blind=100,
        min_buyin=100,
        max_buyin=5000,
    )
    state.update({
        "status": "playing",
        "button_seat": 2,
        "session_active": True,
        "rake_percent": 0.05,
        "rake_cap": 300,
    })
    state["seats"] = [
        player(1, "A", 0, 1000, ["2c", "3d"]),
        player(2, "B", 1, 1000, ["4c", "5d"]),
        player(3, "C", 2, 500, ["6c", "7d"], folded=True),
    ]
    state["hand"] = {
        "id": "reported-sidepot-chop",
        "phase": "river",
        "board": ["Ah", "Kh", "Qh", "Jh", "Th"],
        "deck": [],
        "action_seat": None,
        "acted": [],
        "current_bet": 0,
        "min_raise": 100,
        "log": [],
        "starting_stacks": {"1": 1000, "2": 1000, "3": 500},
        "revealed_user_ids": [],
    }

    runtime_poker_engine._showdown(state)

    pots = state["hand"]["showdown"]["pots"]
    assert [pot["gross_amount"] for pot in pots] == [1500, 1000]
    assert all({w["user_id"] for w in pot["winners"]} == {1, 2} for pot in pots)
    assert state["last_result"]["gross_pot"] == 2500
    assert state["last_result"]["rake"] == 125
    assert {w["user_id"] for w in state["last_result"]["winners"]} == {1, 2}
    assert all(next(p for p in state["seats"] if p["user_id"] == uid)["stack"] > 0 for uid in (1, 2))
    assert [p["user_id"] for p in state["seats"]] == [1, 2, 3], "showdown must never eject a seated player"
    assert state["status"] == "waiting"


if __name__ == "__main__":
    test_connected_presence_survives_waiting_cleanup()
    test_sidepot_chop_keeps_winners_seated()
    print("JJ_POKER_LIFECYCLE_FIX_OK")
