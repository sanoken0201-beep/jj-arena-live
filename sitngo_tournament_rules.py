"""Tournament-only blind/button, elimination-ranking, and betting rules for JJ Sit&Go.

The materialized ring engine stays immutable. This module wraps only the
isolated Sit&Go engine and enforces the tournament contracts that differ from
cash-table convenience behavior:

* dead-button blind movement: the BB is the anchor and never skips a live player;
* heads-up transition: the surviving player who was BB most recently is never
  assigned the BB again immediately;
* the BTN/SB receives the last hole card heads-up, and the button is dealt last
  in normal flop-game dealing as well;
* TDA-style simultaneous elimination ranking, including the 2026 BBA rule that
  compares stacks after the ante is posted rather than raw pre-hand stacks;
* cumulative short all-ins re-open betting once a previously-acted player is
  facing at least the last full raise increment.

These rules intentionally do not alter ``materialized_v1244`` or ring tables.
"""
from __future__ import annotations

import time
from typing import Any

import sitngo_chip_rules


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
    the previous BB position becomes the new SB position. Those positions may
    be empty; only the BB skips forward to the next live seat. This is the
    practical dead-button rule and preserves each player's blind obligations.

    For heads-up the button must be live and is also the SB. The next BB is the
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
    # normal live BTN/SB/BB trio. Dead positions are introduced only by later
    # eliminations.
    button_seat = _next_live_seat(state, _int(state.get("button_seat"), -1), live)
    sb_seat = _next_live_seat(state, button_seat, live)
    bb_seat = _next_live_seat(state, sb_seat, live)
    return button_seat, sb_seat, bb_seat


def _deal_order(state: dict[str, Any], live: list[dict[str, Any]], button_seat: int) -> list[dict[str, Any]]:
    span = max(2, _int(state.get("max_seats"), 6))
    # First card goes to the first live seat left of the button. A live button
    # therefore receives the final card on each pass; a dead button is simply a
    # positional marker and is skipped naturally.
    return sorted(
        live,
        key=lambda p: ((_int(p.get("seat")) - int(button_seat) - 1) % span, _int(p.get("seat"))),
    )


def _prepare_chip_unit(state: dict[str, Any]) -> None:
    """Retain the tournament color-up contract even when this wrapper is outermost."""
    target = sitngo_chip_rules.chip_unit_for_level(state)
    if "chip_unit" not in state:
        state["chip_unit"] = sitngo_chip_rules.MIN_CHIP
    current = max(sitngo_chip_rules.MIN_CHIP, _int(state.get("chip_unit"), sitngo_chip_rules.MIN_CHIP))
    if target > current:
        sitngo_chip_rules.color_up(state, target)
    else:
        state["chip_unit"] = target
    sitngo_chip_rules.validate_chip_integrity(state)


def _start_tournament_hand(engine, state: dict[str, Any]) -> None:
    hold = float(state.get("showdown_hold_until_epoch") or 0)
    if hold > time.time():
        return None
    state.pop("showdown_hold_until_epoch", None)
    if state.get("status") == "playing":
        raise ValueError("hand already in progress")

    _prepare_chip_unit(state)

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
    # remaining chips fund the ante. The ante is dead money and never call
    # credit, matching the existing Sit&Go side-pot adapter.
    tournament = state.get("tournament") or {}
    ante = min(_int(bb_player.get("stack")), max(0, _int(tournament.get("bb_ante"))))
    bb_player["stack"] = _int(bb_player.get("stack")) - ante
    bb_player["all_in"] = _int(bb_player.get("stack")) == 0
    state["_ante_paid"] = ante

    # TDA 2026 simultaneous-elimination comparison under BBA uses the player's
    # hand-start stack after the ante is accounted for. Blinds are not deducted
    # from this comparison value. Only the actual ante paid is deducted, so a
    # short BB that cannot fund the full BBA is not charged a fictional amount.
    elimination_stacks = dict(starting_stacks)
    bb_key = str(bb_player["user_id"])
    elimination_stacks[bb_key] = max(0, _int(starting_stacks.get(bb_key)) - ante)

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
        # These are positional seats. Under dead-button rules the SB position
        # may be empty; the BB position must always contain a live player.
        "small_blind_seat": sb_seat,
        "big_blind_seat": bb_seat,
        "small_blind_dead": sb_player is None,
        "button_dead": _player_at(state, button_seat) is None,
        "log": [f"Hand #{state['hand_no']} started"],
        "showdown": None,
        "starting_stacks": starting_stacks,
        "elimination_stacks_after_ante": elimination_stacks,
        "elimination_ranking_basis": "tda_2026_post_ante",
        "bba_paid_for_ranking": {bb_key: ante},
        "revealed_user_ids": [],
        "result_persisted": False,
    }
    state["status"] = "playing"
    tournament["button_policy"] = "dead_button"
    tournament["elimination_ranking_policy"] = "tda_2026_post_ante"
    engine._set_next_action(state, bb_seat)
    engine._auto_progress_if_needed(state)
    sitngo_chip_rules.validate_chip_integrity(state)
    return None


def _finish_tda_ranked(self, state: dict[str, Any], original_finish) -> None:
    """Rank same-hand bustouts by the TDA comparison stack.

    Legacy hands created before this rule was deployed do not have the new
    comparison snapshot. They intentionally fall back to the previous runtime
    logic so an in-flight event is never reinterpreted mid-hand.
    """
    hand = state.get("hand") or {}
    ranking_stacks = hand.get("elimination_stacks_after_ante")
    if not isinstance(ranking_stacks, dict):
        return original_finish(self, state)

    tournament = state["tournament"]
    if state.get("status") == "playing" or tournament.get("status") == "finished":
        return
    hand_id = hand.get("id")
    if state.get("_ranked_hand") == hand_id:
        return
    state["_ranked_hand"] = hand_id

    existing = {x["user_id"] for x in tournament.get("results", [])}
    busted = [
        p for p in state.get("seats", [])
        if _int(p.get("stack")) == 0 and p.get("user_id") not in existing
    ]
    starting_stacks = hand.get("starting_stacks") or {}
    alive = [p for p in state.get("seats", []) if _int(p.get("stack")) > 0]

    def ranking_stack(player: dict[str, Any]) -> int:
        uid = str(player.get("user_id"))
        return _int(ranking_stacks.get(uid), _int(starting_stacks.get(uid)))

    for player in busted:
        uid = str(player["user_id"])
        comparison = ranking_stack(player)
        # Standard competition ranking: equal comparison stacks share the same
        # finishing place; the next distinct lower stack skips the tied place(s).
        place = len(alive) + 1 + sum(ranking_stack(other) > comparison for other in busted)
        tie_size = sum(ranking_stack(other) == comparison for other in busted)
        tournament["results"].append({
            "user_id": player["user_id"],
            "name": player["name"],
            "place": place,
            "hand_no": state["hand_no"],
            "starting_stack": _int(starting_stacks.get(uid)),
            "ranking_stack": comparison,
            "ranking_basis": hand.get("elimination_ranking_basis", "tda_2026_post_ante"),
            "tie_size": tie_size,
            "prize_points": 0,
        })

    if len(alive) == 1:
        player = alive[0]
        tournament["results"].append({
            "user_id": player["user_id"],
            "name": player["name"],
            "place": 1,
            "hand_no": state["hand_no"],
            "starting_stack": _int(player.get("stack")),
            "ranking_stack": _int(player.get("stack")),
            "ranking_basis": "winner",
            "tie_size": 1,
            "prize_points": 0,
        })
        tournament.update(status="finished", finished_at=self.db.utcnow())
        state.update(session_active=False, next_hand_at_epoch=None)
    elif len(alive) >= 2:
        state["session_active"] = True
        state["next_hand_at_epoch"] = max(
            time.time() + 1.6,
            float(state.get("showdown_hold_until_epoch") or 0),
        )


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
    """Patch only newly-created isolated Sit&Go engines and tournament ranking."""
    if getattr(sitngo_runtime, "_JJ_TOURNAMENT_RULES_INSTALLED", False):
        return

    original_make_engine = sitngo_runtime.make_engine
    original_finish = sitngo_runtime.TournamentRuntime.finish

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

    def finish(self, state):
        return _finish_tda_ranked(self, state, original_finish)

    sitngo_runtime.make_engine = make_engine
    sitngo_runtime.TournamentRuntime.finish = finish
    sitngo_runtime._JJ_TOURNAMENT_RULES_INSTALLED = True


__all__ = ["install"]
