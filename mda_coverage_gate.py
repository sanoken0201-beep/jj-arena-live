"""Lightweight production-readiness coverage audit for JJ population MDA.

Trusted OFFLINE execution on a machine with the DB's *internal* connection.
Reads SQL aggregates only: never SELECT any player's name, hole cards, hand
actions or per-hand identifiers into Python. No FastAPI import or DB mutation.
No external database networking or insecure IP-allowlist change required.

Once the branch is reviewed/deployed, in Render service Shell:
  python mda_coverage_gate.py
  python mda_coverage_gate.py --sqlite path/to/jj.sqlite3
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from mda_offline_audit import connect_read_only

REQUIRED_TABLES = ("jj_hand_history", "jj_hand_players", "jj_hand_actions", "sitngo_hands")


def _tables(con: Any) -> set[str]:
    if con.postgres:
        rows = con.execute(
            """SELECT table_name FROM information_schema.tables
               WHERE table_schema='public'
                 AND table_name IN ('jj_hand_history','jj_hand_players',
                                    'jj_hand_actions','sitngo_hands')"""
        ).fetchall()
        return {r["table_name"] for r in rows}
    rows = con.execute(
        """SELECT name FROM sqlite_master WHERE type='table'
           AND name IN ('jj_hand_history','jj_hand_players',
                        'jj_hand_actions','sitngo_hands')"""
    ).fetchall()
    return {r["name"] for r in rows}


def audit_coverage(con: Any) -> dict[str, Any]:
    """SQL-only anonymous counts; no user-, hand- or card-level row leaves DB."""
    available = _tables(con)
    ring = []
    players = []
    actions = []
    sng = {"status": "source_table_missing"}
    if "jj_hand_history" in available:
        ring = [dict(x) for x in con.execute(
            """SELECT player_count,
                      COUNT(*) AS stored_hands,
                      COALESCE(SUM(CASE WHEN completed_at IS NOT NULL
                                       THEN 1 ELSE 0 END),0) AS completed_hands,
                      COALESCE(SUM(CASE WHEN completed_at IS NOT NULL
                                     AND COALESCE(partial_capture,0)=0
                                       THEN 1 ELSE 0 END),0) AS fully_captured_hands
               FROM jj_hand_history
               WHERE table_id IN ('jj-table-a','jj-table-b')
               GROUP BY player_count ORDER BY player_count"""
        ).fetchall()]
    if "jj_hand_history" in available and "jj_hand_players" in available:
        players = [dict(x) for x in con.execute(
            """SELECT h.player_count,
                      COUNT(*) AS player_hand_rows,
                      COUNT(DISTINCT p.user_id) AS distinct_players,
                      COALESCE(SUM(CASE WHEN p.hole_cards_json IS NULL
                              OR TRIM(CAST(p.hole_cards_json AS TEXT)) IN ('','[]','null')
                              THEN 1 ELSE 0 END),0) AS missing_card_rows
               FROM jj_hand_players p
               JOIN jj_hand_history h ON h.hand_id=p.hand_id
               WHERE h.table_id IN ('jj-table-a','jj-table-b') AND h.completed_at IS NOT NULL
                     AND COALESCE(h.partial_capture,0)=0
               GROUP BY h.player_count ORDER BY h.player_count"""
        ).fetchall()]
    if "jj_hand_history" in available and "jj_hand_actions" in available:
        actions = [dict(x) for x in con.execute(
            """SELECT h.player_count,
                      COUNT(*) AS action_rows,
                      COUNT(DISTINCT a.hand_id) AS hands_with_actions
               FROM jj_hand_actions a
               JOIN jj_hand_history h ON h.hand_id=a.hand_id
               WHERE h.table_id IN ('jj-table-a','jj-table-b') AND h.completed_at IS NOT NULL
                     AND COALESCE(h.partial_capture,0)=0
               GROUP BY h.player_count ORDER BY h.player_count"""
        ).fetchall()]
    if "sitngo_hands" in available:
        row = con.execute(
            """SELECT COUNT(*) AS stored_snapshots,
                      COUNT(DISTINCT event_id) AS events
               FROM sitngo_hands"""
        ).fetchone()
        sng = {"status": "ok", "stored_snapshots": int(row["stored_snapshots"]),
               "events": int(row["events"])}

    # Show coverage by official public Ring table so an unintentionally
    # omitted second table is visible immediately in a production audit.
    source_table_counts = []
    if "jj_hand_history" in available:
        source_table_counts = [dict(x) for x in con.execute(
            """SELECT table_id, COUNT(*) AS stored_hands,
                      COALESCE(SUM(CASE WHEN completed_at IS NOT NULL
                                  AND COALESCE(partial_capture,0)=0 THEN 1 ELSE 0 END),0) AS complete_hands
               FROM jj_hand_history
               WHERE table_id IN ('jj-table-a','jj-table-b')
               GROUP BY table_id ORDER BY table_id"""
        ).fetchall()]

    people_by_size = {int(x["player_count"]): x for x in players if x["player_count"] is not None}
    actions_by_size = {int(x["player_count"]): x for x in actions if x["player_count"] is not None}
    cohorts = []
    for h in ring:
        size = h["player_count"]
        d = people_by_size.get(int(size)) if size is not None else None
        a = actions_by_size.get(int(size)) if size is not None else None
        completed = int(h["completed_hands"])
        usable = int(h["fully_captured_hands"])
        n_players = int(d["distinct_players"]) if d else 0
        hands_with_actions = int(a["hands_with_actions"]) if a else 0
        # Counts alone cannot validate all recorded hole-card classes or
        # real RFI opportunities. Never imply sufficient 169-cell evidence.
        possible_cohort = (
            isinstance(size, int) and 2 <= size <= 6
            and usable >= 100 and n_players >= 8 and hands_with_actions > 0
        )
        cohorts.append({
            "table_size": size,
            "stored_hands": int(h["stored_hands"]),
            "completed_hands": completed,
            "fully_captured_hands": usable,
            "distinct_players_in_fully_captured_hands": n_players,
            "player_hand_rows": int(d["player_hand_rows"]) if d else 0,
            "missing_hole_card_rows": int(d["missing_card_rows"]) if d else None,
            "hands_with_recorded_actions": hands_with_actions,
            "action_rows": int(a["action_rows"]) if a else 0,
            "preliminary_readiness": (
                "possible_population_sample_requires_rfi_validation"
                if possible_cohort else "insufficient_or_incomplete"
            ),
        })
    return {
        "format_version": "mda-coverage-gate-v1",
        "execution": "offline_read_only_internal_access",
        "all_player_roles_included": True,
        "identifiable_rows_returned": False,
        "source_tables_available": sorted(available),
        "source_tables_missing": sorted(set(REQUIRED_TABLES) - available),
        "ring": {"table": "all_public_ring", "source_ring_tables": ["jj-table-a", "jj-table-b"], "per_table_coverage": source_table_counts, "cohorts_by_dealt_in_players": cohorts},
        "sitngo": sng,
        "not_verified_by_aggregate_counts": [
            "actual valid RFI opportunities by position",
            "169 individual hand-class sample sufficiency",
            "per-hand completion, card validity and duplicate decisions",
            "effectiveness of plus-range hypotheses and solver agreement",
        ],
        "next_action": "Run authorized full-history offline population audits only where coarse coverage is adequate.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="JJ MDA anonymous production coverage gate")
    parser.add_argument("--sqlite", default=None)
    args = parser.parse_args()
    with connect_read_only(args.sqlite) as con:
        if con.postgres:
            # Local to this existing READ ONLY transaction. Prevent a
            # pathological full-table scan from disrupting gameplay.
            con.execute("SET LOCAL statement_timeout='5000ms'")
        else:
            con.execute("BEGIN")  # consistent SQLite read snapshot
        data = audit_coverage(con)
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
