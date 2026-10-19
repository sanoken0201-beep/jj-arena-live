"""JJ Arena MDA v2: empirical population tendencies from completed ONLINE RING hands.

Fundamental design:
  P(action | actual opportunity, context), never inferred 169-class membership.
  Absence of observed opens, even 0 of N, NEVER proves a hand is outside a range.
  No plus-notation, synthetic unobserved opens or opponent-specific profiles.

Only authoritative online Ring tables (A/B) and their structured records are
sources. Server-recorded cards are intentionally NEVER SELECTed or processed.
Offline only, read-only, keyset-paginated and no live HUD/job/web request hook.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import argparse
import json
from typing import Any

from mda_foundation import METRICS, derive_decisions, derive_opportunities, wilson_interval
from mda_offline_audit import connect_read_only
from mda_ranges import POSITIONS_BY_SIZE

SOURCES = ("jj-table-a", "jj-table-b")
BATCH = 150
MIN_OPPORTUNITIES = 100
MIN_PLAYERS = 8
METRIC_ORDER = ("rfi", "three_bet", "fold_to_three_bet", "flop_cbet", "fold_to_flop_cbet")


def _bucket(stack: float) -> str | None:
    if stack <= 0:
        return None
    if stack < 20:
        return "under_20bb"
    if stack < 40:
        return "20_to_39bb"
    if stack < 100:
        return "40_to_99bb"
    return "100bb_plus"


def _query_hands(con: Any, cursor: tuple[str, str] | None, limit: int, completed_before: str | None = None) -> list[dict]:
    base = """SELECT hand_id, player_count, big_blind, board_json, completed_at, partial_capture
              FROM jj_hand_history
              WHERE table_id IN ('jj-table-a','jj-table-b')
                AND completed_at IS NOT NULL AND COALESCE(partial_capture,0)=0
                AND player_count BETWEEN 2 AND 6"""
    prefix = ()
    if completed_before is not None:
        base += " AND completed_at<=?"
        prefix = (completed_before,)
    if cursor is not None:
        base += """ AND (completed_at>? OR (completed_at=? AND hand_id>?))"""
        values = (cursor[0], cursor[0], cursor[1], limit)
    else:
        values = (limit,)
    base += " ORDER BY completed_at,hand_id LIMIT ?"
    return [dict(h) for h in con.execute(base, prefix + values).fetchall()]


def _empty() -> dict:
    return {"opportunities": 0, "yes": 0, "participants": set(),
            "actions": Counter(), "bet_sizes": Counter()}


def _add(cell: dict, opportunity: Any, size_band: str | None) -> None:
    cell["opportunities"] += 1
    cell["yes"] += int(opportunity.chosen)
    cell["participants"].add(opportunity.actor_id)
    cell["actions"][opportunity.response] += 1
    # Bet-size frequencies are conditional on an observed BET and a valid
    # pot-relative bet amount. They are never put into the main denominator.
    if opportunity.chosen and opportunity.bet_pct_pot is not None:
        pct = opportunity.bet_pct_pot
        if pct >= 0:
            band = ("0_to_33pct" if pct <= 33 else
                    "34_to_66pct" if pct <= 66 else
                    "67_to_100pct" if pct <= 100 else "over_100pct")
            cell["bet_sizes"][band] += 1


def _publish_bucket(cell: dict, *, threshold: int = MIN_OPPORTUNITIES) -> dict:
    n = cell["opportunities"]
    players = len(cell["participants"])
    if n < threshold or players < MIN_PLAYERS:
        return {"status": "insufficient_sample"}
    yes = cell["yes"]
    return {
        "status": "observed",
        "opportunities": n,
        "unique_players": players,
        "chosen": yes,
        "percentage": round(100 * yes / n, 2),
        "wilson_95_percent": wilson_interval(yes, n),
        "action_counts": dict(sorted(cell["actions"].items())),
        "bet_size_observations": sum(cell["bet_sizes"].values()),
        "bet_size_counts_when_observed": dict(sorted(cell["bet_sizes"].items())),
        "interval_note": "binomial_descriptive_not_adjusted_for_repeated_players",
        "zero_note": "observed_zero_is_not_proof_of_structural_zero",
    }


def audit_online_population(
    con: Any, *, max_hands: int | None = None, batch_size: int = BATCH, completed_before: str | None = None
) -> dict:
    """Online Ring MDA: weighted counts of *eligible actual opportunities*.

    All seats/users (including admin) count equally as individual decisions.
    Format and dealt-in-player-count stay separate. Cuts are independent
    one-dimensional slices to avoid a false precision explosion.
    """
    if type(batch_size) is not int or not 1 <= batch_size <= 150:
        raise ValueError("batch_size out of range")
    if max_hands is not None and (type(max_hands) is not int or max_hands < 1):
        raise ValueError("max_hands must be a positive integer or None")
    counts = defaultdict(_empty)
    by_size = defaultdict(int)
    reject = Counter()
    cursor = None
    scanned = good = timeouts = 0
    players_total: set[int] = set()
    while True:
        limit = min(batch_size, max_hands-scanned) if max_hands is not None else batch_size
        if limit <= 0:
            break
        batch = _query_hands(con, cursor, limit, completed_before)
        if not batch:
            break
        scanned += len(batch)
        cursor = (str(batch[-1]["completed_at"]), str(batch[-1]["hand_id"]))
        ids = tuple(x["hand_id"] for x in batch)
        marks = ",".join("?" for _ in ids)
        # No hole_cards_json, player names or other hidden personal data are
        # selected. Identity is only used in ephemeral distinct-player sets.
        people = defaultdict(list)
        for rec in con.execute(
            f"""SELECT hand_id,user_id,position,effective_stack_bb
                FROM jj_hand_players WHERE hand_id IN ({marks})""", ids
        ).fetchall():
            p = dict(rec)
            people[p.pop("hand_id")].append(p)
        acts = defaultdict(list)
        for rec in con.execute(
            f"""SELECT hand_id,seq,user_id,street,action,pot_before,
                       amount_chips,facing_chips,timed_out
                FROM jj_hand_actions WHERE hand_id IN ({marks})
                ORDER BY hand_id,seq""", ids
        ).fetchall():
            a = dict(rec)
            acts[a.pop("hand_id")].append(a)

        for hand in batch:
            n = int(hand["player_count"])
            persons = people.get(hand["hand_id"], [])
            actions = acts.get(hand["hand_id"], [])
            ids_by_hand = [p.get("user_id") for p in persons]
            if (
                len(persons) != n or len(set(ids_by_hand)) != n
                or any(u is None for u in ids_by_hand)
                or {p.get("position") for p in persons} != set(POSITIONS_BY_SIZE[n])
                or not actions
            ):
                reject["incomplete_players_or_actions"] += 1
                continue
            try:
                hand["board"] = json.loads(hand.pop("board_json") or "[]")
            except (ValueError, TypeError):
                reject["invalid_board"] += 1
                continue
            decisions = derive_decisions(hand, persons, actions)
            if not decisions:
                reject["invalid_action_record"] += 1
                continue
            good += 1
            by_size[n] += 1
            players_total.update(int(u) for u in ids_by_hand)
            # The specific action and valid strategy opportunity are joined
            # by the stable (hand_id,seq) pair, never by guessed action order.
            details = {d.seq: d for d in decisions}
            for opportunity in derive_opportunities(decisions):
                if opportunity.metric not in METRICS:
                    continue
                decision = details.get(opportunity.seq)
                if decision is None or decision.actor_id != opportunity.actor_id:
                    continue
                if decision.timed_out:
                    timeouts += 1
                    continue  # forced folds are not voluntary strategic choices
                dims = [("all", "all"), ("position", decision.position),
                        ("pot_type", decision.pot_type)]
                stack = _bucket(decision.stack_bb_at_start)
                if stack is not None:
                    dims.append(("effective_stack", stack))
                if opportunity.board_texture and decision.street != "preflop":
                    dims.append(("board_texture", opportunity.board_texture))
                for cut, value in dims:
                    _add(counts[(n, opportunity.metric, cut, value)], opportunity, stack)
        if len(batch) < limit:
            break

    cohorts = {}
    for n in range(2, 7):
        if by_size[n] == 0:
            continue
        report = {}
        for metric in METRIC_ORDER:
            overall = _publish_bucket(counts[(n, metric, "all", "all")])
            # Distinct stratification dimensions, not an ungrounded cross-
            # product of all filters or guessed 169-class opening membership.
            cuts = {}
            for cut in ("position", "pot_type", "effective_stack", "board_texture"):
                keys = sorted(k[3] for k in counts if k[:3] == (n, metric, cut))
                if keys:
                    cuts[cut] = {name: _publish_bucket(counts[(n,metric,cut,name)]) for name in keys}
            report[metric] = {"overall": overall, "cuts": cuts}
        cohorts[str(n)] = {"completed_hands_used": by_size[n], "metrics": report}

    return {
        "format_version": "mda-online-population-v2",
        "game": "Ring",
        "source": "server_recorded_online_table_hand_analytics",
        "source_ring_tables": list(SOURCES),
        "all_player_roles_included": True,
        "interpretation": "observed_population_action_frequencies_not_hand_range_membership",
        "coverage": {
            "scope": ("complete_before_cutoff" if completed_before else "complete_history") if max_hands is None else "bounded_partial_scan",
            "completed_before": completed_before,
            "complete_scan": max_hands is None,
            "hands_examined": scanned, "hands_accepted": good,
            "hands_rejected": sum(reject.values()), "rejection_reasons": dict(sorted(reject.items())),
            "timed_out_opportunities_excluded": timeouts,
            "unique_players": len(players_total) if len(players_total) >= MIN_PLAYERS else None,
        },
        "cohorts_by_players_dealt_in": cohorts,
        "privacy": "anonymous_aggregate_only_no_hole_card_or_actor_or_hand_identifiers",
        "limitations": [
            "No unseen starting-hand class can be classified as absent from the strategy.",
            "This is observed pool behavior, not a solver-derived equilibrium range.",
            "Zero chosen out of N observed opportunities is descriptive; true action probability can be above zero.",
            "Every metric denominator is a valid action opportunity, not every completed hand.",
            "Repeated players induce dependent observations; Wilson intervals are descriptive, not adjusted confidence bounds.",
            "The model excludes action timeouts and incomplete/noncanonical logs.",
            "No game clients, live players or active hands are accessed.",
        ],
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Offline opportunity-based Ring-only population MDA")
    p.add_argument("--sqlite", default=None)
    p.add_argument("--max-hands", type=int, default=None)
    a = p.parse_args()
    with connect_read_only(a.sqlite) as con:
        if con.postgres:
            con.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            con.execute("SET LOCAL statement_timeout='30000ms'")
        else:
            con.execute("BEGIN")
        data = audit_online_population(con, max_hands=a.max_hands)
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
