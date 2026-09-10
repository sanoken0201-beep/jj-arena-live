from __future__ import annotations

from pathlib import Path


def apply(root: Path) -> None:
    path = root / "poker_engine.py"
    text = path.read_text(encoding="utf-8")
    marker = "v1.23.0 reconstructed-engine compatibility final"
    if marker in text:
        return
    addon = r'''

# v1.23.0 reconstructed-engine compatibility final.
# v1.23 is layered onto the verified production engine rather than replacing it.
# The established engine stores cumulative pot contributions on each seat,
# `_can_act` accepts one player, `_advance_round` deals exactly one street, and
# `_finish_hand` accepts the state only. These final wrappers intentionally adapt
# v1.23 to those contracts so staging never depends on invented helper APIs.
import inspect
import time


def _occupied(state: dict) -> list[dict]:
    return list(state.get("seats") or [])


def _jj_v123_actionable(state: dict) -> list[dict]:
    return [player for player in _in_hand_players(state) if _can_act(player)]


def _jj_v123_no_decision(state: dict) -> bool:
    if state.get("status") != "playing" or len(_in_hand_players(state)) <= 1:
        return False
    actors = _jj_v123_actionable(state)
    if not actors:
        return True
    if len(actors) > 1:
        return False
    actor = actors[0]
    hand = state.get("hand") or {}
    current = int(hand.get("current_bet", 0) or 0)
    paid = int(actor.get("round_bet", 0) or 0)
    return paid >= current


def _jj_v123_prepare_runout(state: dict) -> None:
    """Freeze betting while preserving cumulative contributions for settlement."""
    hand = state.get("hand") or {}
    if not hand:
        return
    # `contributed` is already the authoritative cumulative pot in the verified
    # engine. Reset only the street-facing amounts; showdown/side-pot code will
    # consume the cumulative contributions later.
    for player in _occupied(state):
        player["round_bet"] = 0
    hand["current_bet"] = 0
    hand["min_raise"] = int(state.get("big_blind", 100) or 100)
    hand["raises_in_round"] = 0
    hand["acted"] = []
    hand["raise_closed_for"] = []
    _jj_v123_queue_runout(state)


def _jj_v123_call_base_award(state: dict, winner: dict | None = None):
    """Delegate postflop settlement without assuming a historical wrapper signature."""
    fn = _jj_v123_base_award_uncontested
    params = [
        p for p in inspect.signature(fn).parameters.values()
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if len(params) >= 2:
        return fn(state, winner or (_in_hand_players(state)[0] if _in_hand_players(state) else None))
    return fn(state)


def _award_uncontested(state: dict) -> None:
    """No Flop, No Drop while preserving the normal winner/result payload."""
    hand = state.get("hand")
    alive = _in_hand_players(state)
    if not hand or len(alive) != 1:
        return _jj_v123_call_base_award(state, alive[0] if alive else None)
    if len(hand.get("board") or []) != 0:
        return _jj_v123_call_base_award(state, alive[0])

    winner = alive[0]
    pot = sum(int(player.get("contributed", 0) or 0) for player in _occupied(state))
    hand["rake"] = 0
    winner["stack"] = int(winner.get("stack", 0) or 0) + max(0, int(pot))
    state["last_result"] = {
        "type": "uncontested",
        "winners": [{
            "user_id": winner.get("user_id"),
            "name": winner.get("name") or "",
            "amount": int(pot),
        }],
        "board": list(hand.get("board") or []),
        "message": f"{winner.get('name') or ''} wins {bb_text(state, pot)}",
    }
    for player in _occupied(state):
        player["contributed"] = 0
        player["round_bet"] = 0
    _finish_hand(state, winner.get("name") or "")


def _auto_progress_if_needed(state: dict) -> None:
    """Preserve normal betting; intercept only the forced no-decision runout."""
    if state.get("status") != "playing":
        return
    alive = _in_hand_players(state)
    if len(alive) == 1:
        _award_uncontested(state)
        return
    actors = _jj_v123_actionable(state)
    if len(actors) <= 1:
        if _jj_v123_no_decision(state):
            hand = state.get("hand") or {}
            if not hand.get("forced_runout"):
                if len(hand.get("board") or []) < 5:
                    _jj_v123_prepare_runout(state)
                else:
                    _jj_v123_queue_runout(state, JJ_V123_SHOWDOWN_REVEAL_DELAY)
        return
    _jj_v123_base_auto_progress(state)


def advance_forced_runout(state: dict) -> bool:
    """Advance one visible stage using the established one-street dealer."""
    if state.get("status") != "playing":
        return False
    hand = state.get("hand") or {}
    if not hand.get("forced_runout"):
        return False
    due = float(hand.get("runout_due_at_epoch") or 0)
    if due > time.time():
        return False
    if len(_in_hand_players(state)) <= 1:
        hand.pop("forced_runout", None)
        hand.pop("runout_due_at_epoch", None)
        _award_uncontested(state)
        return True

    hand.pop("runout_due_at_epoch", None)
    if len(hand.get("board") or []) < 5:
        # Captured before v1.23 replaced `_advance_round`; this is the verified
        # production dealer and advances exactly preflop->flop, flop->turn, or
        # turn->river while preserving deck burn behavior.
        _jj_v123_base_advance_round(state)
        hand = state.get("hand") or hand
        hand["action_seat"] = None
        hand.pop("action_deadline", None)
        if len(hand.get("board") or []) < 5:
            _jj_v123_queue_runout(state, JJ_V123_RUNOUT_STREET_DELAY)
        else:
            _jj_v123_queue_runout(state, JJ_V123_SHOWDOWN_REVEAL_DELAY)
        return True

    hand.pop("forced_runout", None)
    hand.pop("runout_due_at_epoch", None)
    _showdown(state)
    return True


def _finish_hand(state: dict, winner_name: str | None = None) -> None:
    """Keep the established one-argument finish contract and add showdown hold."""
    hand_before = state.get("hand") or {}
    had_showdown = bool(hand_before.get("showdown"))
    _jj_v123_base_finish_hand(state)
    result = state.get("last_result") or {}
    is_showdown = had_showdown or result.get("type") == "showdown" or bool(result.get("showdown"))
    if is_showdown:
        hold_until = time.time() + JJ_V123_SHOWDOWN_HOLD_SECONDS
        state["showdown_hold_until_epoch"] = hold_until
        state["next_hand_at_epoch"] = max(float(state.get("next_hand_at_epoch") or 0), hold_until)
'''
    path.write_text(text.rstrip() + addon + "\n", encoding="utf-8")
