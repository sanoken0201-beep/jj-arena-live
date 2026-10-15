"""Offline read-only MDA across ALL recorded public Ring players and hands.

This is about DATA SUBJECTS: all members and admins are included equally.
It is not a live, in-play HUD. The operator needs authorized private database
access. No raw cards, identities, hand IDs, or opponent-specific stats are emitted.

Usage: python mda_all_players_offline_audit.py --sqlite local.sqlite3
       python mda_all_players_offline_audit.py --max-hands 500
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from typing import Any

from mda_foundation import METRICS, derive_decisions, derive_opportunities, wilson_interval
from mda_offline_audit import connect_read_only
from mda_ranges import (
    CELL_DISTINCT_THRESHOLD, CELL_THRESHOLD, DISTINCT_PLAYER_THRESHOLD,
    HAND_CLASSES, POSITIONS_BY_SIZE, SAMPLE_THRESHOLD, combo_count,
    extract_rfi_evidence, infer_plus_from_counts,
)

BATCH_SIZE = 200


def _counter() -> dict[str, Any]:
    return {"n": 0, "yes": 0, "players": set()}


def _append(bucket: dict[str, Any], actor_id: int, chosen: bool) -> None:
    bucket["n"] += 1
    bucket["yes"] += int(chosen)
    bucket["players"].add(actor_id)


def _metric(bucket: dict[str, Any]) -> dict[str, Any]:
    n, unique = bucket["n"], len(bucket["players"])
    if n < SAMPLE_THRESHOLD or unique < DISTINCT_PLAYER_THRESHOLD:
        return {"status": "insufficient_sample"}
    wins = bucket["yes"]
    return {
        "status": "observed", "opportunities": n, "chosen": wins,
        "percentage": round(100 * wins / n, 2),
        "wilson_95_percent": wilson_interval(wins, n),
        "interval_note": "unadjusted_for_repeat_player_dependence",
    }


def summarize_cohort_range_counts(
    cohort: tuple[int, str],
    per_class: dict[tuple[int, str, str], dict[str, Any]],
) -> dict[str, Any]:
    table_size, position = cohort
    data = {
        label: per_class.get((table_size, position, label), _counter())
        for label in HAND_CLASSES
    }
    count = sum(x["n"] for x in data.values())
    actors: set[int] = set()
    for d in data.values():
        actors.update(d["players"])
    if count < SAMPLE_THRESHOLD or len(actors) < DISTINCT_PLAYER_THRESHOLD:
        return {"status": "insufficient_sample"}
    cells = {}
    for label, d in data.items():
        n = d["n"]
        if n < CELL_THRESHOLD or len(d["players"]) < CELL_DISTINCT_THRESHOLD:
            cells[label] = {"status": "unknown"}
            continue
        opened = d["yes"]
        cells[label] = {
            "status": "observed", "opportunities": n, "opens": opened,
            "open_frequency": round(100 * opened / n, 2),
            "smoothed_frequency": round(100 * (opened + 1) / (n + 2), 2),
            "wilson_95_percent": wilson_interval(opened, n),
            "theoretical_combos": combo_count(label),
        }
    hypotheses = []
    if position != "BB":
        # Reuse exactly the existing heuristic rules; only the input is
        # streaming aggregated counts rather than an unbounded hand list.
        class_stats = {label: (v["n"], v["yes"]) for label, v in data.items()}
        for guess in infer_plus_from_counts(
            class_stats, table_size=table_size, position=position
        ):
            if cells[guess.seed]["status"] != "observed":
                continue
            hypotheses.append({
                "notation": guess.notation,
                "status": guess.status,
                "candidate_classes": guess.candidates,
                "has_counterevidence": bool(guess.contradiction_classes),
                "basis": "monotone_kicker_heuristic_not_observed",
            })
    return {
        "status": "ok", "opportunities": count,
        "unique_players": len(actors), "cells": cells,
        "hypotheses": hypotheses,
        "note": "Plus-ranges are hypotheses, never certainty for unobserved classes.",
    }


def _batch(con: Any, last: tuple[str, str] | None, limit: int) -> list[dict]:
    if last is None:
        sql = """SELECT hand_id,player_count,big_blind,board_json,completed_at,partial_capture
                 FROM jj_hand_history
                 WHERE table_id='jj-table-a' AND completed_at IS NOT NULL
                   AND COALESCE(partial_capture,0)=0 AND player_count BETWEEN 2 AND 6
                 ORDER BY completed_at,hand_id LIMIT ?"""
        params = (limit,)
    else:
        sql = """SELECT hand_id,player_count,big_blind,board_json,completed_at,partial_capture
                 FROM jj_hand_history
                 WHERE table_id='jj-table-a' AND completed_at IS NOT NULL
                   AND COALESCE(partial_capture,0)=0 AND player_count BETWEEN 2 AND 6
                   AND (completed_at>? OR (completed_at=? AND hand_id>?))
                 ORDER BY completed_at,hand_id LIMIT ?"""
        params = (last[0], last[0], last[1], limit)
    return [dict(row) for row in con.execute(sql, params).fetchall()]


def audit_all_players(
    con: Any, *, max_hands: int | None = None, batch_size: int = BATCH_SIZE
) -> dict[str, Any]:
    """Scan all eligible historical Ring hands; all users/roles are included.

    max_hands opts into a clearly labelled partial scan. Memory contains only
    aggregated class/metric counters and distinct-player sets, not hand records.
    """
    if type(batch_size) is not int or not 1 <= batch_size <= 200:
        raise ValueError("batch_size must be integer 1..200")
    if max_hands is not None and (type(max_hands) is not int or max_hands < 1):
        raise ValueError("max_hands must be positive integer or None")

    metrics = defaultdict(_counter)
    per_class = defaultdict(_counter)
    by_position = defaultdict(set)
    action_players = defaultdict(set)
    card_players = defaultdict(set)
    hands_by_size = defaultdict(int)
    global_people: set[int] = set()
    rejected = accepted = scanned = participant_hands = action_rows = 0
    last: tuple[str, str] | None = None
    while True:
        limit = min(batch_size, max_hands - scanned) if max_hands is not None else batch_size
        if limit <= 0:
            break
        batch = _batch(con, last, limit)
        if not batch:
            break
        scanned += len(batch)
        last = (str(batch[-1]["completed_at"]), str(batch[-1]["hand_id"]))
        ids = tuple(h["hand_id"] for h in batch)
        marks = ",".join("?" for _ in ids)
        players_by_hand: dict[str, list[dict]] = defaultdict(list)
        actions_by_hand: dict[str, list[dict]] = defaultdict(list)
        for r in con.execute(
            f"""SELECT hand_id,user_id,position,effective_stack_bb,hole_cards_json
                FROM jj_hand_players WHERE hand_id IN ({marks})""", ids
        ).fetchall():
            p = dict(r)
            players_by_hand[p.pop("hand_id")].append(p)
        for r in con.execute(
            f"""SELECT hand_id,seq,user_id,street,action,pot_before,
                       amount_chips,facing_chips,timed_out
                FROM jj_hand_actions WHERE hand_id IN ({marks}) ORDER BY hand_id,seq""", ids
        ).fetchall():
            a = dict(r)
            actions_by_hand[a.pop("hand_id")].append(a)

        for hand in batch:
            size = int(hand["player_count"])
            players = players_by_hand.get(hand["hand_id"], [])
            actions = actions_by_hand.get(hand["hand_id"], [])
            people = [p.get("user_id") for p in players]
            if (
                len(players) != size or len(set(people)) != size
                or any(uid is None for uid in people)
                or {p.get("position") for p in players} != set(POSITIONS_BY_SIZE[size])
                or not actions
            ):
                rejected += 1
                continue
            try:
                hand["board"] = json.loads(hand.pop("board_json") or "[]")
            except (ValueError, TypeError):
                rejected += 1
                continue
            decisions = derive_decisions(hand, players, actions)
            if not decisions:
                rejected += 1
                continue
            accepted += 1
            hands_by_size[size] += 1
            participant_hands += len(players)
            action_rows += len(decisions)
            for p in players:
                actor_id = int(p["user_id"])
                global_people.add(actor_id)
                by_position[(size, p["position"])].add(actor_id)
            for d in decisions:
                action_players[(size, d.position)].add(d.actor_id)
            for o in derive_opportunities(decisions):
                _append(metrics[(size, o.position, o.metric)], o.actor_id, o.chosen)
            for e in extract_rfi_evidence(hand, players, actions):
                _append(per_class[(size, e.position, e.holding)], e.actor_id, e.opened)
                card_players[(size, e.position)].add(e.actor_id)
        if len(batch) < limit:
            break

    by_size = {}
    for size in range(2, 7):
        if not hands_by_size[size]:
            continue
        positions = {}
        for pos in POSITIONS_BY_SIZE[size]:
            people = by_position[(size, pos)]
            if hands_by_size[size] < SAMPLE_THRESHOLD or len(people) < DISTINCT_PLAYER_THRESHOLD:
                positions[pos] = {"status": "insufficient_sample"}
                continue
            positions[pos] = {
                "status": "ok",
                "contributing_players": len(people),
                "players_with_decisions": len(action_players[(size, pos)]),
                "rfi_players_with_known_cards": len(card_players[(size, pos)]),
                "metrics": {
                    name: _metric(metrics[(size, pos, name)]) for name in sorted(METRICS)
                },
                "rfi_range": summarize_cohort_range_counts((size, pos), per_class)
                if pos != "BB" else {"status": "not_applicable"},
            }
        by_size[str(size)] = {
            "completed_hands_used": hands_by_size[size], "positions": positions
        }

    return {
        "format_version": "mda-all-players-v1",
        "mode": "offline_read_only",
        "population": "all recorded public Ring players, all account roles",
        "user_role_filter": "none",
        "game": "Ring", "table": "jj-table-a",
        "coverage": {
            "scope": "all_historical_completed_full_capture"
            if max_hands is None else "bounded_partial_scan",
            "complete_scan": max_hands is None,
            "hands_examined": scanned, "hands_accepted": accepted,
            "hands_rejected": rejected,
            "participant_hand_rows_accepted": participant_hands,
            "action_rows_accepted": action_rows,
            "unique_players": len(global_people)
            if len(global_people) >= DISTINCT_PLAYER_THRESHOLD else None,
        },
        "cohorts_by_players_dealt_in": by_size,
        "disclosure": "admin_offline_only; review separately before any member-facing aggregate",
        "notes": [
            "Every player is counted regardless of administrator/member account role.",
            "Rows from active, partially captured or unrecognized hands are excluded.",
            "Each size/position is independent; 2-player BTN/SB is a separate position.",
            "Each rate requires at least 100 opportunities from 8 unique players.",
            "RFI classes require 12 opportunities from 4 unique players.",
            "Individual card values, user IDs and hand IDs are not serialized.",
            "Sit&Go source storage is separate and not part of this Ring scan.",
            "Analysis is observational, not a verified GTO solution.",
        ],
    }


def main() -> None:
    p = argparse.ArgumentParser(description="JJ Ring all-player population MDA, offline only")
    p.add_argument("--sqlite", default=None)
    p.add_argument("--max-hands", type=int, default=None, help="PARTIAL scan for testing")
    args = p.parse_args()
    if args.max_hands is not None and args.max_hands < 1:
        p.error("--max-hands must be positive")
    with connect_read_only(args.sqlite) as con:
        if con.postgres:
            con.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        else:
            con.execute("BEGIN")  # Hold one consistent SQLite read snapshot.
        data = audit_all_players(con, max_hands=args.max_hands)
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
