"""Reuse committed/read table snapshots only within the current event-loop turn.

This is not a replacement for authoritative DB reads. Every request/lifecycle
load still reads DB. A one-turn ticket only removes the immediate broadcast's
second read. Tickets cannot survive an await, cross tasks, or survive a failed
save. Normal reads therefore also observe maintenance/external DB updates.
"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
from copy import deepcopy
from threading import RLock


def same_state(left, right):
    """JSON-shaped equality without dumps; retain numeric-type frame changes."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(same_state(value, right[key]) for key, value in left.items())
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(same_state(a, b) for a, b in zip(left, right))
    if isinstance(left, float):
        return repr(left) == repr(right)
    return left == right


class BroadcastSnapshots:
    def __init__(self, server):
        self.server = server
        self.snapshots = {}
        self.generations = {}
        self.lock = RLock()
        self.ticket = ContextVar("jj_broadcast_snapshot", default=None)
        original_load, original_save = server.load_table, server.save_table

        def load(table_id):
            try:
                state = original_load(table_id)
                self.publish(table_id, state, write=False)
                return state
            except Exception:
                self.invalidate(table_id)
                raise

        def save(state):
            table_id = state.get("id")
            # Invalidate even if the DB commit later fails. Never expose the
            # caller's mutable state (including result_persisted on rollback).
            self.invalidate(table_id)
            result = original_save(state)
            if table_id:
                self.publish(table_id, state, write=True)
            return result

        server.load_table, server.save_table = load, save

    def invalidate(self, table_id):
        self.ticket.set(None)
        with self.lock:
            self.snapshots.pop(table_id, None)

    def publish(self, table_id, state, *, write):
        snapshot = deepcopy(state)
        with self.lock:
            if write or not same_state(self.snapshots.get(table_id), snapshot):
                self.generations[table_id] = self.generations.get(table_id, 0) + 1
            generation = self.generations[table_id]
            self.snapshots[table_id] = snapshot
        try:
            loop, owner = asyncio.get_running_loop(), asyncio.current_task()
        except RuntimeError:
            return
        ticket = [table_id, generation, owner, True]
        self.ticket.set(ticket)
        # A resumed coroutine must re-read DB; no TTL or stale background cache.
        loop.call_soon(ticket.__setitem__, 3, False)

    def for_broadcast(self, table_id):
        ticket = self.ticket.get()
        with self.lock:
            valid = (ticket and ticket[0] == table_id and ticket[2] is asyncio.current_task()
                     and ticket[3] and ticket[1] == self.generations.get(table_id)
                     and table_id in self.snapshots)
            state = deepcopy(self.snapshots[table_id]) if valid else None
            generation = ticket[1] if valid else None
        if state is None:
            state = self.server.load_table(table_id)
            generation = self.ticket.get()[1]
        else:
            # load_table historically performs this repair before broadcasting.
            repair = getattr(self.server, "_jj_v16_repair_table_state", None)
            if repair and repair(state):
                self.server.save_table(state)
                generation = self.ticket.get()[1]
        return state, generation
