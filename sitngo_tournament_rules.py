"""Tournament-only blind/button and betting-reopen rules for JJ Sit&Go.

The materialized ring engine stays immutable.  This module wraps only the
isolated Sit&Go engine and enforces the tournament contracts that differ from
cash-table convenience behavior:

* dead-button blind movement: the BB is the anchor and never skips a live player;
* heads-up transition: the surviving player who was BB most recently is never
  assigned the BB again immediately;
* the BTN/SB receives the last hole card heads-up, and the button is dealt last
  in normal flop-game dealing as well;
* cumulative short all-ins re-open betting once a previously-acted player is
  facing at least the last full raise increment.

These rules intentionally do not alter ``materialized_v1244`` or ring tables.
"""
from __future__ import annotations

import time
from typing import Any


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _live_players(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for p in state.get("seats", []) if _int(p.get("stack")) > 0]


def _next_live_seat(state: dict[str, Any], after: int, live: list[dict[str, Any]]) -> int:
    occupied = {_int(p.get("seat")): p for p in live}
    span = max(2, _int(state.get("max_seats"), 6))
    for step in range(1, span + 1):
        seat = (int(after) + step) % span
        if seat in occupied:
            return seat
    raise RuntimeError("Sit&Go has no live seat for blind movement")


def _player_at(state: dict[str, Any], seat: int) -> dict[str, Any] | None:
    return next(
        (p for p in state.get("seats", []) if _int(p.get("seat"), -1) == int(seat) and _int(p.get("stack")) > 0),
        None,
    )


def _positions(state: dict[str, Any], live: list[dict[str, Any]]) -> tuple[int, int, int]:
    """Return (button position, SB position, live BB seat).

    For 3+ players the previous SB position becomes the new button position and
    the previous BB position becomes the new SB position.  Those positions may
    be empty; only the BB skips forward to the next live seat.  This is the
    practical dead-button rule and preserves each player's blind obligations.

    For heads-up the button must be live and is also the SB.  The next BB is the
    first live player clockwise from the previous BB, which automatically avoids
    assigning the same surviving player the BB twice when a table changes from
    three players to two.
    """
    if len(live) < 2:
        raise RuntimeError("Sit&Go blind movement requires at least two live players")

    hand = state.get("hand") or {}
    previous_bb = hand.get("big_blind_seat")
    previous_sb = hand.get("small_blind_seat")
    has_previous = _int(state.get("hand_no")) > 0 and previous_bb is not None

    if len(live) == 2:
        if has_previous:
            bb_seat = _next_live_seat(state, _int(previous_bb), live)
            button_seat = _next_live_seat(state, bb_seat, live)
        else:
            button_seat = _next_live_seat(state, _int(state.get("button_seat"), -1), live)
            bb_seat = _next_live_seat(state, button_seat, live)
        return button_seat, button_seat, bb_seat

    if has_previous and previous_sb is not None:
        bb_seat = _next_live_seat(state, _int(previous_bb), live)
        return (
            _int(previous_sb) % _int(state.get("max_seats"), 6),
            _int(previous_bb) % _int(state.get("max_seats"), 6),
            bb_seat,
        )

    # First hand: seats were already randomized at tournament start, so choose a
    # normal live BTN/SB/BB trio.  Dead positions are introduced only by later
    # eliminations.
    button_seat = _next_live_seat(state, _int(state.get("button_seat"), -1), live)
    sb_seat = _next_live_seat(state, button_seat, live)
    bb_seat = _next_live_seat(state, sb_seat, live)
    return button_seat, sb_seat, bb_seat


def _deal_order(state: dict[str, Any], live: list[dict[str, Any]], button_seat: int) -> list[dict[str, Any]]:
    span = max(2, _int(state.get("max_seats"), 6))
    # First card goes to the first live seat left of the button.  A live button
    # therefore receives the final card on each pass; a dead button is simply a
    # positional marker and is skipped naturally.
    return sorted(
        live,
        key=lambda p: ((_int(p.get("seat")) - int(button_seat) - 1) % span, _int(p.get("seat"))),
    )


def _start_tournament_hand(engine, state: dict[str, Any]) -> None:
    hold = float(state.get("showdown_hold_until_epoch") or 0)
    if hold > time.time():
        return None
    state.pop("showdown_hold_until_epoch", None)
    if state.get("status") == "playing":
        raise ValueError("hand already in progress")

    # Tournament players cannot voluntarily sit out or leave to avoid blinds.
    for player in state.get("seats", []):
        player.update(sitting_out=False, sit_out_next=False, leave_after_hand=False)

    live = _live_players(state)
    if len(live) < 2:
        raise ValueError("at least two players with chips are required")

    starting_stacks = {str(p["user_id"]): _int(p.get("stack")) for p in live}
    button_seat, sb_seat, bb_seat = _positions(state, live)

    for player in state.get("seats", []):
        player.update(
            in_hand=_int(player.get("stack")) > 0,
            folded=False,
            all_in=False,
            round_bet=0,
            contributed=0,
            cards=[],
            ready=False,
        )

    state["next_hand_at_epoch"] = None
    state["last_result"] = None
    state["hand_no"] = _int(state.get("hand_no")) + 1
    state["button_seat"] = button_seat
    state["_ante_paid"] = 0

    deck = engine.new_deck()
    for _ in range(2):
        for player in _deal_order(state, live, button_seat):
            player["cards"].append(deck.pop())

    sb_player = _player_at(state, sb_seat)
    bb_player = _player_at(state, bb_seat)
    if bb_player is None:
        raise RuntimeError("Sit&Go dead-button movement produced a dead big blind")

    if sb_player is not None:
        engine._post_blind(sb_player, _int(state.get("small_blind")))
    engine._post_blind(bb_player, _int(state.get("big_blind")))

    # Big-blind-first BBA: if the BB is short, the blind is satisfied before any
    # remaining chips fund the ante.  The ante is dead money and never call
    # credit, matching the existing Sit&Go side-pot adapter.
    tournament = state.get("tournament") or {}
    ante = min(_int(bb_player.get("stack")), max(0, _int(tournament.get("bb_ante"))))
    bb_player["stack"] = _int(bb_player.get("stack")) - ante
    bb_player["all_in"] = _int(bb_player.get("stack")) == 0
    state["_ante_paid"] = ante

    state["hand"] = {
        "id": f"{state['id']}-{state['hand_no']}-{engine.uuid.uuid4().hex[:10]}",
        "phase": "preflop",
        "deck": deck,
        "board": [],
        "current_bet": max(
            _int(sb_player.get("round_bet")) if sb_player else 0,
            _int(bb_player.get("round_bet")),
            _int(state.get("big_blind")),
        ),
        "min_raise": _int(state.get("big_blind")),
        "acted": [],
        "raise_closed_for": [],
        "action_seat": None,
        # These are positional seats.  Under dead-button rules the SB position
        # may be empty; the BB position must always contain a live player.
        "small_blind_seat": sb_seat,
        "big_blind_seat": bb_seat,
        "small_blind_dead": sb_player is None,
        "button_dead": _player_at(state, button_seat) is None,
        "log": [f"Hand #{state['hand_no']} started"],
        "showdown": None,
        "starting_stacks": starting_stacks,
        "revealed_user_ids": [],
        "result_persisted": False,
    }
    state["status"] = "playing"
    tournament["button_policy"] = "dead_button"
    engine._set_next_action(state, bb_seat)
    engine._auto_progress_if_needed(state)
    return None


def _cumulative_reopen(state: dict[str, Any], user_id: int) -> bool:
    hand = state.get("hand") or {}
    closed = set(hand.get("raise_closed_for") or [])
    if int(user_id) not in closed:
        return False
    player = next((p for p in state.get("seats", []) if _int(p.get("user_id"), -1) == int(user_id)), None)
    if player is None:
        return False
    faced = max(0, _int(hand.get("current_bet")) - _int(player.get("round_bet")))
    full_raise = max(1, _int(hand.get("min_raise"), _int(state.get("big_blind"), 1)))
    return faced >= full_raise


def install(sitngo_runtime) -> None:
    """Patch only newly-created isolated Sit&Go engines."""
    if getattr(sitngo_runtime, "_JJ_TOURNAMENT_RULES_INSTALLED", False):
        return

    original_make_engine = sitngo_runtime.make_engine

    def make_engine():
        engine = original_make_engine()
        original_start = engine.start_hand
        original_legal = engine.legal_actions
        original_action = engine.apply_action

        def start_hand(state, *args, **kwargs):
            if state.get("tournament"):
                return _start_tournament_hand(engine, state)
            return original_start(state, *args, **kwargs)

        def legal_actions(state, user_id):
            if not state.get("tournament") or not _cumulative_reopen(state, int(user_id)):
                return original_legal(state, user_id)
            hand = state.get("hand") or {}
            saved = list(hand.get("raise_closed_for") or [])
            hand["raise_closed_for"] = [uid for uid in saved if _int(uid, -1) != int(user_id)]
            try:
                legal = dict(original_legal(state, user_id) or {})
            finally:
                hand["raise_closed_for"] = saved
            legal["reopened_by_cumulative_short_allins"] = True
            return legal

        def apply_action(state, user_id, action, amount=None):
            if state.get("tournament") and _cumulative_reopen(state, int(user_id)):
                hand = state.get("hand") or {}
                hand["raise_closed_for"] = [
                    uid for uid in hand.get("raise_closed_for", []) if _int(uid, -1) != int(user_id)
                ]
            return original_action(state, user_id, action, amount)

        engine.start_hand = start_hand
        engine.legal_actions = legal_actions
        engine.apply_action = apply_action
        return engine

    sitngo_runtime.make_engine = make_engine
    sitngo_runtime._JJ_TOURNAMENT_RULES_INSTALLED = True


__all__ = ["install"]
