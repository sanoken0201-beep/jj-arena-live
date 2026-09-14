from __future__ import annotations

"""Correct cash-game rake settlement for uncalled contributions.

The canonical materialized v1.24.4 engine intentionally remains immutable.
This integration patch fixes one settlement edge case at runtime: a unique
highest contribution can contain chips that no opponent matched. Those chips
must be returned before the contested pot is built and before rake is computed.

The existing JJ Arena rules remain unchanged:
- 10% rake by default;
- 5bb hand cap by default;
- integer-chip round-down;
- No Flop, No Drop for preflop uncontested pots;
- existing main/side-pot, split-pot and odd-chip allocation.
"""

from typing import Any

_INSTALLED = False


def _chip(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def refund_uncalled_contribution(state: dict[str, Any]) -> int:
    """Return the unique unmatched top layer and remove it from pot accounting.

    For contribution levels [1000, 500], only 500 from each player is contested;
    the extra 500 belongs back to the 1000-contributor.  More generally, when
    exactly one player has the highest contribution, the difference between the
    highest and second-highest contribution is uncalled.

    The operation is naturally idempotent: after the refund, the two highest
    contribution levels are tied, so a second call returns zero.
    """

    seats = list(state.get("seats") or [])
    if len(seats) < 2:
        return 0

    levels = [(player, _chip(player.get("contributed"))) for player in seats]
    highest = max((amount for _player, amount in levels), default=0)
    if highest <= 0:
        return 0

    leaders = [player for player, amount in levels if amount == highest]
    if len(leaders) != 1:
        return 0

    second_highest = max(
        (amount for _player, amount in levels if amount < highest),
        default=0,
    )
    refund = highest - second_highest
    if refund <= 0:
        return 0

    player = leaders[0]
    player["contributed"] = highest - refund
    player["stack"] = _chip(player.get("stack")) + refund

    # Any uncalled layer can only belong to the current betting round.  During a
    # staged all-in runout round_bet may already be zero, so never drive it below
    # zero.  Settlement is ending the hand, but clearing all_in when chips return
    # keeps the state internally truthful until the normal finish-hand reset.
    player["round_bet"] = max(0, _chip(player.get("round_bet")) - refund)
    if _chip(player.get("stack")) > 0:
        player["all_in"] = False

    return refund


def install(poker_engine) -> None:
    """Install the settlement correction exactly once on the runtime engine."""

    global _INSTALLED
    if _INSTALLED:
        return

    original_showdown = poker_engine._showdown
    original_award_uncontested = poker_engine._award_uncontested

    def showdown_with_uncalled_refund(state: dict[str, Any]):
        refund_uncalled_contribution(state)
        return original_showdown(state)

    def uncontested_with_uncalled_refund(state: dict[str, Any], *args, **kwargs):
        hand = state.get("hand") or {}
        # Preserve the existing No Flop, No Drop payload exactly.  Preflop pots
        # are unraked already, so normalizing the blind imbalance would only
        # change gross-pot/result presentation without affecting correctness.
        if len(hand.get("board") or []) > 0:
            refund_uncalled_contribution(state)
        return original_award_uncontested(state, *args, **kwargs)

    poker_engine._showdown = showdown_with_uncalled_refund
    poker_engine._award_uncontested = uncontested_with_uncalled_refund
    _INSTALLED = True
