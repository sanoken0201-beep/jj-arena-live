"""Compare privacy-suppressed MDA range snapshots without freezing any estimate.

This intentionally has no storage, scheduler or route. The caller supplies
two already-suppressed snapshots of the SAME exact cohort, and may use the
results only in an admin/offline review (never as a live opponent HUD).
"""
from __future__ import annotations

from typing import Any, Mapping

FORMAT = "rfi-range-v2"


def _key(s: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        s.get("format_version"), s.get("game"), s.get("table"),
        s.get("table_size"), s.get("position"), s.get("sample_policy"),
        s.get("requested_hand_limit"),
    )


def _known_cell(cell: Any) -> bool:
    return isinstance(cell, dict) and cell.get("status") == "observed"


def _hypotheses(report: Mapping[str, Any]) -> dict[str, tuple[Any, ...]]:
    results = {}
    for h in report.get("hypotheses") or []:
        if isinstance(h, dict) and isinstance(h.get("notation"), str):
            results[h["notation"]] = (
                h.get("status"), h.get("has_counterevidence"),
                tuple(h.get("candidate_classes") or ()),
            )
    return results


def compare_range_reports(
    previous: Mapping[str, Any], current: Mapping[str, Any]
) -> dict[str, Any]:
    """Return deterministic revision/withdrawal evidence from current history.

    A previously 'observed' rate can go up or down, or become 'unknown'
    after source correction/window movement. 'Seed replicated' is NOT an
    immutable truth; heuristic plus hypotheses can be withdrawn entirely.
    Reject cohort/window mismatch rather than making misleading deltas.
    """
    if not isinstance(previous, dict) or not isinstance(current, dict):
        raise ValueError("range snapshots must be objects")
    if previous.get("format_version") != FORMAT or _key(previous) != _key(current):
        raise ValueError("cannot compare different versions, table sizes, positions or sample policies")
    old = previous.get("range") or {}
    new = current.get("range") or {}
    if not isinstance(old, dict) or not isinstance(new, dict):
        raise ValueError("missing range payload")
    if old.get("position") != current.get("position") or new.get("position") != current.get("position"):
        raise ValueError("range position mismatch")
    for record in (old, new):
        if record.get("table_size") != current.get("table_size"):
            raise ValueError("range table-size mismatch")

    old_cells = old.get("cells") or {}
    new_cells = new.get("cells") or {}
    if not isinstance(old_cells, dict) or not isinstance(new_cells, dict):
        raise ValueError("invalid range cells")
    changed = []
    for label in sorted(set(old_cells) | set(new_cells)):
        before = old_cells.get(label) or {"status": "unknown"}
        after = new_cells.get(label) or {"status": "unknown"}
        if not isinstance(before, dict) or not isinstance(after, dict):
            raise ValueError("invalid cell")
        if before == after:
            continue
        old_known, new_known = _known_cell(before), _known_cell(after)
        change = (
            "newly_observed" if not old_known and new_known else
            "observation_withdrawn" if old_known and not new_known else
            "observed_frequency_revised" if old_known and new_known else
            "availability_changed"
        )
        changed.append({
            "class": label,
            "change": change,
            "previous_status": before.get("status", "unknown"),
            "current_status": after.get("status", "unknown"),
            "previous_frequency": before.get("open_frequency") if old_known else None,
            "current_frequency": after.get("open_frequency") if new_known else None,
            "previous_opportunities": before.get("opportunities") if old_known else None,
            "current_opportunities": after.get("opportunities") if new_known else None,
        })

    old_h, new_h = _hypotheses(previous), _hypotheses(current)
    suggestions = []
    for notation in sorted(set(old_h) | set(new_h)):
        prev, curr = old_h.get(notation), new_h.get(notation)
        if prev == curr:
            continue
        suggestions.append({
            "notation": notation,
            "change": "withdrawn" if curr is None else "added" if prev is None else "revised",
            "previous_status": prev[0] if prev else None,
            "current_status": curr[0] if curr else None,
            "counterevidence_now": curr[1] if curr else None,
        })
    status_transition = old.get("status") != new.get("status")
    return {
        "status": "updated" if changed or suggestions or status_transition else "unchanged",
        "table_size": current["table_size"],
        "position": current["position"],
        "sample_policy": current["sample_policy"],
        "previous_cohort_status": old.get("status"),
        "current_cohort_status": new.get("status"),
        "changed_cells": changed,
        "hypothesis_revisions": suggestions,
        "warning": "Admin-only revision comparison; never expose fine-grained changes to live players.",
    }
