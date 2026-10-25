"""Read-only, deterministic Ring population-MDA feature extraction.

No app imports, DB writes, routes, live-hand reads or hole-card processing.
User identifiers are INTERNAL only; never serialize raw decisions to a member API.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import sqrt
from typing import Any, Iterable, Mapping, Sequence


ACTIONS = frozenset({"fold", "check", "call", "raise", "allin_raise", "allin_call"})
AGGRESSIVE = frozenset({"raise", "allin_raise"})
VOLUNTARY = frozenset({"call", "raise", "allin_call", "allin_raise"})
FOLD = "fold"
METRICS = frozenset({"rfi", "three_bet", "fold_to_three_bet", "flop_cbet", "fold_to_flop_cbet"})


@dataclass(frozen=True)
class Decision:
    """Private intermediate row; not an API payload."""

    hand_id: str
    seq: int
    actor_id: int
    street: str
    action: str
    position: str
    pot_type: str
    players_dealt_in: int
    stack_bb_at_start: float
    facing_chips: int
    pot_before_chips: int
    bet_pct_pot: float | None
    board_texture: str | None
    timed_out: bool

    @property
    def aggressive(self) -> bool:
        return self.action in AGGRESSIVE


@dataclass(frozen=True)
class Opportunity:
    """One decision at which a narrowly defined action was available."""

    metric: str
    hand_id: str
    seq: int
    actor_id: int
    position: str
    street: str
    pot_type: str
    chosen: bool
    response: str
    bet_pct_pot: float | None
    board_texture: str | None


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _texture(board: Sequence[str], street: str) -> str | None:
    count = {"flop": 3, "turn": 4, "river": 5}.get(street)
    if count is None or len(board) < count:
        return None
    cards = board[:count]  # Never use future runout cards for earlier streets.
    if any(len(str(c)) < 2 for c in cards):
        return None
    ranks = [str(card)[:-1].upper() for card in cards]
    suits = [str(card)[-1:].lower() for card in cards]
    if any(s not in {"s", "h", "d", "c"} for s in suits):
        return None
    multiplicities = Counter(ranks).values()
    pairing = (
        "trips_plus" if max(multiplicities) >= 3 else
        "double_paired" if sum(v >= 2 for v in multiplicities) >= 2 else
        "paired" if any(v >= 2 for v in multiplicities) else "unpaired"
    )
    suit_counts = sorted((suits.count(s) for s in set(suits)), reverse=True)
    return f"{pairing}:{suit_counts[0]}max"


def _pot_type(raise_count: int) -> str:
    if raise_count <= 0:
        return "unraised"
    if raise_count == 1:
        return "srp"
    if raise_count == 2:
        return "3bet"
    return "4bet_plus"


def derive_decisions(
    hand: Mapping[str, Any],
    players: Sequence[Mapping[str, Any]],
    actions: Sequence[Mapping[str, Any]],
) -> tuple[Decision, ...]:
    """Normalize one complete, fully captured hand without accessing cards.

    Returns empty on missing/partial or inconsistent action records. The stack
    field is intentionally labelled AT START, not a guessed street-end stack.
    """
    if not hand.get("completed_at") or _integer(hand.get("partial_capture")):
        return ()
    hand_id = str(hand.get("hand_id") or "")
    bb = _integer(hand.get("big_blind"))
    if not hand_id or bb <= 0 or not actions:
        return ()
    persons = {int(p["user_id"]): p for p in players if p.get("user_id") is not None}
    if not persons:
        return ()
    board = hand.get("board") or []
    if not isinstance(board, (tuple, list)):
        return ()
    ordered = sorted(actions, key=lambda a: _integer(a.get("seq"), -1))
    seen_sequences: set[int] = set()
    raise_count = 0
    street_aggression: dict[str, int] = {}
    result: list[Decision] = []
    for a in ordered:
        seq = _integer(a.get("seq"), -1)
        actor = _integer(a.get("user_id"), -1)
        street = str(a.get("street") or "").lower()
        action = str(a.get("action") or "").lower()
        if (
            seq < 1 or seq in seen_sequences or actor not in persons
            or street not in {"preflop", "flop", "turn", "river"} or action not in ACTIONS
        ):
            return ()
        seen_sequences.add(seq)
        player = persons[actor]
        pot = _integer(a.get("pot_before"))
        facing = _integer(a.get("facing_chips"))
        amount = _integer(a.get("amount_chips"))
        if pot < 0 or facing < 0 or amount < 0:
            return ()
        first_bet = (
            street != "preflop" and action in AGGRESSIVE
            and facing == 0 and street_aggression.get(street, 0) == 0
        )
        ratio = round(amount * 100.0 / pot, 2) if first_bet and pot > 0 else None
        decision = Decision(
            hand_id=hand_id,
            seq=seq,
            actor_id=actor,
            street=street,
            action=action,
            position=str(player.get("position") or ""),
            pot_type=_pot_type(raise_count),
            players_dealt_in=_integer(hand.get("player_count"), len(persons)),
            stack_bb_at_start=float(player.get("effective_stack_bb") or 0),
            facing_chips=facing,
            pot_before_chips=pot,
            bet_pct_pot=ratio,
            board_texture=_texture(board, street),
            timed_out=bool(_integer(a.get("timed_out"))),
        )
        result.append(decision)
        if action in AGGRESSIVE:
            if street == "preflop":
                raise_count += 1
            street_aggression[street] = street_aggression.get(street, 0) + 1
    if not any(d.street == "preflop" for d in result):
        return ()
    return tuple(result)


def _op(metric: str, d: Decision, chosen: bool) -> Opportunity:
    return Opportunity(
        metric=metric,
        hand_id=d.hand_id,
        seq=d.seq,
        actor_id=d.actor_id,
        position=d.position,
        street=d.street,
        pot_type=d.pot_type,
        chosen=chosen,
        response=d.action,
        bet_pct_pot=d.bet_pct_pot,
        board_texture=d.board_texture,
    )


def derive_opportunities(decisions: Sequence[Decision]) -> tuple[Opportunity, ...]:
    """RFI, first 3bet, fold-to-first-3bet, flop cbet, direct fold-to-cbet.

    Deliberately omits unclear spots rather than counting imaginary chances.
    """
    pre = [d for d in decisions if d.street == "preflop"]
    flop = [d for d in decisions if d.street == "flop"]
    if not pre:
        return ()
    out: list[Opportunity] = []
    voluntary_seen = False
    for d in pre:
        # A limp closes RFI; only the first genuine unopened decision qualifies.
        if not voluntary_seen and d.position not in {"BB", ""}:
            out.append(_op("rfi", d, d.aggressive))
        if d.action in VOLUNTARY:
            voluntary_seen = True

    opener_index = next((i for i, d in enumerate(pre) if d.aggressive), None)
    three_bet_index: int | None = None
    if opener_index is not None:
        opener = pre[opener_index]
        examined: set[int] = set()
        for i in range(opener_index + 1, len(pre)):
            d = pre[i]
            if d.actor_id == opener.actor_id or d.actor_id in examined:
                continue
            examined.add(d.actor_id)
            out.append(_op("three_bet", d, d.aggressive))
            if d.aggressive:
                three_bet_index = i
                break
        if three_bet_index is not None:
            for d in pre[three_bet_index + 1:]:
                if d.actor_id == opener.actor_id:
                    # A 4bet by the opener is a non-fold response to the 3bet.
                    out.append(_op("fold_to_three_bet", d, d.action == FOLD))
                    break
                if d.aggressive:  # Another player's 4bet changes the faced wager.
                    break

    if opener_index is not None:
        preflop_aggressors = [d for d in pre if d.aggressive]
        pfa = preflop_aggressors[-1].actor_id
        pfa_first_index = next((i for i, d in enumerate(flop) if d.actor_id == pfa), None)
        if pfa_first_index is not None:
            before = flop[:pfa_first_index]
            if not any(d.aggressive for d in before):
                first = flop[pfa_first_index]
                out.append(_op("flop_cbet", first, first.aggressive))
                if first.aggressive:
                    seen: set[int] = set()
                    for d in flop[pfa_first_index + 1:]:
                        if d.actor_id == pfa:
                            break
                        if d.actor_id in seen:
                            continue
                        seen.add(d.actor_id)
                        # The raiser faced the original cbet too; count that
                        # non-fold before ending eligibility for later actors.
                        out.append(_op("fold_to_flop_cbet", d, d.action == FOLD))
                        if d.aggressive:
                            break
    return tuple(out)


def wilson_interval(wins: int, total: int, z: float = 1.9599639845) -> tuple[float, float] | None:
    """Approximate binomial interval, unadjusted for clustering by player."""
    if not total or wins < 0 or wins > total:
        return None
    p = wins / total
    z2 = z * z
    center = (p + z2 / (2 * total)) / (1 + z2 / total)
    margin = z * sqrt((p * (1 - p) + z2 / (4 * total)) / total) / (1 + z2 / total)
    return (round(100 * max(0, center - margin), 2), round(100 * min(1, center + margin), 2))


def summarize(
    opportunities: Iterable[Opportunity],
    metric: str,
    *,
    min_opportunities: int = 100,
    min_players: int = 8,
    position: str | None = None,
) -> dict[str, Any]:
    """Privacy-thresholded population summary. Never reveals an actor/hand ID."""
    if metric not in METRICS:
        raise ValueError("unknown MDA metric")
    sample = [o for o in opportunities if o.metric == metric and (position is None or o.position == position)]
    count = len(sample)
    unique = len({o.actor_id for o in sample})
    if count < min_opportunities or unique < min_players:
        return {"metric": metric, "position": position, "status": "insufficient_sample"}
    successes = sum(o.chosen for o in sample)
    return {
        "metric": metric,
        "position": position,
        "status": "ok",
        "opportunities": count,
        "unique_players": unique,
        "chosen": successes,
        "percentage": round(successes * 100 / count, 2),
        "wilson_95_percent": wilson_interval(successes, count),
        "interval_note": "unadjusted_for_repeated_players",
    }


def coverage_report(con: Any) -> dict[str, Any]:
    """Read-only SQL audit on existing analytics tables, run OFFLINE only.

    Does not access secret hole-card columns. No background job/route is installed.
    """
    def scalar(sql: str) -> int:
        row = con.execute(sql).fetchone()
        try:
            value = row["n"]
        except (TypeError, KeyError, IndexError):  # bare sqlite3.Connection returns tuples
            value = row[0] if row else 0
        return int(value or 0)
    valid = "h.completed_at IS NOT NULL AND COALESCE(h.partial_capture,0)=0"
    return {
        "completed_full_hands": scalar(
            f"SELECT COUNT(*) AS n FROM jj_hand_history h WHERE {valid}"
        ),
        "completed_partial_hands": scalar(
            "SELECT COUNT(*) AS n FROM jj_hand_history WHERE completed_at IS NOT NULL AND COALESCE(partial_capture,0)<>0"
        ),
        "incomplete_hands": scalar(
            "SELECT COUNT(*) AS n FROM jj_hand_history WHERE completed_at IS NULL"
        ),
        "full_hand_player_rows": scalar(
            f"SELECT COUNT(*) AS n FROM jj_hand_players p JOIN jj_hand_history h ON h.hand_id=p.hand_id WHERE {valid}"
        ),
        "full_hand_action_rows": scalar(
            f"SELECT COUNT(*) AS n FROM jj_hand_actions a JOIN jj_hand_history h ON h.hand_id=a.hand_id WHERE {valid}"
        ),
        "full_hands_missing_actions": scalar(
            f"SELECT COUNT(*) AS n FROM jj_hand_history h WHERE {valid} "
            "AND NOT EXISTS (SELECT 1 FROM jj_hand_actions a WHERE a.hand_id=h.hand_id)"
        ),
        "full_hand_distinct_players": scalar(
            f"SELECT COUNT(DISTINCT p.user_id) AS n FROM jj_hand_players p JOIN jj_hand_history h "
            f"ON h.hand_id=p.hand_id WHERE {valid}"
        ),
    }
