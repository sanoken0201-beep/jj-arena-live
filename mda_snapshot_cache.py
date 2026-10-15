"""Offline MDA snapshot builder and opt-in atomic PostgreSQL publication.

IMPORTANT:
- Full historical analysis is NEVER started by a web/API request.
- Only anonymized, suppressed 13x13 grids are persisted.
- Publication is a separate operator-launched process, never on game tick.
- No snapshot is published from bounded/partial-history audits.
- The read API is admin-only; a separate privacy review is needed for members.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from typing import Any, Mapping

from mda_all_players_offline_audit import audit_all_players
from mda_offline_audit import connect_read_only
from mda_range_grid import range_matrix
from mda_ranges import POSITIONS_BY_SIZE
from mda_sitngo_offline_audit import audit_all_sitngo_players

TABLE_NAME = "jj_mda_population_cache"
FORMAT = "mda-admin-cache-v1"
MAX_DOC_BYTES = 50_000


def cache_key(game: str, table_size: int, position: str) -> str:
    """Canonical scope key: no user or opponent dimension."""
    if game not in ("Ring", "Sit&Go"):
        raise ValueError("MDA population format must be Ring or Sit&Go")
    if type(table_size) is not int or position not in POSITIONS_BY_SIZE.get(table_size, ()):
        raise ValueError("invalid dealt-in table size / position")
    return f"{game}:{table_size}:{position}"


def snapshot_documents(
    ring: Mapping[str, Any],
    sitngo: Mapping[str, Any],
    *,
    generated_at: str,
) -> dict[str, dict[str, Any]]:
    """Generate bounded anonymous cache entries with strict allowlisted fields."""
    required = (
        (ring, "Ring", "mda-all-players-v1"),
        (sitngo, "Sit&Go", "mda-sitngo-rfi-v1"),
    )
    for report, game, version in required:
        if (
            not isinstance(report, dict)
            or report.get("game") != game
            or report.get("format_version") != version
            or report.get("coverage", {}).get("complete_scan") is not True
        ):
            raise ValueError("refusing non-full-history/unknown-format MDA source")
    if not isinstance(generated_at, str) or not generated_at.endswith("+00:00"):
        raise ValueError("generated_at must be a UTC ISO8601 timestamp")
    docs = {}
    for report, game, _ in required:
        source = report.get("cohorts_by_players_dealt_in") or {}
        for table_size in POSITIONS_BY_SIZE:
            for position in POSITIONS_BY_SIZE[table_size]:
                key = cache_key(game, table_size, position)
                grid = range_matrix(report, table_size=table_size, position=position)
                meta = source.get(str(table_size), {}) or {}
                # No source raw IDs, cards or hands are copied to persisted JSON.
                body = {
                    "format_version": FORMAT,
                    "generated_at": generated_at,
                    "data_scope": "complete_history_snapshot",
                    "game": game,
                    "table_size": table_size,
                    "position": position,
                    "completed_hands_used": int(meta.get("completed_hands_used") or 0),
                    "range_status": grid["status"],
                    "grid": grid["grid"],
                    "legend": grid["legend"],
                    "rank_order": grid["rank_order"],
                }
                serialized = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
                if len(serialized.encode("utf-8")) > MAX_DOC_BYTES:
                    raise ValueError("MDA cache entry exceeds safe size")
                docs[key] = body
    return docs


def _prepare_full_audit(sqlite_path: str | None, game: str) -> dict[str, Any]:
    with connect_read_only(sqlite_path) as con:
        if con.postgres:
            # Retain one consistent read-only snapshot during each format scan.
            con.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            con.execute("SET LOCAL statement_timeout='30000ms'")
        else:
            con.execute("BEGIN")
        if game == "Ring":
            return audit_all_players(con)
        return audit_all_sitngo_players(con)


def _persist_postgres(docs: Mapping[str, Mapping[str, Any]], database_url: str) -> None:
    """Publish a complete generation atomically in a separate short TX."""
    import psycopg
    # Never log URL; it contains credentials.
    with psycopg.connect(database_url, connect_timeout=10) as con:
        with con.transaction():
            con.execute("SET LOCAL statement_timeout='10000ms'")
            con.execute(
                """CREATE TABLE IF NOT EXISTS jj_mda_population_cache(
                     scope_key TEXT PRIMARY KEY,
                     payload_json TEXT NOT NULL,
                     generated_at TIMESTAMPTZ NOT NULL)"""
            )
            # Versioned rows are completely replaced within one committed TX:
            # users never see one format half-updated during a refresh.
            for key, body in docs.items():
                con.execute(
                    """INSERT INTO jj_mda_population_cache(scope_key,payload_json,generated_at)
                       VALUES (%s,%s,%s)
                       ON CONFLICT(scope_key) DO UPDATE
                       SET payload_json=excluded.payload_json,
                           generated_at=excluded.generated_at""",
                    (key, json.dumps(body, ensure_ascii=False, separators=(",", ":")),
                     body["generated_at"]),
                )
        # Existing cache rows from old schema/position should not be exposed by
        # this route, because scope and format are revalidated at read time.


def main() -> None:
    p = argparse.ArgumentParser(description="Offline publish of suppressed all-player MDA grids")
    p.add_argument("--sqlite", default=None, help="source-only local SQLite for dry run")
    p.add_argument("--publish", action="store_true", help="explicitly write cache table to PostgreSQL")
    p.add_argument("--permit-primary-scan", action="store_true",
                   help="acknowledge full-history queries on production primary; run off-peak")
    args = p.parse_args()
    if args.publish and (args.sqlite or not args.permit_primary_scan):
        p.error("--publish requires production internal DATABASE_URL and --permit-primary-scan")
    if not args.sqlite and not args.permit_primary_scan:
        p.error("production full-history scan requires --permit-primary-scan")
    # External scheduler should run off-peak; no periodic timer is installed.
    ring = _prepare_full_audit(args.sqlite, "Ring")
    sitngo = _prepare_full_audit(args.sqlite, "Sit&Go")
    docs = snapshot_documents(
        ring, sitngo, generated_at=datetime.now(timezone.utc).isoformat()
    )
    summary = {
        "format_version": FORMAT, "published": False,
        "grids_created": len(docs),
        "ring_hands_accepted": ring["coverage"]["hands_accepted"],
        "sitngo_hands_accepted": sitngo["coverage"]["hands_accepted"],
        "source": "all_player_full_history",
        "private_data_returned": False,
    }
    if args.publish:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL is not configured")
        _persist_postgres(docs, url)
        summary["published"] = True
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
