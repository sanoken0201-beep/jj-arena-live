from __future__ import annotations

"""Focused regression for the event-driven production performance layer.

This test intentionally uses an in-memory fake table runtime: it verifies that
idle tables stop polling, state writes wake the scheduler, due transitions still
fire, staged runouts remain scheduled, and one broadcast performs one chat read
regardless of connected client count.
"""

import asyncio
import time

import runtime_performance


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
            {"user_id": 1, "stack": 100, "sitting_out": False, "ready": True},
            {"user_id": 2, "stack": 100, "sitting_out": False, "ready": True},
        ],
        "hand": None,
    }
    lock = asyncio.Lock()
    load_count = 0
    save_count = 0
    chat_reads = 0
    runout_steps = 0

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

    hub = Hub()


async def _exercise_scheduler() -> None:
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


async def _exercise_broadcast() -> None:
    runtime_performance._install_broadcast_coalescing(FakeServer, FakeEngine)
    a, b = FakeWS(), FakeWS()
    FakeServer.hub.connections["table-a"] = [(a, 1), (b, 2)]
    before = FakeServer.chat_reads
    await FakeServer.hub.broadcast("table-a")
    assert FakeServer.chat_reads - before == 1, "chat was queried once per client instead of once per broadcast"
    assert len(a.messages) == 1 and len(b.messages) == 1
    assert a.messages[0]["state"]["user_id"] == 1
    assert b.messages[0]["state"]["user_id"] == 2


def main() -> None:
    import psycopg_pool  # noqa: F401 - proves the production pool extra is installed.

    asyncio.run(_exercise_scheduler())
    asyncio.run(_exercise_broadcast())
    print("runtime performance smoke test passed")


if __name__ == "__main__":
    main()
