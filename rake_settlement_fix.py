from __future__ import annotations

"""Correct cash-game rake settlement for uncalled contributions.

The canonical materialized v1.24.4 engine intentionally remains immutable.
This integration patch keeps the production settlement path poker-correct:
uncalled chips are returned before contested-pot accounting, then the configured
rake is applied only to chips that were actually contested.

JJ Arena rake rules:
- 5% rake;
- 3bb cap per hand;
- integer-chip round-down;
- No Flop, No Drop for preflop uncontested pots;
- existing main/side-pot, split-pot and odd-chip allocation.
"""

import json
import sys
from typing import Any

_INSTALLED = False
RAKE_PERCENT = 0.05
RAKE_CAP_BB = 3


def _chip(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def apply_rake_policy(state: dict[str, Any]) -> bool:
    """Apply the configured 5% / 3bb policy without changing settlement logic."""
    big_blind = max(1, _chip(state.get("big_blind")))
    cap = big_blind * RAKE_CAP_BB
    changed = (
        float(state.get("rake_percent", -1)) != RAKE_PERCENT
        or _chip(state.get("rake_cap")) != cap
    )
    state["rake_percent"] = RAKE_PERCENT
    state["rake_cap"] = cap
    return changed


def _install_runtime_policy() -> None:
    """Keep runtime constants and persisted fixed-table values on one policy."""
    db = sys.modules.get("db")
    if db is None:
        return

    db.RAKE_PERCENT = RAKE_PERCENT
    db.RAKE_CAP_BB = RAKE_CAP_BB

    fixed_tables = tuple(getattr(db, "FIXED_TABLES", ()) or ())
    if not fixed_tables:
        return

    with db.connect() as con:
        for table_id, _name in fixed_tables:
            row = con.execute("SELECT state_json FROM tables WHERE id=?", (table_id,)).fetchone()
            if not row:
                continue
            state = json.loads(row["state_json"])
            if not apply_rake_policy(state):
                continue
            con.execute(
                "UPDATE tables SET state_json=? WHERE id=?",
                (json.dumps(state, ensure_ascii=False), table_id),
            )


def refund_uncalled_contribution(state: dict[str, Any]) -> int:
    """Return the unique unmatched top layer and remove it from pot accounting.

    For contribution levels [1000, 500], only 500 from each player is contested;
    the extra 500 belongs back to the 1000-contributor. More generally, when
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

    # Any uncalled layer can only belong to the current betting round. During a
    # staged all-in runout round_bet may already be zero, so never drive it below
    # zero. Settlement is ending the hand, but clearing all_in when chips return
    # keeps the state internally truthful until the normal finish-hand reset.
    player["round_bet"] = max(0, _chip(player.get("round_bet")) - refund)
    if _chip(player.get("stack")) > 0:
        player["all_in"] = False

    return refund


def _complete_uncontested_result_metadata(poker_engine, state: dict[str, Any], gross_pot: int) -> None:
    """Keep No-Flop-No-Drop results compatible with hand/result persistence.

    The v1.23 canonical no-flop wrapper predates the online-hand persistence
    fields and therefore omits ``gross_pot``, ``rake`` and ``net_results``.
    Fill only those settlement metadata fields after the canonical award path;
    chip movement and winner selection remain canonical.
    """

    result = state.get("last_result")
    if not isinstance(result, dict):
        return
    result["gross_pot"] = int(gross_pot)
    result["rake"] = 0
    attach = getattr(poker_engine, "_attach_net_results", None)
    if callable(attach):
        attach(state)


def install(poker_engine) -> None:
    """Install the rake policy and settlement correction exactly once."""

    global _INSTALLED
    if _INSTALLED:
        return

    _install_runtime_policy()

    original_showdown = poker_engine._showdown
    original_award_uncontested = poker_engine._award_uncontested
    original_rake_amount = getattr(poker_engine, "_rake_amount", None)

    if original_rake_amount is not None:
        def rake_amount_with_policy(state: dict[str, Any], pot_amount: int):
            apply_rake_policy(state)
            return original_rake_amount(state, pot_amount)

        poker_engine._rake_amount = rake_amount_with_policy

    def showdown_with_uncalled_refund(state: dict[str, Any]):
        apply_rake_policy(state)
        refund_uncalled_contribution(state)
        return original_showdown(state)

    def uncontested_with_uncalled_refund(state: dict[str, Any], *args, **kwargs):
        apply_rake_policy(state)
        hand = state.get("hand") or {}
        no_flop_no_drop = len(hand.get("board") or []) == 0

        # Uncalled chips are never part of a contested pot, regardless of whether
        # rake is zero. Refunding before the canonical award path keeps gross-pot
        # history truthful while leaving final stacks unchanged.
        refund_uncalled_contribution(state)
        gross_pot = sum(_chip(player.get("contributed")) for player in state.get("seats", []))

        value = original_award_uncontested(state, *args, **kwargs)
        if no_flop_no_drop:
            _complete_uncontested_result_metadata(poker_engine, state, gross_pot)
        return value

    poker_engine._showdown = showdown_with_uncalled_refund
    poker_engine._award_uncontested = uncontested_with_uncalled_refund
    _INSTALLED = True
