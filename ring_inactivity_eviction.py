from __future__ import annotations

"""Ring inactivity eviction measured from one BB hand through the next BB hand.

A seated Ring player is removed only after they complete a full big-blind-to-
next-big-blind observation window without one successful player-submitted poker
action. Blind posting, server timeout folds, timebank consumption, reconnects,
chat and presence traffic are not activity.

The first BB observed after a new seating/deployment starts the grace window.
The second BB schedules an end-of-hand check. A successful manual action at any
point before that hand finishes cancels the removal and resets the checkpoint.
"""

from typing import Any

MARKER = "ring BB-to-next-BB inactivity eviction 2026-10-10"

_ACTION_COUNT = "_jj_inactivity_manual_actions"
_BB_CHECKPOINT = "_jj_inactivity_bb_checkpoint"
_PENDING_HAND = "_jj_inactivity_pending_hand"


def _same_user(left: Any, right: Any) -> bool:
    try:
        return int(left) == int(right)
    except (TypeError, ValueError):
        return left == right


def _player(state: dict[str, Any], user_id: int) -> dict[str, Any] | None:
    return next(
        (p for p in state.get("seats", []) if _same_user(p.get("user_id"), user_id)),
        None,
    )


def _action_count(player: dict[str, Any]) -> int:
    try:
        return max(0, int(player.get(_ACTION_COUNT, 0) or 0))
    except (TypeError, ValueError):
        return 0


def record_manual_action(state: dict[str, Any], user_id: int) -> None:
    """Record one successful player-submitted Ring decision.

    This function is called only from the guarded HTTP action path after the
    authoritative engine accepts the decision. Automatic timeout actions never
    call it, so an unattended player cannot keep a seat through forced folds.
    """
    if state.get("tournament"):
        return
    player = _player(state, user_id)
    if player is None:
        return
    player[_ACTION_COUNT] = _action_count(player) + 1


def on_hand_started(state: dict[str, Any]) -> None:
    """Open or advance the inactivity window for the player posting the BB."""
    if state.get("tournament") or state.get("status") != "playing":
        return
    hand = state.get("hand") or {}
    bb_seat = hand.get("big_blind_seat")
    if bb_seat is None:
        return
    player = next(
        (p for p in state.get("seats", []) if p.get("seat") == bb_seat and p.get("in_hand")),
        None,
    )
    if player is None:
        return

    current = _action_count(player)
    checkpoint = player.get(_BB_CHECKPOINT)
    if checkpoint is None:
        # First BB starts the grace window.
        player[_BB_CHECKPOINT] = current
        player.pop(_PENDING_HAND, None)
        return

    try:
        checkpoint_value = int(checkpoint)
    except (TypeError, ValueError):
        checkpoint_value = current
        player[_BB_CHECKPOINT] = current

    if current != checkpoint_value:
        # The player acted at least once since the previous BB checkpoint.
        # Start a fresh full-orbit window at this BB.
        player[_BB_CHECKPOINT] = current
        player.pop(_PENDING_HAND, None)
        return

    # No manual action since the previous BB started. Give the player this
    # entire BB hand to act; only its completed save may remove the seat.
    hand_id = str(hand.get("id") or "")
    if hand_id:
        player[_PENDING_HAND] = hand_id


def finalize_inactive_removals(state: dict[str, Any]) -> list[int]:
    """Remove players whose second BB hand finished without a manual action."""
    if state.get("tournament") or state.get("status") == "playing":
        return []
    hand = state.get("hand") or {}
    hand_id = str(hand.get("id") or "")
    if not hand_id:
        return []

    removed: list[int] = []
    kept: list[dict[str, Any]] = []
    for player in state.get("seats", []):
        pending = str(player.get(_PENDING_HAND) or "")
        if pending != hand_id:
            kept.append(player)
            continue

        current = _action_count(player)
        try:
            checkpoint = int(player.get(_BB_CHECKPOINT, current))
        except (TypeError, ValueError):
            checkpoint = current

        if current == checkpoint:
            try:
                removed.append(int(player.get("user_id")))
            except (TypeError, ValueError):
                pass
            continue

        # A manual action during the second BB hand cancels removal and becomes
        # the baseline for the next BB-to-next-BB inactivity window.
        player[_BB_CHECKPOINT] = current
        player.pop(_PENDING_HAND, None)
        kept.append(player)

    if removed:
        state["seats"] = kept
    return removed


def _strip_internal_state(public: dict[str, Any]) -> dict[str, Any]:
    for player in public.get("seats", []) if isinstance(public, dict) else []:
        if not isinstance(player, dict):
            continue
        player.pop(_ACTION_COUNT, None)
        player.pop(_BB_CHECKPOINT, None)
        player.pop(_PENDING_HAND, None)
    return public


def install(server: Any, engine: Any) -> None:
    if bool(getattr(server, "_jj_ring_inactivity_eviction_installed", False)):
        return

    base_start = engine.start_hand

    def start_hand(state: dict[str, Any]):
        result = base_start(state)
        on_hand_started(state)
        return result

    # Ring config currently keeps server.start_hand and engine.start_hand aligned;
    # assign both so every canonical start path uses the same inactivity hook.
    engine.start_hand = start_hand
    server.start_hand = start_hand

    base_save = server.save_table

    def save_table(state: dict[str, Any]):
        removed = finalize_inactive_removals(state)
        if removed:
            table_id = str(state.get("id") or "")
            presence = getattr(server, "table_presence", None)
            if isinstance(presence, dict):
                for user_id in removed:
                    presence.pop((table_id, int(user_id)), None)

            active_fn = getattr(server, "_jj_table_active_players", None)
            if callable(active_fn):
                active = active_fn(state)
                if len(active) < 2:
                    state["session_active"] = False
                    state["next_hand_at_epoch"] = None
                    for player in state.get("seats", []):
                        player["ready"] = False

            if isinstance(state.get("hand"), dict):
                names = []
                for user_id in removed:
                    names.append(str(user_id))
                state["hand"].setdefault("log", []).append(
                    "Inactive seat removed after a full BB-to-next-BB window"
                )
        return base_save(state)

    server.save_table = save_table

    base_public = engine.public_state

    def public_state(state: dict[str, Any], viewer_id: int | None = None):
        return _strip_internal_state(base_public(state, viewer_id))

    engine.public_state = public_state
    server.public_state = public_state

    server._jj_ring_inactivity_eviction_installed = True
    server._jj_ring_inactivity_base_start = base_start
    server._jj_ring_inactivity_base_save = base_save


__all__ = [
    "MARKER",
    "record_manual_action",
    "on_hand_started",
    "finalize_inactive_removals",
    "install",
]
