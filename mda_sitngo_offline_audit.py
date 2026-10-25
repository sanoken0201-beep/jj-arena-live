"""Conservative OFFLINE Sit&Go MDA ingestion of every player's completed hands.

Unlike Ring's structured jj_hand_actions, Sit&Go persists a private completed
state snapshot in sitngo_hands.state_json. Its per-hand text log is not a
validated action ledger. Only unambiguous preflop RFI opportunities are used.

No runtime hooks, game path changes, database writes or public APIs.
All roles are included, with privacy-suppressed anonymous cohort results.
"""
from __future__ import annotations

from collections import defaultdict
import argparse
import json
from typing import Any, Mapping

from mda_all_players_offline_audit import summarize_cohort_range_counts
from mda_offline_audit import connect_read_only
from mda_ranges import (
    DISTINCT_PLAYER_THRESHOLD, POSITIONS_BY_SIZE, SAMPLE_THRESHOLD,
    PrivateRfiEvidence, hand_class,
)

BATCH_SIZE = 100


def _private_rfi_from_snapshot(
    state: Mapping[str, Any],
    *,
    expected_hand_id: str | None = None,
    expected_event_id: str | None = None,
) -> tuple[tuple[PrivateRfiEvidence, ...], int, str | None]:
    """Parse only a fully completed hand with unambiguous action ownership.

    Returns (evidence, dealt-in-player-count, error). Zero RFI opportunities
    is a valid result when forced blind all-ins prevent voluntary actions.
    """
    hand = state.get("hand") or {}
    if not isinstance(hand, dict) or hand.get("phase") != "complete":
        return (), 0, "not_complete"
    if expected_hand_id is not None and hand.get("id") != expected_hand_id:
        return (), 0, "hand_mismatch"
    if expected_event_id is not None and state.get("id") != expected_event_id:
        return (), 0, "event_mismatch"
    if not isinstance(state.get("tournament"), dict):
        return (), 0, "not_tournament"

    starts = hand.get("starting_stacks")
    seats = state.get("seats")
    if not isinstance(starts, dict) or not isinstance(seats, list):
        return (), 0, "missing_dealt_in"
    try:
        start_ids = {int(uid) for uid, stack in starts.items() if int(stack) > 0}
        max_seats = int(state["max_seats"])
        button = int(state["button_seat"])
    except (ValueError, TypeError, KeyError):
        return (), 0, "invalid_dealt_in"
    n = len(start_ids)
    if n not in POSITIONS_BY_SIZE or max_seats < n or not 0 <= button < max_seats:
        return (), 0, "unsupported_player_count"

    dealt = [p for p in seats if isinstance(p, dict) and p.get("user_id") in start_ids]
    if len(dealt) != n or len({p.get("user_id") for p in dealt}) != n:
        return (), 0, "missing_dealt_in"
    names = [p.get("name") for p in dealt]
    if len(set(names)) != n or any(not isinstance(name, str) or not name or "\n" in name for name in names):
        return (), 0, "ambiguous_player_names"
    try:
        order = sorted(dealt, key=lambda p: (int(p["seat"]) - button) % max_seats)
        if len({int(p["seat"]) for p in order}) != n:
            return (), 0, "duplicate_seats"
    except (ValueError, TypeError, KeyError):
        return (), 0, "invalid_seats"
    if int(order[0]["seat"]) != button:
        return (), 0, "button_not_dealt_in"

    labels = POSITIONS_BY_SIZE[n]
    players = {
        p["name"]: {
            "id": int(p["user_id"]), "position": position,
            "holding": hand_class(p.get("cards") or []),
        }
        for p, position in zip(order, labels)
    }
    log = hand.get("log")
    if not isinstance(log, list) or not log:
        return (), 0, "missing_hand_log"

    # Always reject any unexplained preflop text rather than invent an action.
    # Names and entries are the strings persisted by the canonical engine.
    action_suffixes = (
        (" folds", "fold"), (" checks", "check"),
        (" calls ", "call"), (" raises to ", "raise"),
        (" is all-in to ", "raise"), (" is all-in for ", "call"),
    )
    result = []
    seen: set[int] = set()
    voluntary = False
    reached_postflop = False
    saw_opening_marker = False
    for i, raw in enumerate(log):
        if not isinstance(raw, str):
            return (), 0, "invalid_log_entry"
        line = raw.strip()
        if i == 0:
            if not line.startswith("Hand #") or not line.endswith(" started"):
                return (), 0, "invalid_start_marker"
            saw_opening_marker = True
            continue
        if line in {"FLOP", "TURN", "RIVER"}:
            reached_postflop = True
            break
        matches = []
        for name, player in players.items():
            for suffix, action in action_suffixes:
                if line.startswith(name + suffix):
                    tail = line[len(name + suffix):]
                    # A name that merely prefixes a longer one must not match.
                    # For numeric actions require a non-empty engine log amount.
                    if action in {"call", "raise"} and not tail.strip():
                        continue
                    matches.append((player, action))
        if len(matches) != 1:
            return (), 0, "unknown_or_ambiguous_log_action"
        player, action = matches[0]
        if player["id"] in seen:
            # Multiple actions by a player can happen on a raised street;
            # first RFI decision only. Still accept later valid action lines.
            pass
        elif not voluntary and player["position"] not in {"BB"}:
            seen.add(player["id"])
            if player["holding"] is not None:
                result.append(PrivateRfiEvidence(
                    hand_id=str(hand["id"]), actor_id=player["id"],
                    position=player["position"], table_size=n,
                    holding=player["holding"], opened=action == "raise",
                ))
        else:
            seen.add(player["id"])
        if action in {"call", "raise"}:
            voluntary = True

    if not saw_opening_marker:
        return (), 0, "invalid_start_marker"
    # Preflop-only all-fold endings are valid and may have no FLOP marker.
    return tuple(result), n, None


def _batch(con: Any, cursor: tuple[str, str] | None, limit: int) -> list[dict]:
    if cursor is None:
        return [dict(x) for x in con.execute(
            """SELECT hand_id,event_id,state_json,created_at FROM sitngo_hands
               ORDER BY created_at,hand_id LIMIT ?""", (limit,)
        ).fetchall()]
    return [dict(x) for x in con.execute(
        """SELECT hand_id,event_id,state_json,created_at FROM sitngo_hands
           WHERE created_at>? OR (created_at=? AND hand_id>?)
           ORDER BY created_at,hand_id LIMIT ?""",
        (cursor[0], cursor[0], cursor[1], limit),
    ).fetchall()]


def audit_all_sitngo_players(
    con: Any,
    *,
    max_hands: int | None = None,
    batch_size: int = BATCH_SIZE,
) -> dict[str, Any]:
    """Aggregate all players whose completed SitGo hand log is reconstructable."""
    if type(batch_size) is not int or not 1 <= batch_size <= 100:
        raise ValueError("batch_size must be integer 1..100")
    if max_hands is not None and (type(max_hands) is not int or max_hands < 1):
        raise ValueError("max_hands must be positive or None")
    groups: dict[tuple[int, str, str], dict[str, Any]] = defaultdict(
        lambda: {"n": 0, "yes": 0, "players": set()}
    )
    by_size = defaultdict(int)
    invalid = defaultdict(int)
    accepted = scanned = opportunities = 0
    seen_players: set[int] = set()
    cursor = None

    while True:
        limit = min(batch_size, max_hands - scanned) if max_hands is not None else batch_size
        if limit <= 0:
            break
        batch = _batch(con, cursor, limit)
        if not batch:
            break
        scanned += len(batch)
        cursor = (str(batch[-1]["created_at"]), str(batch[-1]["hand_id"]))
        for row in batch:
            try:
                state = json.loads(row["state_json"])
            except (ValueError, TypeError):
                invalid["invalid_json"] += 1
                continue
            if not isinstance(state, dict):
                invalid["invalid_json"] += 1
                continue
            events, size, error = _private_rfi_from_snapshot(
                state, expected_hand_id=row["hand_id"],
                expected_event_id=row["event_id"],
            )
            if error is not None:
                invalid[error] += 1
                continue
            accepted += 1
            by_size[size] += 1
            # All tournament hands enter coverage regardless of the player role
            # or whether a given player had a voluntary-action opportunity.
            hand = state["hand"]
            seen_players.update(int(uid) for uid in hand["starting_stacks"])
            for event in events:
                cell = groups[(size, event.position, event.holding)]
                cell["n"] += 1
                cell["yes"] += int(event.opened)
                cell["players"].add(event.actor_id)
                opportunities += 1

        if len(batch) < limit:
            break

    cohorts = {}
    for size in range(2, 7):
        if not by_size[size]:
            continue
        positions = {}
        for position in POSITIONS_BY_SIZE[size]:
            if position == "BB":
                positions[position] = {"rfi_range": {"status": "not_applicable"}}
                continue
            result = summarize_cohort_range_counts((size, position), groups)
            positions[position] = {"rfi_range": result}
        cohorts[str(size)] = {
            "completed_hands_used": by_size[size],
            "positions": positions,
        }
    return {
        "format_version": "mda-sitngo-rfi-v1",
        "source": "sitngo_hands",
        "game": "Sit&Go",
        "population": "all recorded tournament participants regardless of role",
        "user_role_filter": "none",
        "mode": "offline_read_only",
        "coverage": {
            "scope": "all_historical_complete_snapshots" if max_hands is None else "bounded_partial_scan",
            "complete_scan": max_hands is None,
            "hands_examined": scanned, "hands_accepted": accepted,
            "hands_rejected": sum(invalid.values()),
            "rejection_reasons": dict(sorted(invalid.items())),
            "eligible_rfi_opportunities_with_cards": opportunities,
            "unique_players": len(seen_players) if len(seen_players) >= DISTINCT_PLAYER_THRESHOLD else None,
        },
        "cohorts_by_players_dealt_in": cohorts,
        "notes": [
            "The action log is human-readable, so only explicitly unambiguous preflop RFI was extracted.",
            "No assumptions are made about missing player actions or missing hole cards.",
            "Sit&Go ranges are NEVER pooled with Ring ranges or 2-6 handed cohorts.",
            "3bet, flop cbet, ICM and full bet-size frequencies require a structured Sit&Go action ledger.",
            "No active hand, private cards, names, hand IDs or user IDs are serialized.",
            "Sample suppression applies independently to all table sizes and position/class cells.",
        ],
    }


def main() -> None:
    p = argparse.ArgumentParser(description="JJ all-player SitGo MDA offline RFI audit")
    p.add_argument("--sqlite", default=None)
    p.add_argument("--max-hands", type=int, default=None)
    args = p.parse_args()
    if args.max_hands is not None and args.max_hands < 1:
        p.error("--max-hands must be positive")
    with connect_read_only(args.sqlite) as con:
        if con.postgres:
            con.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        else:
            con.execute("BEGIN")
        data = audit_all_sitngo_players(con, max_hands=args.max_hands)
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
