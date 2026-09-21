from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import timebank_rules


class Lock:
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc, tb):
        return False


class Hub:
    def __init__(self):
        self.broadcasts = 0
    async def broadcast(self, _table_id):
        self.broadcasts += 1


class Engine:
    def __init__(self):
        self.actions = []
    def legal_actions(self, _state, _uid):
        return {"can_act": True, "can_check": True}
    def apply_action(self, state, uid, action, amount=None):
        self.actions.append((uid, action))
        player = next(p for p in state["seats"] if p["user_id"] == uid)
        if action == "fold":
            player["folded"] = True
        state["hand"]["action_seat"] = None


def state(cards=None):
    player = {
        "user_id": 7,
        "name": "Timebank Tester",
        "seat": 0,
        "stack": 1000,
        "folded": False,
    }
    if cards is not None:
        player["timebank_cards_remaining"] = cards
    return {
        "status": "playing",
        "seats": [player],
        "hand": {
            "action_seat": 0,
            "action_deadline": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
            "log": [],
        },
    }


async def one_ring_scan(server):
    calls = 0
    original_sleep = asyncio.sleep

    async def sleep(_seconds):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise asyncio.CancelledError

    asyncio.sleep = sleep
    try:
        await server.timeout_loop()
    except asyncio.CancelledError:
        pass
    finally:
        asyncio.sleep = original_sleep


def ring_test():
    engine = Engine()
    holder = {"state": state()}
    server = SimpleNamespace(
        db=SimpleNamespace(FIXED_TABLES=(("jj-table-a", "JJ Table A"),)),
        arm_action_deadline=lambda *_args, **_kwargs: None,
        get_table_lock=lambda _tid: Lock(),
        load_table=lambda _tid: holder["state"],
        save_table=lambda s: holder.__setitem__("state", s),
        prune_idle_players=lambda _s, _tid: False,
        hub=Hub(),
    )
    timebank_rules.install_ring(server, engine)

    # Normal decision window is 30 seconds and lazily grants exactly 3 cards.
    fresh = state()
    fresh["hand"]["action_deadline"] = None
    before = datetime.now(timezone.utc)
    server.arm_action_deadline(fresh)
    deadline = datetime.fromisoformat(fresh["hand"]["action_deadline"])
    seconds = (deadline - before).total_seconds()
    assert 29 <= seconds <= 31, seconds
    assert fresh["seats"][0]["timebank_cards_remaining"] == 3
    assert fresh["hand"]["action_clock_source"] == "base"

    # Three consecutive expiries consume all three cards. None may auto-check/fold.
    holder["state"] = state(3)
    for expected in (2, 1, 0):
        holder["state"]["hand"]["action_deadline"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        asyncio.run(one_ring_scan(server))
        assert holder["state"]["seats"][0]["timebank_cards_remaining"] == expected
        assert engine.actions == []
        assert holder["state"]["hand"]["action_clock_source"] == "timebank"
        extended = datetime.fromisoformat(holder["state"]["hand"]["action_deadline"])
        remain = (extended - datetime.now(timezone.utc)).total_seconds()
        assert 28 <= remain <= 31, remain

    # After the third card has been used, the following 30s expiry is forced fold,
    # even in a spot where checking would otherwise be legal.
    holder["state"]["hand"]["action_deadline"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    asyncio.run(one_ring_scan(server))
    assert engine.actions[-1] == (7, "fold")
    assert holder["state"]["seats"][0]["folded"] is True


class TournamentRuntime:
    def __init__(self, server, engine, holder):
        self.server = server
        self.engine = engine
        self.holder = holder
        self._pending_action_arrivals = {}
        self.original_calls = 0
    def load(self, _eid):
        return self.holder["state"]
    def save(self, value):
        self.holder["state"] = value
    async def tick(self, _eid, *, now=None, recover=False):
        self.original_calls += 1
        return now


def sitngo_test():
    engine = Engine()
    holder = {"state": state(3)}
    server = SimpleNamespace(
        get_table_lock=lambda _eid: Lock(),
        hub=Hub(),
        arm_action_deadline=lambda s, seconds=30: timebank_rules._set_deadline(s, seconds, source="base"),
    )
    module = SimpleNamespace(TournamentRuntime=TournamentRuntime)
    timebank_rules.install_sitngo(module)
    runtime = module.TournamentRuntime(server, engine, holder)

    for expected in (2, 1, 0):
        deadline = datetime.now(timezone.utc) - timedelta(seconds=1)
        holder["state"]["hand"]["action_deadline"] = deadline.isoformat()
        asyncio.run(runtime.tick("event-1", now=deadline.timestamp() + 1))
        assert holder["state"]["seats"][0]["timebank_cards_remaining"] == expected
        assert engine.actions == []
        assert runtime.original_calls == 0
        assert holder["state"]["hand"]["action_clock_source"] == "timebank"

    deadline = datetime.now(timezone.utc) - timedelta(seconds=1)
    holder["state"]["hand"]["action_deadline"] = deadline.isoformat()
    asyncio.run(runtime.tick("event-1", now=deadline.timestamp() + 1))
    assert engine.actions[-1] == (7, "fold")
    assert holder["state"]["seats"][0]["folded"] is True


def persistence_test():
    player = {"user_id": 1, "timebank_cards_remaining": 1}
    timebank_rules.ensure_cards(player)
    assert player["timebank_cards_remaining"] == 1
    assert player["timebank_cards_total"] == 3


def source_and_browser_contract_test():
    from pathlib import Path
    import poker_simple

    app_source = Path("app.py").read_text(encoding="utf-8")
    assert "timebank_rules.install_ring(runtime_server, runtime_poker_engine)" in app_source
    assert "sitngo_action_safety.install(sitngo_runtime)" in app_source
    assert "timebank_rules.install_sitngo(sitngo_runtime)" in app_source

    source = Path("materialized_v1244/static/app.js").read_text(encoding="utf-8")
    transformed = poker_simple.transform_app_js(source)
    assert "TIME BANK" in transformed
    assert "timebank_cards_remaining" in transformed
    assert "action_clock_source==='timebank'" in transformed


def main():
    assert timebank_rules.BASE_ACTION_SECONDS == 30
    assert timebank_rules.TIMEBANK_CARD_SECONDS == 30
    assert timebank_rules.TIMEBANK_CARDS == 3
    ring_test()
    sitngo_test()
    persistence_test()
    source_and_browser_contract_test()
    print("JJ_TIMEBANK_RULES_OK", flush=True)


if __name__ == "__main__":
    main()
