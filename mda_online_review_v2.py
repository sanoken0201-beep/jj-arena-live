"""Safe offline, no-write candidate publisher for empirical Ring-only MDA v2.

Not a production scheduled job. No 169-class range, plus inference or cards.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json

from mda_online_population_v2 import METRIC_ORDER, SOURCES, audit_online_population
from mda_offline_audit import connect_read_only

FORMAT = "mda-population-v2-review"
MAX_BYTES = 500_000


def prepare_review(report: dict) -> dict:
    if (
        not isinstance(report, dict)
        or report.get("format_version") != "mda-online-population-v2"
        or report.get("source") != "server_recorded_online_table_hand_analytics"
        or report.get("source_ring_tables") != list(SOURCES)
        or report.get("all_player_roles_included") is not True
        or report.get("coverage", {}).get("complete_scan") is not True
    ):
        raise ValueError("reject old range, incomplete scan and unknown sources")
    cohorts = report.get("cohorts_by_players_dealt_in")
    if not isinstance(cohorts, dict):
        raise ValueError("invalid population report")
    output = {}
    for size, group in cohorts.items():
        if size not in ("2", "3", "4", "5", "6"):
            raise ValueError("invalid dealt-in cohort")
        values = {}
        for metric in METRIC_ORDER:
            raw = group["metrics"][metric]
            observed = raw["overall"]
            # Preserve publication thresholds. Missing/sparse cells remain
            # suppressed, never encoded as zero-frequency decisions.
            if observed["status"] != "observed":
                values[metric] = {"status": "insufficient_sample"}
            else:
                n, yes = observed["opportunities"], observed["chosen"]
                if n < 100 or observed["unique_players"] < 8 or not 0 <= yes <= n:
                    raise ValueError("privacy/denominator mismatch")
                values[metric] = {
                    "status": "observed", "opportunities": n,
                    "chosen": yes, "percentage": round(yes * 100 / n, 2),
                    "wilson_95_percent": observed["wilson_95_percent"],
                    "interpretation": "frequency_of_actual_opportunities_not_range_membership",
                }
        output[size] = {"completed_hands_used": int(group["completed_hands_used"]), "metrics": values}
    result = {
        "format_version": FORMAT, "game": "Ring",
        "source_ring_tables": list(SOURCES),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cohorts_by_players_dealt_in": output,
        "no_hand_class_inference": True,
        "published": False,
    }
    encoded = json.dumps(result, ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_BYTES:
        raise ValueError("oversized review snapshot")
    return result


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Create read-only MDA v2 aggregate review JSON")
    parser.add_argument("--sqlite", default=None)
    parser.add_argument("--max-hands", type=int)
    args = parser.parse_args()
    with connect_read_only(args.sqlite) as con:
        if con.postgres:
            con.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            con.execute("SET LOCAL statement_timeout='30000ms'")
        else:
            con.execute("BEGIN")
        report = audit_online_population(con, max_hands=args.max_hands)
    if args.max_hands is None:
        print(json.dumps(prepare_review(report), ensure_ascii=False, indent=2))
    else:
        # Diagnostics only: never label a bounded scan as publishable.
        print(json.dumps({"review_eligible": False, "coverage": report["coverage"]}, indent=2))


if __name__ == "__main__":
    main()
