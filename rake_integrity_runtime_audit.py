from __future__ import annotations

"""Read-only production audit for persisted ring-game rake/result integrity.

This module never mutates application tables. It is intentionally executed only
by the Render production runtime after hand-analytics tables exist. The audit
uses the application's already-proven PostgreSQL connection path (including the
required Render TLS settings), marks the transaction READ ONLY, and emits one
compact JSON log line without member names, emails, or other personal data.
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import math
from typing import Any

UNCALLED_FIX_AT = datetime.fromisoformat("2026-09-14T15:59:55.992406+00:00")
RAKE_5_3_AT = datetime.fromisoformat("2026-09-14T16:17:08.642886+00:00")
NOFLOP_FIX_AT = datetime.fromisoformat("2026-09-14T17:43:56.661173+00:00")

CURRENT_ANOMALY_KEYS = (
    "fixed_table_policy_violation",
    "orphan_result",
    "hand_result_metadata_mismatch",
    "duplicate_user_result",
    "points_mismatch",
    "current_hand_conservation_or_completeness",
    "current_rake_formula_violation",
    "current_rake_bound_violation",
    "current_missing_analytics_history",
    "current_noflop_violation",
)


def _dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    try:
        return dict(row)
    except Exception:
        return {}


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value or "").strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _expected_rake_bb(gross_pot_bb: float, played_at: datetime, reached_street: str | None) -> float:
    if reached_street == "preflop":
        return 0.0
    # Ring tables use BB=100. online_hands persists gross_pot_bb to two
    # decimals, which exactly represents integer chip pots at BB=100.
    if played_at >= RAKE_5_3_AT:
        return min(math.floor(gross_pot_bb * 5.0 + 1e-9) / 100.0, 3.0)
    return min(math.floor(gross_pot_bb * 10.0 + 1e-9) / 100.0, 5.0)


def _read_rows(db) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    with db.connect() as con:
        if bool(getattr(db, "IS_POSTGRES", False)):
            # This is the first statement in the transaction. PostgreSQL then
            # rejects any accidental write attempted by this audit.
            con.execute("SET TRANSACTION READ ONLY")
        tables = [_dict(r) for r in con.execute("SELECT id,name,state_json FROM tables").fetchall()]
        hands = [_dict(r) for r in con.execute(
            "SELECT hand_id,table_id,gross_pot_bb,rake_bb,played_at,month,voided FROM online_hands"
        ).fetchall()]
        results = [_dict(r) for r in con.execute(
            "SELECT id,hand_id,table_id,user_id,result_bb,points,month FROM online_hand_results"
        ).fetchall()]
        history = [_dict(r) for r in con.execute(
            "SELECT hand_id,reached_street,player_count FROM jj_hand_history"
        ).fetchall()]
    return tables, hands, results, history


def audit_rows(
    tables: list[dict[str, Any]],
    hands: list[dict[str, Any]],
    results: list[dict[str, Any]],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    samples: dict[str, list[str]] = defaultdict(list)

    def flag(key: str, hand_id: Any = None) -> None:
        counts[key] += 1
        if hand_id is not None and len(samples[key]) < 20:
            samples[key].append(str(hand_id))

    # Persisted fixed-table policy.
    for row in tables:
        try:
            state = json.loads(str(row.get("state_json") or "{}"))
        except Exception:
            state = {}
        if "rake_percent" not in state:
            continue
        bb = max(0, int(state.get("big_blind") or 0))
        if abs(_float(state.get("rake_percent")) - 0.05) > 1e-12 or int(state.get("rake_cap") or -1) != bb * 3:
            flag("fixed_table_policy_violation", row.get("id"))

    hands_by_id = {str(row.get("hand_id")): row for row in hands if row.get("hand_id") is not None}
    history_by_id = {str(row.get("hand_id")): row for row in history if row.get("hand_id") is not None}
    results_by_hand: dict[str, list[dict[str, Any]]] = defaultdict(list)

    seen_users: Counter[tuple[str, Any]] = Counter()
    for row in results:
        hid = str(row.get("hand_id"))
        if hid not in hands_by_id:
            flag("orphan_result", hid)
            continue
        results_by_hand[hid].append(row)
        hand = hands_by_id[hid]
        if row.get("table_id") != hand.get("table_id") or row.get("month") != hand.get("month"):
            flag("hand_result_metadata_mismatch", hid)
        seen_users[(hid, row.get("user_id"))] += 1
        if abs(_float(row.get("points")) - round(_float(row.get("result_bb")) * 3.0, 2)) > 0.001:
            flag("points_mismatch", hid)

    for (hid, _uid), n in seen_users.items():
        if n > 1:
            flag("duplicate_user_result", hid)

    policy_windows: Counter[str] = Counter()
    for hid, hand in hands_by_id.items():
        played_at = _dt(hand.get("played_at"))
        gross = _float(hand.get("gross_pot_bb"))
        rake = _float(hand.get("rake_bb"))
        hrows = results_by_hand.get(hid, [])
        total_net = sum(_float(row.get("result_bb")) for row in hrows)
        hist = history_by_id.get(hid)
        reached = str(hist.get("reached_street") or "") if hist else None
        player_count = int(hist.get("player_count") or 0) if hist else 0

        if played_at < UNCALLED_FIX_AT:
            policy_windows["legacy_before_uncalled_fix"] += 1
            flag("legacy_uncalled_risk_window_hands", hid)
        elif played_at < RAKE_5_3_AT:
            policy_windows["10pct_5bb_after_uncalled_fix"] += 1
        elif played_at < NOFLOP_FIX_AT:
            policy_windows["5pct_3bb_before_noflop_metadata_fix"] += 1
        else:
            policy_windows["current_5pct_3bb"] += 1

        completeness_bad = (
            gross < -0.001
            or rake < -0.001
            or abs(total_net + rake) > 0.011
            or (player_count > 0 and len(hrows) != player_count)
        )
        if completeness_bad:
            flag("hand_conservation_or_completeness", hid)
            if played_at >= NOFLOP_FIX_AT:
                flag("current_hand_conservation_or_completeness", hid)
            else:
                flag("legacy_hand_conservation_or_completeness", hid)

        if hist:
            expected = _expected_rake_bb(gross, played_at, reached)
            if abs(rake - expected) > 0.001:
                flag("rake_formula_violation", hid)
                if played_at >= NOFLOP_FIX_AT:
                    flag("current_rake_formula_violation", hid)
                else:
                    flag("legacy_rake_formula_violation", hid)
        elif played_at >= NOFLOP_FIX_AT:
            flag("current_missing_analytics_history", hid)

        if played_at >= RAKE_5_3_AT and (rake < -0.001 or rake > 3.001 or rake - gross > 0.001):
            flag("current_rake_bound_violation", hid)

        if reached == "preflop":
            noflop_bad = (
                abs(rake) > 0.001
                or gross <= 0
                or abs(total_net + rake) > 0.011
                or (player_count > 0 and len(hrows) != player_count)
            )
            if noflop_bad:
                if played_at >= NOFLOP_FIX_AT:
                    flag("current_noflop_violation", hid)
                else:
                    flag("legacy_noflop_metadata_gap", hid)

    # Ensure stable zero-valued keys for operational parsing.
    for key in CURRENT_ANOMALY_KEYS:
        counts.setdefault(key, 0)
    counts.setdefault("legacy_noflop_metadata_gap", 0)
    counts.setdefault("legacy_uncalled_risk_window_hands", 0)
    counts.setdefault("legacy_hand_conservation_or_completeness", 0)
    counts.setdefault("legacy_rake_formula_violation", 0)

    current_total = sum(int(counts[key]) for key in CURRENT_ANOMALY_KEYS)
    return {
        "status": "ok" if current_total == 0 else "warning",
        "hand_count": len(hands),
        "result_count": len(results),
        "history_count": len(history),
        "current_anomaly_total": current_total,
        "checks": dict(sorted(counts.items())),
        "policy_windows": dict(sorted(policy_windows.items())),
        "samples": {key: value for key, value in sorted(samples.items()) if value},
    }


def should_run(db, environ: Any) -> bool:
    return (
        bool(getattr(db, "IS_POSTGRES", False))
        and str(environ.get("RENDER", "")).strip().lower() in {"1", "true", "yes"}
    )


def run(db) -> dict[str, Any]:
    report = audit_rows(*_read_rows(db))
    print("JJ_RAKE_AUDIT " + json.dumps(report, ensure_ascii=False, sort_keys=True), flush=True)
    return report


__all__ = [
    "CURRENT_ANOMALY_KEYS",
    "NOFLOP_FIX_AT",
    "RAKE_5_3_AT",
    "UNCALLED_FIX_AT",
    "audit_rows",
    "run",
    "should_run",
]
