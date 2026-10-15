"""Private OFFLINE JJ MDA range auditor, segregated by players dealt in.

Read-only PostgreSQL/SQLite, batch queries, no app import, writes or live HUD.
The sanitized output is for an authorized administrator. Never expose a class
grid or revisions as a live per-opponent feed. All raw hole cards/IDs stay local.

Examples:
 python mda_range_offline_audit.py --table-size 6 --position BTN
 python mda_range_offline_audit.py --sqlite jj.sqlite3 --table-size 2 --position BTN/SB
 python mda_range_offline_audit.py --table-size 6 --position BTN --compare-json old.json
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
from typing import Any

from mda_offline_audit import connect_read_only
from mda_ranges import extract_rfi_evidence, infer_plus_hypotheses, summarize_range
from mda_range_revisions import compare_range_reports

POSITIONS_BY_SIZE = {
    2: ("BTN/SB", "BB"),
    3: ("BTN", "SB", "BB"),
    4: ("BTN", "SB", "BB", "CO"),
    5: ("BTN", "SB", "BB", "UTG", "CO"),
    6: ("BTN", "SB", "BB", "UTG", "HJ", "CO"),
}
BATCH_SIZE = 200
MAX_HANDS = 50000


def report_rfi_range(
    con: Any, *, table_size: int, position: str, limit: int = 5000
) -> dict[str, Any]:
    """Recompute from CURRENT completed history: no append-only certainty.

    The limit is applied after filtering by table_size, so 2–6 handed
    observations cannot silently displace one another.
    """
    if type(table_size) is not int or table_size not in POSITIONS_BY_SIZE:
        raise ValueError("table_size must be a dealt-in count of 2..6")
    if position not in POSITIONS_BY_SIZE[table_size] or position == "BB":
        raise ValueError("RFI is unavailable for this table-size/position pairing")
    if not 1 <= limit <= MAX_HANDS:
        raise ValueError(f"Sample limit must be 1..{MAX_HANDS}")

    rows = con.execute(
        """SELECT hand_id,big_blind,board_json,player_count,completed_at,partial_capture
           FROM jj_hand_history
           WHERE table_id='jj-table-a' AND player_count=?
             AND completed_at IS NOT NULL AND COALESCE(partial_capture,0)=0
           ORDER BY completed_at DESC, hand_id DESC LIMIT ?""",
        (table_size, limit),
    ).fetchall()

    private = []
    rejected = 0
    for offset in range(0, len(rows), BATCH_SIZE):
        batch = [dict(row) for row in rows[offset : offset + BATCH_SIZE]]
        ids = [hand["hand_id"] for hand in batch]
        if not ids:
            continue
        placeholders = ",".join("?" for _ in ids)
        players_by_hand: dict[str, list[dict]] = defaultdict(list)
        for p in con.execute(
            f"""SELECT hand_id,user_id,position,effective_stack_bb,hole_cards_json
                FROM jj_hand_players WHERE hand_id IN ({placeholders})""",
            tuple(ids),
        ).fetchall():
            item = dict(p)
            players_by_hand[item.pop("hand_id")].append(item)
        actions_by_hand: dict[str, list[dict]] = defaultdict(list)
        for a in con.execute(
            f"""SELECT hand_id,seq,user_id,street,action,pot_before,amount_chips,
                       facing_chips,timed_out
                FROM jj_hand_actions WHERE hand_id IN ({placeholders})
                ORDER BY hand_id,seq""",
            tuple(ids),
        ).fetchall():
            item = dict(a)
            actions_by_hand[item.pop("hand_id")].append(item)

        for h in batch:
            try:
                h["board"] = json.loads(h.pop("board_json") or "[]")
            except (TypeError, ValueError):
                rejected += 1
                continue
            persons = players_by_hand.get(h["hand_id"], [])
            acts = actions_by_hand.get(h["hand_id"], [])
            if not persons or not acts or len(persons) != table_size:
                rejected += 1
                continue
            private.extend(extract_rfi_evidence(h, persons, acts))

    report = summarize_range(private, position=position, table_size=table_size)
    public_hypotheses = []
    if report["status"] == "ok":
        for suggestion in infer_plus_hypotheses(private, position=position, table_size=table_size):
            seed_cell = report["cells"].get(suggestion.seed, {})
            if seed_cell.get("status") != "observed":
                continue
            public_hypotheses.append({
                "notation": suggestion.notation,
                "status": suggestion.status,
                "candidate_classes": suggestion.candidates,
                "basis": "monotone_kicker_heuristic_not_observed",
                "has_counterevidence": bool(suggestion.contradiction_classes),
            })
    return {
        "format_version": "rfi-range-v2",
        "mode": "offline_admin_only",
        "game": "Ring",
        "table": "jj-table-a",
        "table_size": table_size,
        "position": position,
        "sample_policy": "latest_completed_full_hands_per_table_size",
        "requested_hand_limit": limit,
        "hands_examined": len(rows),
        "hands_rejected_for_basic_completeness": rejected,
        "range": report,
        "hypotheses": public_hypotheses,
        "warnings": [
            "Never combine tables of different dealt-in player counts.",
            "Latest-N per table-size sample is a rolling window, not necessarily all history.",
            "All figures are recomputed: a previous estimated or highly supported range can be revised or withdrawn.",
            "Heuristic plus-notation is not proof of action with unobserved stronger kickers.",
            "Sparse cells remain unknown, not 0% or 100%. No in-play or opponent-specific use.",
            "All exact historical decisions are evidence, not an immutable statistical strategy.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="JJ MDA admin-only offline 2–6-hand RFI range audit")
    parser.add_argument("--sqlite", default=None, help="local SQLite database in read-only mode")
    parser.add_argument("--table-size", required=True, type=int, choices=sorted(POSITIONS_BY_SIZE))
    parser.add_argument("--position", required=True)
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument(
        "--compare-json", default=None,
        help="optional previous sanitized audit JSON for revision comparison (no writes)",
    )
    args = parser.parse_args()
    if args.position not in POSITIONS_BY_SIZE[args.table_size] or args.position == "BB":
        parser.error("position must exist for the requested table size and be RFI-eligible")
    if not 1 <= args.limit <= MAX_HANDS:
        parser.error(f"--limit must be 1..{MAX_HANDS}")

    with connect_read_only(args.sqlite) as con:
        result = report_rfi_range(
            con, table_size=args.table_size, position=args.position, limit=args.limit
        )

    if args.compare_json:
        previous = json.loads(Path(args.compare_json).read_text(encoding="utf-8"))
        result["revision"] = compare_range_reports(previous, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
