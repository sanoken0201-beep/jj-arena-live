"""Run a bounded, read-only population-MDA coverage audit OUTSIDE live requests.

Usage:
  DATABASE_URL=... python mda_offline_audit.py --limit 200
  python mda_offline_audit.py --sqlite /path/to/jj.db --limit 200

Outputs only aggregate coverage and privacy-suppressed frequency summaries.
Does not import/start FastAPI, expose cards or write to the production database.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from mda_foundation import METRICS, coverage_report, derive_decisions, derive_opportunities, summarize


class QueryConnection:
    def __init__(self, raw: Any, *, postgres: bool):
        self.raw = raw
        self.postgres = postgres

    def execute(self, sql: str, params: tuple = ()) -> Any:
        if self.postgres:
            sql = sql.replace("?", "%s")
        return self.raw.execute(sql, params)


@contextmanager
def connect_read_only(sqlite_path: str | None = None) -> Iterator[QueryConnection]:
    url = os.environ.get("DATABASE_URL")
    if sqlite_path:
        # SQLite URI mode=ro refuses creation and every write.
        path = Path(sqlite_path).expanduser().resolve()
        raw = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
        raw.row_factory = sqlite3.Row
        try:
            yield QueryConnection(raw, postgres=False)
        finally:
            raw.close()
        return
    if not url:
        raise RuntimeError("Supply DATABASE_URL or --sqlite; no DB has been opened")
    import psycopg
    from psycopg.rows import dict_row

    if "render.com" in url and "sslmode=" not in url and "internal" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    raw = psycopg.connect(url, row_factory=dict_row, connect_timeout=10)
    try:
        raw.execute("SET TRANSACTION READ ONLY")
        yield QueryConnection(raw, postgres=True)
    finally:
        raw.rollback()  # Always close without committing, even after successful reads.
        raw.close()


def audit_recent(con: QueryConnection | Any, limit: int = 200) -> dict[str, Any]:
    if not 1 <= limit <= 500:
        raise ValueError("limit must be within 1..500")
    all_coverage = coverage_report(con)
    # Explicit small bounded slice, not a claim to characterize all historical play.
    rows = con.execute(
        """SELECT hand_id, table_id, big_blind, board_json, player_count,
                  completed_at, partial_capture
           FROM jj_hand_history
           WHERE completed_at IS NOT NULL AND COALESCE(partial_capture,0)=0
           ORDER BY completed_at DESC, hand_id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    extracted = []
    usable_hands = 0
    rejected_hands = 0
    total_decisions = 0
    for row in rows:
        h = dict(row)
        try:
            board = json.loads(h.pop("board_json") or "[]")
        except (TypeError, ValueError):
            rejected_hands += 1
            continue
        h["board"] = board
        # Only minimum fields are retrieved. Private hole-card and name columns
        # are never accessed by this audit.
        players = [
            dict(x) for x in con.execute(
                "SELECT user_id,position,effective_stack_bb FROM jj_hand_players WHERE hand_id=?",
                (h["hand_id"],),
            ).fetchall()
        ]
        actions = [
            dict(x) for x in con.execute(
                """SELECT seq,user_id,street,action,pot_before,amount_chips,facing_chips,timed_out
                   FROM jj_hand_actions WHERE hand_id=? ORDER BY seq""",
                (h["hand_id"],),
            ).fetchall()
        ]
        decisions = derive_decisions(h, players, actions)
        if not decisions:
            rejected_hands += 1
            continue
        usable_hands += 1
        total_decisions += len(decisions)
        extracted.extend(derive_opportunities(decisions))
    return {
        "scope": "Ring analytics history (most recent completed full-capture slice)",
        "read_only": True,
        "source_coverage": all_coverage,
        "recent_limit": limit,
        "recent_hands_examined": len(rows),
        "recent_hands_usable": usable_hands,
        "recent_hands_rejected": rejected_hands,
        "recent_decisions_extracted": total_decisions,
        "frequency": {
            metric: summarize(extracted, metric) for metric in sorted(METRICS)
        },
        "caveats": [
            "Latest-hand slice is not a randomized sample.",
            "Suppressed results do not reveal small cohort counts.",
            "Wilson intervals do not adjust for repeat-player clustering.",
            "Missing/partial/unrecognized actions are excluded rather than guessed.",
            "This is an offline audit, not an installed API or live-table HUD.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="JJ Ring MDA read-only bounded coverage audit")
    parser.add_argument("--sqlite", default=None, help="local SQLite file (read-only); overrides DATABASE_URL")
    parser.add_argument("--limit", type=int, default=200, help="most recent full hands (1..500)")
    args = parser.parse_args()
    if not 1 <= args.limit <= 500:
        parser.error("--limit must be 1..500")
    with connect_read_only(args.sqlite) as con:
        result = audit_recent(con, limit=args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
