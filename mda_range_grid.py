"""Privacy-safe 13 x 13 preflop MDA range display contract.

Inputs must already be sanitized *offline* population/cohort summaries, NOT
private hand records. No routes, DB access, live table hooks or heavy deps.
Exactly 169 classes: pairs on diagonal, suited above, offsuit below.
'Observed' means sample-qualified recorded action frequency, NOT a guaranteed
range membership; 'hypothesis' is only an unobserved plus-range candidate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from mda_ranges import POSITIONS_BY_SIZE, RANKS, expand_plus

SUPPORTED_FORMATS = frozenset((
    "rfi-range-v2", "mda-all-players-v1", "mda-sitngo-rfi-v1",
))


def _label(row: int, col: int) -> str:
    if row == col:
        return RANKS[row] * 2
    if row < col:
        return RANKS[row] + RANKS[col] + "s"
    return RANKS[col] + RANKS[row] + "o"


def _source_range(
    report: Mapping[str, Any], table_size: int, position: str
) -> tuple[Mapping[str, Any], list[Mapping[str, Any]]]:
    fmt = report.get("format_version")
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError("unsupported sanitized MDA report version")
    if fmt == "rfi-range-v2":
        if report.get("table_size") != table_size or report.get("position") != position:
            raise ValueError("table size / position differ from requested range")
        data = report.get("range") or {}
        hints = report.get("hypotheses") or []
        if data.get("table_size") != table_size or data.get("position") != position:
            raise ValueError("conflicting RFI cohort metadata")
    else:
        cohort = (report.get("cohorts_by_players_dealt_in") or {}).get(str(table_size), {})
        pos = (cohort.get("positions") or {}).get(position) or {}
        data = pos.get("rfi_range") or {}
        hints = data.get("hypotheses") or []
    if not isinstance(data, dict) or not isinstance(hints, list):
        raise ValueError("invalid anonymized MDA range data")
    return data, hints


def range_matrix(
    report: Mapping[str, Any],
    *,
    table_size: int,
    position: str,
    include_hypotheses: bool = True,
) -> dict[str, Any]:
    """Create a UI-ready 13x13 grid for one exact game + size + position.

    Suppressed data STAYS suppressed. Never fill in unobserved open rates from
    heuristics or solver guesses. No original cards, actor/hand IDs or names.
    """
    if type(table_size) is not int or table_size not in POSITIONS_BY_SIZE:
        raise ValueError("table_size must be an integer from 2 through 6")
    if position not in POSITIONS_BY_SIZE[table_size]:
        raise ValueError("position does not exist at this dealt-in player count")
    if not isinstance(report, dict):
        raise ValueError("sanitized report must be an object")
    info, hypotheses = _source_range(report, table_size, position)
    status = str(info.get("status") or "insufficient_sample")
    if position == "BB":
        status = "not_applicable"
    if status not in ("ok", "not_applicable", "insufficient_sample"):
        raise ValueError("unrecognized privacy cohort status")

    # Never use a cell from a suppressed group, even if a malformed file
    # happens to contain per-class statistics underneath that group.
    cells = info.get("cells", {}) if status == "ok" else {}
    if not isinstance(cells, dict):
        raise ValueError("invalid cells mapping")
    observed = {}
    for label in (_label(i, j) for i in range(13) for j in range(13)):
        cell = cells.get(label) or {}
        if not isinstance(cell, dict):
            raise ValueError("invalid anonymized class cell")
        if cell.get("status") != "observed":
            continue
        n = cell.get("opportunities")
        frequency = cell.get("open_frequency")
        if (
            type(n) is not int or n < 12
            or not isinstance(frequency, (int, float))
            or isinstance(frequency, bool) or not 0 <= frequency <= 100
        ):
            continue
        observed[label] = {
            "status": "observed",
            "open_frequency": float(frequency),
            "opportunities": n,
            "smoothed_frequency": cell.get("smoothed_frequency"),
            "confidence_interval": cell.get("wilson_95_percent"),
            "hypothesis": None,
        }

    inferred: dict[str, str] = {}
    if status == "ok" and include_hypotheses:
        for hint in hypotheses:
            if not isinstance(hint, dict) or hint.get("status") not in ("tentative", "seed_replicated"):
                continue
            notation = hint.get("notation")
            if not isinstance(notation, str):
                continue
            try:
                candidates = expand_plus(notation)
            except ValueError:
                continue
            seed = notation[:-1]
            # A seed must be publicly reportable (and genuinely observed)
            # before displaying any inferred candidate.
            if seed not in observed or hint.get("has_counterevidence"):
                continue
            if tuple(hint.get("candidate_classes") or []) != candidates:
                continue
            for c in candidates:
                if c != seed and c not in observed:
                    inferred.setdefault(c, notation)

    grid = []
    for i in range(13):
        row = []
        for j in range(13):
            label = _label(i, j)
            cell = observed.get(label)
            if cell is None:
                guess = inferred.get(label)
                cell = {
                    "status": "hypothesis" if guess else "unknown",
                    "open_frequency": None,
                    "opportunities": None,
                    "smoothed_frequency": None,
                    "confidence_interval": None,
                    "hypothesis": guess,
                }
            row.append({"class": label, **cell})
        grid.append(row)
    return {
        "format_version": "mda-grid-v1",
        "source_format": report["format_version"],
        "game": report.get("game"),
        "table_size": table_size,
        "position": position,
        "status": status,
        "rank_order": list(RANKS),
        "layout": "pairs diagonal; suited upper right; offsuit lower left",
        "grid": grid,
        "legend": {
            "observed": "Actual sample-qualified action frequency; may change on reanalysis",
            "hypothesis": "Kicker-monotonicity candidate, NOT an observed raise or a percentage",
            "unknown": "Insufficient evidence; never zero or 100 percent by default",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Display sanitized anonymous MDA in 13x13 grid JSON")
    parser.add_argument("--input", required=True, help="offline already-sanitized JSON report")
    parser.add_argument("--table-size", required=True, type=int, choices=range(2, 7))
    parser.add_argument("--position", required=True)
    parser.add_argument("--no-hypotheses", action="store_true")
    args = parser.parse_args()
    raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = range_matrix(raw, table_size=args.table_size, position=args.position,
                          include_hypotheses=not args.no_hypotheses)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
