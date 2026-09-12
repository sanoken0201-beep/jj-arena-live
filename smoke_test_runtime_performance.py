from __future__ import annotations

"""Focused regression for the production performance layers.

This test intentionally uses an in-memory fake table runtime: it verifies that
idle tables stop polling, state writes wake the lifecycle scheduler, due
transitions still fire, staged runouts remain scheduled, action timeouts are
exact-time/event-driven, and websocket chat/state work is separated. It also
guards the browser asset cache and shared public-gateway HTTP client.
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import runtime_performance

ROOT = Path(__file__).resolve().parent


class FakeDB:
    IS_POSTGRES = False
    FIXED_TABLES = (("table-a", "Table A"),)


class FakeEngine:
    started = 0

    @classmethod
    def start_hand(cls, state):
        cls.started += 1
        state["status"] = "playing"
        state["next_hand_at_epoch"] = None
        state["hand"] = {"forced_runout": False, "runout_due_at_epoch": None}

    @staticmethod
    def public_state(state, user_id):
        return {"status": state.get("status"), "user_id": user_id}


class FakeWS:
    def __init__(self):
        self.messages = []

    async def send_json(self, payload):
        self.messages.append(payload)


class FakeServer:
    state = {
        "status": "waiting",
        "session_active": False,
        "next_hand_at_epoch": None,
        "seats": [
            {"user_id": 1, "seat": 0, "name": "A", "stack": 100, "sitting_out": False, "ready": True},
            {"user_id": 2, "seat": 1, "name": "B", "stack": 100, "sitting_out": False, "ready": True},
        ],
        "hand": None,
    }
    lock = asyncio.Lock()
    load_count = 0
    save_count = 0
    chat_reads = 0
    runout_steps = 0
    TABLE_IDLE_SECONDS = 15 * 60
    SERVER_STARTED_AT = time.time()
    table_presence = {}

    @classmethod
    def get_table_lock(cls, _table_id):
        return cls.lock

    @classmethod
    def load_table(cls, _table_id):
        cls.load_count += 1
        return cls.state

    @classmethod
    def save_table(cls, _state):
        cls.save_count += 1

    @classmethod
    def touch_presence(cls, table_id, user_id):
        cls.table_presence[(table_id, int(user_id))] = time.time()

    @classmethod
    def prune_idle_players(cls, _state, _table_id, _now=None):
        return False

    @staticmethod
    def _jj_table_active_players(state):
        return [
            p
            for p in state.get("seats", [])
            if int(p.get("stack", 0)) > 0 and not bool(p.get("sitting_out"))
        ]

    @staticmethod
    def arm_action_deadline(state):
        state["deadline_armed"] = True

    @staticmethod
    def legal_actions(_state, _user_id):
        return {"can_act": True, "can_check": True}

    @staticmethod
    def apply_action(state, _user_id, _action):
        state["status"] = "waiting"
        state["hand"] = None

    @classmethod
    def advance_forced_runout(cls, state):
        cls.runout_steps += 1
        state["hand"]["forced_runout"] = False
        state["hand"]["runout_due_at_epoch"] = None
        return True

    @classmethod
    def get_messages(cls, _table_id):
        cls.chat_reads += 1
        return [{"body": "hello"}]

    class Hub:
        def __init__(self):
            self.connections = {}

        def remove(self, table_id, ws):
            self.connections[table_id] = [
                (w, uid) for w, uid in self.connections.get(table_id, []) if w is not ws
            ]

        async def broadcast(self, _table_id):
            return None

    hub = Hub()


async def _exercise_scheduler() -> None:
    FakeServer.load_count = 0
    FakeServer.save_count = 0
    FakeEngine.started = 0
    FakeServer.runout_steps = 0
    FakeServer.state = {
        "status": "waiting",
        "session_active": False,
        "next_hand_at_epoch": None,
        "seats": [
            {"user_id": 1, "seat": 0, "name": "A", "stack": 100, "sitting_out": False, "ready": True},
            {"user_id": 2, "seat": 1, "name": "B", "stack": 100, "sitting_out": False, "ready": True},
        ],
        "hand": None,
    }
    runtime_performance._install_event_driven_lifecycle(FakeDB, FakeServer, FakeEngine)

    task = asyncio.create_task(FakeServer.auto_deal_loop())
    try:
        # Idle tables should be read once and then sleep indefinitely rather than
        # returning to the database every 180ms/500ms.
        await asyncio.sleep(0.08)
        idle_reads = FakeServer.load_count
        assert idle_reads <= 2, f"idle scheduler kept polling: {idle_reads} reads"

        # A normal table state write wakes the scheduler immediately. The exact
        # next-hand timestamp is then respected without periodic polling.
        due = time.time() + 0.08
        FakeServer.state["session_active"] = True
        FakeServer.state["next_hand_at_epoch"] = due
        FakeServer.save_table(FakeServer.state)
        await asyncio.sleep(0.14)
        assert FakeEngine.started == 1, "next hand did not start at its scheduled due time"
        assert FakeServer.state.get("deadline_armed") is True

        # A staged all-in runout uses the same exact-time scheduler.
        FakeServer.state["hand"] = {
            "forced_runout": True,
            "runout_due_at_epoch": time.time() + 0.06,
        }
        FakeServer.save_table(FakeServer.state)
        await asyncio.sleep(0.11)
        assert FakeServer.runout_steps == 1, "forced runout frame was not advanced"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def _exercise_timeout_scheduler() -> None:
    FakeServer.load_count = 0
    FakeServer.table_presence = {
        ("table-a", 1): time.time(),
        ("table-a", 2): time.time(),
    }
    deadline = datetime.now(timezone.utc) + timedelta(seconds=0.08)
    FakeServer.state = {
        "status": "playing",
        "session_active": True,
        "next_hand_at_epoch": None,
        "seats": [
            {"user_id": 1, "seat": 0, "name": "A", "stack": 100, "sitting_out": False, "ready": True},
            {"user_id": 2, "seat": 1, "name": "B", "stack": 100, "sitting_out": False, "ready": True},
        ],
        "hand": {
            "action_deadline": deadline.isoformat(),
            "action_seat": 0,
            "log": [],
        },
    }
    runtime_performance._install_event_driven_timeout_loop(FakeDB, FakeServer)

    task = asyncio.create_task(FakeServer.timeout_loop())
    try:
        await asyncio.sleep(0.035)
        early_reads = FakeServer.load_count
        assert early_reads <= 2, f"timeout scheduler kept polling before deadline: {early_reads} reads"
        await asyncio.sleep(0.10)
        assert FakeServer.state["status"] == "waiting", "deadline did not execute the timeout action"
        assert FakeServer.state["seats"][0].get("sitting_out") is True
        assert FakeServer.state.get("session_active") is False
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def _exercise_broadcast() -> None:
    runtime_performance._LAST_BROADCAST_STATE.clear()
    runtime_performance._install_broadcast_coalescing(FakeServer, FakeEngine)
    FakeServer.state = {
        "status": "waiting",
        "seats": [],
        "hand": None,
    }
    FakeServer.chat_reads = 0
    a, b = FakeWS(), FakeWS()
    FakeServer.hub.connections["table-a"] = [(a, 1), (b, 2)]

    # First broadcast remains compatible: one shared chat read plus personalized state.
    await FakeServer.hub.broadcast("table-a")
    assert FakeServer.chat_reads == 1
    assert a.messages[-1]["type"] == "state" and b.messages[-1]["type"] == "state"
    assert a.messages[-1]["state"]["user_id"] == 1
    assert b.messages[-1]["state"]["user_id"] == 2
    assert a.messages[-1]["messages"] == [{"body": "hello"}]

    # No table-state change means chat-only fanout: no personalized state rebuild.
    await FakeServer.hub.broadcast("table-a")
    assert FakeServer.chat_reads == 2
    assert a.messages[-1]["type"] == "chat" and b.messages[-1]["type"] == "chat"

    # A real state change sends state only and performs no chat query.
    FakeServer.state["status"] = "playing"
    before = FakeServer.chat_reads
    await FakeServer.hub.broadcast("table-a")
    assert FakeServer.chat_reads == before, "state broadcast performed a redundant chat query"
    assert a.messages[-1]["type"] == "state"
    assert "messages" not in a.messages[-1]


def _guard_client_and_gateway_efficiency() -> None:
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    proxy_source = (ROOT / "public_proxy.py").read_text(encoding="utf-8")

    assert "renderPokerRoom();refreshMe().catch(()=>{})" in app_source
    assert '"renderPokerRoom()"' in app_source
    assert "m.type==='chat'" in app_source
    assert "renderTableChat()" in app_source
    assert 'js = js.replace("showApp();await refreshAll()", "showApp()")' in app_source
    assert app_source.count("@lru_cache(maxsize=1)") >= 4
    assert "encoded = body.encode(\"utf-8\")" in app_source
    assert "jj-arena-live-v66" in app_source
    assert "/static/app.js?v=66" in app_source

    assert "_HTTP_CLIENT = httpx.AsyncClient(" in proxy_source
    assert "response = await _HTTP_CLIENT.request(" in proxy_source
    assert "await _HTTP_CLIENT.get(" in proxy_source
    assert "async with httpx.AsyncClient" not in proxy_source


def main() -> None:
    import psycopg_pool  # noqa: F401 - proves the production pool extra is installed.

    asyncio.run(_exercise_scheduler())
    asyncio.run(_exercise_timeout_scheduler())
    asyncio.run(_exercise_broadcast())
    _guard_client_and_gateway_efficiency()
    print("runtime performance smoke test passed")


if __name__ == "__main__":
    main()
