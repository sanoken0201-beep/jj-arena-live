"""Admin-only offline, read-only RFI range-class audit for JJ MDA.

Runs only on a trusted machine with authorized database access. There is no
member API, live-table hook, browser integration, scheduled polling or write.
Reads private completed-hand hole-card records in memory, and prints only
privacy-thresholded 169-class aggregate data (never identity, raw cards, hand IDs).

Usage: python mda_range_offline_audit.py --position BTN --limit 500
       python mda_range_offline_audit.py --sqlite /path/db.sqlite3 --position BTN
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from mda_offline_audit import connect_read_only
from mda_ranges import extract_rfi_evidence, infer_plus_hypotheses, summarize_range


ALLOWED_POSITIONS = ("UTG", "HJ", "CO", "BTN", "SB", "BTN/SB", "BB")


def report_rfi_range(con: Any, *, position: str = "BTN", limit: int = 500) -> dict[str, Any]:
    if position not in ALLOWED_POSITIONS:
        raise ValueError("Unsupported preflop position")
    if not 1 <= limit <= 500:
        raise ValueError("Sample limit must be 1..500")
    # Completed, non-partial Ring analytics records from the current public
    # table only. Sit&Go, partial deployments, and historical table B excluded.
    rows = con.execute(
        """SELECT hand_id, big_blind, board_json, player_count, completed_at, partial_capture
           FROM jj_hand_history
           WHERE table_id='jj-table-a'
             AND completed_at IS NOT NULL AND COALESCE(partial_capture,0)=0
           ORDER BY completed_at DESC, hand_id DESC LIMIT ?""",
        (limit,),
    ).fetchall()

    private = []
    rejected = 0
    for record in rows:
        hand = dict(record)
        try:
            hand["board"] = json.loads(hand.pop("board_json") or "[]")
        except (ValueError, TypeError):
            rejected += 1
            continue
        # Never select player names, credentials, reviews or hole cards from
        # live / incomplete games. The only sensitive field is limited to this
        # trusted offline analysis and is not returned in the JSON report.
        players = [
            dict(p) for p in con.execute(
                """SELECT user_id,position,effective_stack_bb,hole_cards_json
                   FROM jj_hand_players WHERE hand_id=?""",
                (hand["hand_id"],),
            ).fetchall()
        ]
        actions = [
            dict(a) for a in con.execute(
                """SELECT seq,user_id,street,action,pot_before,amount_chips,
                          facing_chips,timed_out
                   FROM jj_hand_actions WHERE hand_id=? ORDER BY seq""",
                (hand["hand_id"],),
            ).fetchall()
        ]
        if not players or not actions:
            rejected += 1
            continue
        private.extend(extract_rfi_evidence(hand, players, actions))

    # Pool suppression *before* generating any public suggestion. If sparse,
    # do not reveal the identity of an observed starting hand.
    report = summarize_range(private, position=position)
    public_hypotheses = []
    if report["status"] == "ok":
        for suggestion in infer_plus_hypotheses(private, position=position):
            seed_cell = report["cells"].get(suggestion.seed, {})
            if seed_cell.get("status") != "observed":
                continue
            # Suggestions are derived solely from an independently publishable
            # seed cell, and remain separate from observed frequencies.
            public_hypotheses.append({
                "notation": suggestion.notation,
                "status": suggestion.status,
                "candidate_classes": suggestion.candidates,
                "basis": "monotonic_kicker_assumption_not_observed",
                "has_counterevidence": bool(suggestion.contradiction_classes),
            })
    return {
        "mode": "offline_admin_only",
        "game": "Ring",
        "table": "jj-table-a",
        "position": position,
        "hands_examined": len(rows),
        "hands_rejected_for_basic_completeness": rejected,
        "range": report,
        "hypotheses": public_hypotheses,
        "warnings": [
            "Suggestions are heuristic, not proven inclusions in any player's strategy.",
            "Observation rates are hand-class conditional, not weighted by deal frequency.",
            "Unknown cells may not be reported as 0% or 100%.",
            "Do not expose unredacted private RFI evidence, identities or hole cards.",
            "Rare hand samples and repeat players can materially bias inference.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="JJ MDA offline private-data range auditor")
    parser.add_argument("--sqlite", default=None, help="local SQLite database (read-only)")
    parser.add_argument("--position", choices=ALLOWED_POSITIONS, default="BTN")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()
    if not 1 <= args.limit <= 500:
        parser.error("--limit must be 1..500")
    with connect_read_only(args.sqlite) as con:
        result = report_rfi_range(con, position=args.position, limit=args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
