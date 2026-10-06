from __future__ import annotations

"""Spectator-only hole-card visibility for the live Ring table.

The immutable materialized poker core keeps the normal player privacy contract:
seated players receive only their own live hole cards (plus cards legitimately
revealed at showdown). Production installs this adapter on top of that contract
so an authenticated viewer who is not seated receives every seated player's
stored hole cards while remaining read-only and absent from table membership.
"""

MARKER = "spectator all-hole-card visibility 2026-10-06"


def _same_user(left, right) -> bool:
    try:
        return int(left) == int(right)
    except (TypeError, ValueError):
        return left == right


def _viewer_is_seated(state: dict, viewer_id: int | None) -> bool:
    if viewer_id is None:
        return False
    return any(
        _same_user(player.get("user_id"), viewer_id)
        for player in state.get("seats", [])
    )


def install(server, poker_engine) -> None:
    """Install spectator visibility without mutating seats or table state."""
    if bool(getattr(server, "_jj_spectator_visibility_installed", False)):
        return

    base_public_state = poker_engine.public_state

    def spectator_public_state(state: dict, viewer_id: int | None = None) -> dict:
        public = base_public_state(state, viewer_id)

        # viewer_id=None is used by internal/diagnostic callers. Never make an
        # unauthenticated/internal snapshot an all-cards feed.
        if viewer_id is None or _viewer_is_seated(state, viewer_id):
            return public

        private_by_uid = {
            str(player.get("user_id")): player
            for player in state.get("seats", [])
        }
        for visible_player in public.get("seats", []):
            private = private_by_uid.get(str(visible_player.get("user_id"))) or {}
            visible_player["cards"] = list(private.get("cards") or [])

        # Spectating is always read-only. The adapter does not add a player,
        # stack, seat, ready state, or action entitlement.
        public["legal"] = {"can_act": False}
        public["viewer_mode"] = "spectator"
        return public

    spectator_public_state.__name__ = getattr(base_public_state, "__name__", "public_state")
    spectator_public_state.__doc__ = (
        "Return player-private state, or all hole cards for an authenticated non-seated spectator."
    )

    poker_engine.public_state = spectator_public_state
    server.public_state = spectator_public_state
    server._jj_spectator_visibility_installed = True


__all__ = ["MARKER", "install"]
