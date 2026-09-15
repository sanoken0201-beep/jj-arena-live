from __future__ import annotations

"""Runtime-only poker table lifecycle fixes.

The immutable materialized core tracks a 15-minute table-presence timestamp for
idle cleanup. Browser clients normally remain on a table through a WebSocket,
but WebSocket pings and poker actions do not update that timestamp. A player can
therefore be actively playing for more than 15 minutes and then be removed by
the first idle-cleanup scan after a hand settles back to ``waiting``.

Treat a live authenticated table WebSocket as authoritative evidence that the
user is still present. HTTP fallback already refreshes presence through the
existing table GET endpoint, so the original idle-removal semantics remain in
place for genuinely disconnected users.
"""

from time import time
from typing import Any


def connected_user_ids(runtime_server: Any, table_id: str) -> set[int]:
    connections = getattr(getattr(runtime_server, "hub", None), "connections", {})
    rows = connections.get(table_id, []) if isinstance(connections, dict) else []
    out: set[int] = set()
    for item in rows:
        try:
            _ws, user_id = item
            out.add(int(user_id))
        except (TypeError, ValueError):
            continue
    return out


def refresh_connected_presence(runtime_server: Any, table_id: str, now_ts: float | None = None) -> set[int]:
    now = float(time() if now_ts is None else now_ts)
    users = connected_user_ids(runtime_server, table_id)
    presence = getattr(runtime_server, "table_presence", None)
    if isinstance(presence, dict):
        for user_id in users:
            presence[(table_id, user_id)] = now
    return users


def install(runtime_server: Any) -> None:
    original = runtime_server.prune_idle_players
    if getattr(original, "_jj_connected_presence_fix", False):
        return

    def prune_idle_players(state: dict, table_id: str, now_ts: float | None = None) -> bool:
        now = float(time() if now_ts is None else now_ts)
        refresh_connected_presence(runtime_server, table_id, now)
        return original(state, table_id, now_ts=now)

    prune_idle_players._jj_connected_presence_fix = True  # type: ignore[attr-defined]
    prune_idle_players._jj_original = original  # type: ignore[attr-defined]
    runtime_server.prune_idle_players = prune_idle_players


__all__ = ["connected_user_ids", "refresh_connected_presence", "install"]
