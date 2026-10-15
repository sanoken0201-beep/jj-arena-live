"""JJ MDA: conservative preflop range-class evidence and explicit hypotheses.

Private/offline analysis only. Reconstruct observed RFI from *fully captured,
completed* Ring hands; never treat a theoretical plus range as observed opens.

No database access, API, browser/real-time integration or write operations.
Input hole cards and actor IDs must never be returned to a member endpoint.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
from typing import Any, Iterable, Mapping, Sequence

from mda_foundation import derive_decisions, derive_opportunities, wilson_interval

RANKS = "AKQJT98765432"
SUITS = frozenset("shdc")
RANK_ORDER = {rank: index for index, rank in enumerate(RANKS)}
SAMPLE_THRESHOLD = 100
DISTINCT_PLAYER_THRESHOLD = 8
CELL_THRESHOLD = 12
CELL_DISTINCT_THRESHOLD = 4

# These labels mirror hand_analytics._position_map and are NOT seat capacity.
POSITIONS_BY_SIZE = {
    2: ("BTN/SB", "BB"),
    3: ("BTN", "SB", "BB"),
    4: ("BTN", "SB", "BB", "CO"),
    5: ("BTN", "SB", "BB", "UTG", "CO"),
    6: ("BTN", "SB", "BB", "UTG", "HJ", "CO"),
}


def _validate_cohort(position: str, table_size: int) -> None:
    if type(table_size) is not int or position not in POSITIONS_BY_SIZE.get(table_size, ()):
        raise ValueError("position must be valid for dealt-in table size (2..6)")


def hand_class(cards: Sequence[str]) -> str | None:
    """Return e.g. K5o, K5s, 55, AKo; reject invalid/duplicate cards."""
    if not isinstance(cards, (tuple, list)) or len(cards) != 2:
        return None
    normalized: list[tuple[str, str]] = []
    for c in cards:
        if not isinstance(c, str):
            return None
        c = c.strip()
        if len(c) == 3 and c[:2] == "10":
            c = "T" + c[2]
        if len(c) != 2:
            return None
        r, suit = c[0].upper(), c[1].lower()
        if r not in RANK_ORDER or suit not in SUITS:
            return None
        normalized.append((r, suit))
    if normalized[0] == normalized[1]:
        return None
    first, second = sorted(normalized, key=lambda x: RANK_ORDER[x[0]])
    if first[0] == second[0]:
        return first[0] * 2
    return first[0] + second[0] + ("s" if first[1] == second[1] else "o")


def all_classes() -> tuple[str, ...]:
    """All 169 non-overlapping starting-hand classes."""
    values = []
    for i, high in enumerate(RANKS):
        values.append(high + high)
        for low in RANKS[i + 1:]:
            values.extend((high + low + "s", high + low + "o"))
    assert len(values) == 169
    return tuple(values)


HAND_CLASSES = all_classes()


def combo_count(label: str) -> int:
    """Unblocked theoretical combos, not observed deal counts."""
    if label in HAND_CLASSES:
        return 6 if len(label) == 2 else 4 if label[-1] == "s" else 12
    raise ValueError("invalid starting hand class")


def expand_plus(token: str) -> tuple[str, ...]:
    """Conventional same-high-card expansion, never across suit types.

    K5o+ = K5o..KQo (not AKo); K5s+ is distinct.
    TT+ = TT, JJ, QQ, KK, AA.
    This expands notation, NOT empirical evidence or GTO permission.
    """
    token = str(token).strip()
    if len(token) < 3 or not token.endswith("+"):
        raise ValueError("expected a plus range (e.g. K5o+ or TT+)")
    base = token[:-1]
    if base not in HAND_CLASSES:
        raise ValueError("invalid plus-range seed")
    if len(base) == 2:
        i = RANK_ORDER[base[0]]
        return tuple(r * 2 for r in reversed(RANKS[: i + 1]))
    high, low, kind = base
    index = RANK_ORDER[high]
    upper = RANK_ORDER[low]
    if upper <= index:
        raise ValueError("bad kicker")
    return tuple(high + r + kind for r in reversed(RANKS[index + 1:upper + 1]))


@dataclass(frozen=True)
class PrivateRfiEvidence:
    """One genuine unopened RFI decision, always tied to known hole cards."""

    hand_id: str
    actor_id: int
    position: str
    table_size: int
    holding: str
    opened: bool


def _cards_json(value: Any) -> Sequence[str]:
    if isinstance(value, (tuple, list)):
        return value
    try:
        cards = json.loads(str(value or "[]"))
    except (TypeError, ValueError):
        return ()
    return cards if isinstance(cards, list) else ()


def extract_rfi_evidence(
    hand: Mapping[str, Any],
    players: Sequence[Mapping[str, Any]],
    actions: Sequence[Mapping[str, Any]],
) -> tuple[PrivateRfiEvidence, ...]:
    """Join existing MDA RFI opportunities to server-recorded cards offline.

    A missing/ambiguous recording stays UNKNOWN: never impute hole cards.
    Only one first-action RFI decision per actor is counted per hand.
    """
    # The cohort key is the number *actually dealt in when the hand began*,
    # not table capacity. Reject mismatched/partial player snapshots rather than
    # silently treating a 6-handed hand as 5-handed.
    try:
        table_size = int(hand["player_count"])
    except (KeyError, TypeError, ValueError):
        return ()
    ids = [str(p.get("user_id")) for p in players if p.get("user_id") is not None]
    if (
        table_size not in POSITIONS_BY_SIZE or len(ids) != table_size
        or len(set(ids)) != table_size
        or {str(p.get("position")) for p in players} != set(POSITIONS_BY_SIZE[table_size])
    ):
        return ()
    decisions = derive_decisions(hand, players, actions)
    if not decisions:
        return ()
    cards_by_user = {
        int(p["user_id"]): hand_class(_cards_json(p.get("hole_cards_json")))
        for p in players if p.get("user_id") is not None
    }
    opportunities = (o for o in derive_opportunities(decisions) if o.metric == "rfi")
    result: list[PrivateRfiEvidence] = []
    used: set[int] = set()
    for o in opportunities:
        if o.actor_id in used:
            continue
        used.add(o.actor_id)
        label = cards_by_user.get(o.actor_id)
        if not label:
            continue
        result.append(PrivateRfiEvidence(
            hand_id=o.hand_id,
            actor_id=o.actor_id,
            position=o.position,
            table_size=table_size,
            holding=label,
            opened=o.chosen,
        ))
    return tuple(result)


@dataclass(frozen=True)
class PlusHypothesis:
    """An explicit, falsifiable monotonicity assumption, not a solver range."""

    notation: str
    seed: str
    candidates: tuple[str, ...]
    status: str   # tentative or seed_replicated; NEVER 'confirmed'
    seed_open_count: int
    seed_opportunities: int
    contradiction_classes: tuple[str, ...]


def infer_plus_hypotheses(
    evidence: Iterable[PrivateRfiEvidence],
    *,
    position: str,
    table_size: int,
    min_seed_opens: int = 1,
    min_seed_opportunities: int = 1,
    min_conflict_opportunities: int = 8,
) -> tuple[PlusHypothesis, ...]:
    """Infer a same-high-card lower frontier, keeping exceptions visible.

    Suited A-x is omitted by default: wheel/blocker play is non-monotone.
    Individual low-gap suited hands and differing positions are not pooled.
    High-frequency evidence from stronger kickers can challenge a frontier.
    """
    _validate_cohort(position, table_size)
    stats: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for event in evidence:
        if event.position == position and event.table_size == table_size and event.holding in HAND_CLASSES:
            stats[event.holding][0] += 1
            stats[event.holding][1] += int(event.opened)
    return infer_plus_from_counts(
        stats,
        position=position,
        table_size=table_size,
        min_seed_opens=min_seed_opens,
        min_seed_opportunities=min_seed_opportunities,
        min_conflict_opportunities=min_conflict_opportunities,
    )


def infer_plus_from_counts(
    stats: Mapping[str, Sequence[int]],
    *,
    position: str,
    table_size: int,
    min_seed_opens: int = 1,
    min_seed_opportunities: int = 1,
    min_conflict_opportunities: int = 8,
) -> tuple[PlusHypothesis, ...]:
    """Build the same hypotheses from streaming private class counters.

    Each value is (eligible opportunities, opens). No actor identifiers,
    hand IDs or card combinations should be present in this input.
    """
    _validate_cohort(position, table_size)
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for hand in HAND_CLASSES:
        if len(hand) != 3:
            continue
        high, _low, kind = hand
        if high == "A" and kind == "s":
            continue
        groups[(high, kind)].append(hand)
    hypotheses: list[PlusHypothesis] = []
    for (high, kind), members in groups.items():
        seeds = [
            label for label in members
            if stats[label][0] >= min_seed_opportunities and stats[label][1] >= min_seed_opens
        ]
        if not seeds:
            continue
        # Lowest observed open kicker, not a claim of deterministic continuity.
        seed = max(seeds, key=lambda x: RANK_ORDER[x[1]])
        n, opens = stats[seed]
        candidates = expand_plus(seed + "+")
        if len(candidates) < 2:
            continue
        # A nonzero number of folds alone is not a contradiction: mixed strategies
        # naturally contain them. Flag sustained inversions with >=8 opportunities.
        seed_rate = opens / n
        contradictions = tuple(
            label for label in candidates
            if label != seed and stats[label][0] >= min_conflict_opportunities
            and stats[label][1] / stats[label][0] + 0.15 < seed_rate
        )
        support = (n >= 12 and opens >= 5 and not contradictions)
        hypotheses.append(PlusHypothesis(
            notation=seed + "+",
            seed=seed,
            candidates=candidates,
            status="seed_replicated" if support else "tentative",
            seed_open_count=opens,
            seed_opportunities=n,
            contradiction_classes=contradictions,
        ))
    return tuple(sorted(hypotheses, key=lambda x: (RANK_ORDER[x.seed[0]], x.seed[-1], x.seed)))


def summarize_range(
    evidence: Iterable[PrivateRfiEvidence],
    *,
    position: str,
    table_size: int,
    minimum_opportunities: int = SAMPLE_THRESHOLD,
    minimum_distinct_players: int = DISTINCT_PLAYER_THRESHOLD,
    minimum_cell_opportunities: int = CELL_THRESHOLD,
    minimum_cell_distinct_players: int = CELL_DISTINCT_THRESHOLD,
) -> dict[str, Any]:
    """Privacy-filtered 169-class RFI estimate; no hidden cards/user/hand IDs.

    Sparse classes remain unknown, even if we have a monotonicity hypothesis.
    Smoothed probabilities are within observed classes only; no implicit 100%.
    """
    _validate_cohort(position, table_size)
    selected = [
        e for e in evidence if e.position == position and e.table_size == table_size and e.holding in HAND_CLASSES
    ]
    unique = len({e.actor_id for e in selected})
    if len(selected) < minimum_opportunities or unique < minimum_distinct_players:
        return {"status": "insufficient_sample", "position": position, "table_size": table_size}

    groups: dict[str, list[PrivateRfiEvidence]] = defaultdict(list)
    for item in selected:
        groups[item.holding].append(item)
    cells = {}
    for label in HAND_CLASSES:
        items = groups[label]
        if len(items) < minimum_cell_opportunities or len({e.actor_id for e in items}) < minimum_cell_distinct_players:
            cells[label] = {"status": "unknown"}
            continue
        opens = sum(e.opened for e in items)
        count = len(items)
        cells[label] = {
            "status": "observed",
            "opportunities": count,
            "opens": opens,
            "open_frequency": round(100 * opens / count, 2),
            "smoothed_frequency": round(100 * (opens + 1) / (count + 2), 2),
            "wilson_95_percent": wilson_interval(opens, count),
            "theoretical_combos": combo_count(label),
        }
    return {
        "status": "ok",
        "position": position,
        "table_size": table_size,
        "opportunities": len(selected),
        "unique_players": unique,
        "cells": cells,
        "notes": [
            "Empirical RFI frequency, not GTO or guaranteed action.",
            "Cells with insufficient observations or distinct players are unknown.",
            "Smoothed frequency uses Beta(1,1) for observed cells only.",
            "Binomial Wilson interval does not adjust for repeated players.",
            "Inferred plus ranges must be presented as separate hypotheses.",
        ],
    }
