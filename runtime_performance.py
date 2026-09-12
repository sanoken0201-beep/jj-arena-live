from __future__ import annotations

"""Low-risk production runtime performance optimizations for JJ Arena.

The goals are deliberately narrow:
- reuse PostgreSQL connections instead of opening a brand-new session per query;
- replace the 0.18s/0.5s table polling loops with an event-driven lifecycle loop;
- fetch table chat once per broadcast and fan websocket updates out concurrently.

Game rules, action deadlines, staged runout timing, next-hand delay, ranking logic,
and the public API remain unchanged.
"""

import asyncio
import atexit
import os
import threading
import time
from contextlib import contextmanager
from typing import Any

_INSTALLED = False
_POOL = None
_POOL_LOCK = threading.Lock()
_STATE_EVENT: asyncio.Event | None = None
_STATE_EVENT_LOOP: asyncio.AbstractEventLoop | None = None


def _database_url(db) -> str:
    url = str(getattr(db, "DATABASE_URL", "") or "").strip()
    if "render.com" in url and "sslmode=" not in url and "internal" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return url


def _int_env(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def _float_env(name: str, default: float, low: float, high: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def _install_postgres_pool(db) -> None:
    """Swap db.connect() for a small bounded psycopg connection pool.

    A small pool is intentional: JJ Arena's queries are short, and the database
    is currently the constrained resource. Reuse eliminates connection setup
    cost while the bound prevents a request burst from stampeding PostgreSQL.
    """
    if not bool(getattr(db, "IS_POSTGRES", False)):
        return

    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    min_size = _int_env("JJ_DB_POOL_MIN", 1, 1, 4)
    max_size = _int_env("JJ_DB_POOL_MAX", 4, min_size, 12)
    timeout = _float_env("JJ_DB_POOL_TIMEOUT", 10.0, 1.0, 30.0)

    def get_pool():
        global _POOL
        if _POOL is not None:
            return _POOL
        with _POOL_LOCK:
            if _POOL is None:
                _POOL = ConnectionPool(
                    conninfo=_database_url(db),
                    min_size=min_size,
                    max_size=max_size,
                    timeout=timeout,
                    max_waiting=64,
                    kwargs={"row_factory": dict_row},
                    open=True,
                    name="jj-arena-db",
                )
                atexit.register(_POOL.close)
        return _POOL

    @contextmanager
    def pooled_connect():
        pool = get_pool()
        with pool.connection() as raw:
            con = db.PgConnection(raw)
            try:
                yield con
                raw.commit()
            except Exception:
                raw.rollback()
                raise

    db.connect = pooled_connect


def _signal_table_state_change() -> None:
    event = _STATE_EVENT
    loop = _STATE_EVENT_LOOP
    if event is None or loop is None or loop.is_closed():
        return
    try:
        loop.call_soon_threadsafe(event.set)
    except RuntimeError:
        pass


def _candidate_due(current: float | None, value: Any) -> float | None:
    try:
        due = float(value or 0)
    except (TypeError, ValueError):
        return current
    if due <= 0:
        return current
    return due if current is None else min(current, due)


def _install_event_driven_lifecycle(db, server, poker_engine) -> None:
    """Replace continuous table polling with exact-time/event-driven scheduling.

    The old runtime read both table rows every 180ms for staged runouts and every
    500ms for next-hand dealing even when nobody was playing. Every poker state
    write now signals this scheduler. It then sleeps until the exact next due
    transition (or indefinitely if nothing is scheduled), preserving timing
    while eliminating idle database traffic.
    """
    original_save_table = server.save_table

    def save_table_and_signal(state):
        original_save_table(state)
        _signal_table_state_change()

    server.save_table = save_table_and_signal

    async def lifecycle_loop():
        global _STATE_EVENT, _STATE_EVENT_LOOP
        _STATE_EVENT_LOOP = asyncio.get_running_loop()
        _STATE_EVENT = asyncio.Event()
        _STATE_EVENT.set()
        try:
            while True:
                _STATE_EVENT.clear()
                next_due: float | None = None

                for table_id, _table_name in db.FIXED_TABLES:
                    changed = False
                    try:
                        async with server.get_table_lock(table_id):
                            state = server.load_table(table_id)
                            now = time.time()

                            # Preserve the established automatic next-hand lifecycle.
                            if state.get("status") == "waiting" and bool(state.get("session_active")):
                                active = server._jj_table_active_players(state)
                                if len(active) < 2:
                                    state["session_active"] = False
                                    state["next_hand_at_epoch"] = None
                                    for player in state.get("seats", []):
                                        player["ready"] = False
                                    server.save_table(state)
                                    changed = True
                                else:
                                    due = state.get("next_hand_at_epoch")
                                    if due is None:
                                        due = now + 1.6
                                        state["next_hand_at_epoch"] = due
                                        server.save_table(state)
                                        changed = True
                                        next_due = _candidate_due(next_due, due)
                                    else:
                                        try:
                                            due_value = float(due)
                                        except (TypeError, ValueError):
                                            due_value = now
                                        if due_value <= now:
                                            try:
                                                poker_engine.start_hand(state)
                                            except ValueError:
                                                state["session_active"] = False
                                                state["next_hand_at_epoch"] = None
                                            else:
                                                server.arm_action_deadline(state)
                                            server.save_table(state)
                                            changed = True
                                        else:
                                            next_due = _candidate_due(next_due, due_value)

                            # Preserve the v1.23 staged all-in runout presentation.
                            hand = state.get("hand") or {}
                            runout_due = hand.get("runout_due_at_epoch")
                            if (
                                state.get("status") == "playing"
                                and hand.get("forced_runout")
                                and runout_due
                            ):
                                try:
                                    runout_due_value = float(runout_due)
                                except (TypeError, ValueError):
                                    runout_due_value = now
                                if runout_due_value <= now:
                                    if server.advance_forced_runout(state):
                                        # Forced runout frames contain no player decision.
                                        # Keep the existing behavior: no action deadline here.
                                        server.save_table(state)
                                        changed = True
                                        hand = state.get("hand") or {}
                                        next_due = _candidate_due(
                                            next_due, hand.get("runout_due_at_epoch")
                                        )
                                else:
                                    next_due = _candidate_due(next_due, runout_due_value)

                        if changed:
                            await server.hub.broadcast(table_id)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        try:
                            import resilience

                            resilience.record_error(
                                db,
                                "table_lifecycle",
                                f"{type(exc).__name__}: {exc}",
                                path=table_id,
                            )
                        except Exception:
                            pass

                # A state write that happened while scanning must be handled now.
                if _STATE_EVENT.is_set():
                    continue

                if next_due is None:
                    await _STATE_EVENT.wait()
                    continue

                timeout = max(0.0, next_due - time.time())
                try:
                    await asyncio.wait_for(_STATE_EVENT.wait(), timeout=timeout)
                except TimeoutError:
                    pass
        finally:
            _STATE_EVENT = None
            _STATE_EVENT_LOOP = None

    # FastAPI's lifespan function resolves this module global when it starts,
    # so replacing it here prevents the legacy 0.18s/0.5s polling tasks from
    # ever being spawned in production.
    server.auto_deal_loop = lifecycle_loop


def _install_broadcast_coalescing(server, poker_engine) -> None:
    """Read chat once and fan websocket state to clients concurrently."""

    async def broadcast(self, table_id: str):
        try:
            state = server.load_table(table_id)
            messages = server.get_messages(table_id)
        except Exception:
            return

        connections = list(self.connections.get(table_id, []))
        if not connections:
            return

        async def send_one(ws, user_id: int):
            await ws.send_json(
                {
                    "type": "state",
                    "state": poker_engine.public_state(state, user_id),
                    "messages": messages,
                }
            )

        results = await asyncio.gather(
            *(send_one(ws, uid) for ws, uid in connections),
            return_exceptions=True,
        )
        for (ws, _uid), result in zip(connections, results):
            if isinstance(result, BaseException):
                self.remove(table_id, ws)

    server.Hub.broadcast = broadcast


def _install_indexes(db) -> None:
    """Add only read-path indexes that are safe and idempotent."""
    statements = (
        "CREATE INDEX IF NOT EXISTS idx_table_messages_table_id_id ON table_messages(table_id,id DESC)",
        "CREATE INDEX IF NOT EXISTS idx_online_hands_played_at ON online_hands(played_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_online_hand_results_hand_id ON online_hand_results(hand_id)",
    )
    try:
        with db.connect() as con:
            for statement in statements:
                try:
                    con.execute(statement)
                except Exception:
                    # Older/partial test schemas may not contain every production table.
                    pass
    except Exception:
        pass


def install(db, server, poker_engine) -> None:
    """Install the production optimizations exactly once."""
    global _INSTALLED
    if _INSTALLED:
        return

    _install_postgres_pool(db)
    _install_event_driven_lifecycle(db, server, poker_engine)
    _install_broadcast_coalescing(server, poker_engine)
    _install_indexes(db)
    _INSTALLED = True


__all__ = ["install"]
