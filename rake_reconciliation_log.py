"""Read-only rake reconciliation across historic BB-to-point conversion rates.

Executed only by the existing production rake audit on Render. Aggregate data
only: no member names, user identifiers, cards, credentials or mutations.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN
import json

CENT = Decimal("0.01")
ORIGINAL_RATE = Decimal("3")


def money(value):
    return Decimal(str(value if value is not None else 0))


def two(value):
    return str(money(value).quantize(CENT, rounding=ROUND_HALF_EVEN))


def when(raw):
    if isinstance(raw, datetime):
        stamp = raw
    else:
        stamp = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def json_value(raw):
    if isinstance(raw, dict):
        return raw
    try:
        result = json.loads(raw or "{}")
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}


def compute(hands, settlements, change_rows, current_rate):
    current_rate = money(current_rate)
    if not current_rate.is_finite() or current_rate <= 0:
        raise ValueError("Invalid current online conversion rate")

    events = []
    for row in change_rows:
        detail = json_value(row["detail_json"])
        changed = detail.get("changed") or {}
        if not isinstance(changed, dict) or changed.get("online_points_per_bb") is None:
            continue
        try:
            rate = money(changed["online_points_per_bb"])
            stamp = when(row["created_at"])
            if rate.is_finite() and Decimal("0") < rate <= Decimal("100"):
                events.append((stamp, int(row["id"]), rate))
        except (ValueError, TypeError):
            continue
    events.sort(key=lambda e: (e[0], e[1]))
    event_dates = [item[0] for item in events]

    classified = []
    rate_bins = defaultdict(lambda: [0, Decimal("0"), Decimal("0")])
    month_bins = defaultdict(lambda: [0, Decimal("0"), Decimal("0")])
    missing_snapshot = 0
    missing_rate_near_change = 0
    invalid_rates = 0
    void_hands = 0
    void_bb = Decimal("0")
    all_bb = Decimal("0")
    all_points = Decimal("0")
    snap_bb = Decimal("0")
    snap_points = Decimal("0")
    inferred_bb = Decimal("0")
    inferred_points = Decimal("0")

    for raw in hands:
        rake = money(raw["rake_bb"])
        if int(raw["voided"] or 0):
            void_hands += 1
            void_bb += rake
            continue
        stamp = when(raw["played_at"])
        stored_rate = raw.get("points_per_bb")
        if stored_rate is not None:
            rate = money(stored_rate)
            rate_source = "hand_snapshot"
        else:
            index = bisect_right(event_dates, stamp) - 1
            rate = events[index][2] if index >= 0 else ORIGINAL_RATE
            rate_source = "audit_inferred" if index >= 0 else "original_3_assumed"
            missing_snapshot += 1
            if any(abs((stamp - event[0]).total_seconds()) <= 7200 for event in events):
                missing_rate_near_change += 1
        if not rate.is_finite() or rate <= 0 or rate > 100:
            invalid_rates += 1
            continue
        points = rake * rate
        all_bb += rake
        all_points += points
        if stored_rate is None:
            inferred_bb += rake
            inferred_points += points
        else:
            snap_bb += rake
            snap_points += points
        month = str(raw.get("month") or stamp.strftime("%Y-%m"))
        rb = rate_bins[(str(rate), rate_source)]
        rb[0] += 1
        rb[1] += rake
        rb[2] += points
        mb = month_bins[month]
        mb[0] += 1
        mb[1] += rake
        mb[2] += points
        classified.append({
            "table": str(raw["table_id"]),
            "hand_no": int(raw["hand_no"]),
            "rake": rake,
            "points": points,
            "inferred": stored_rate is None,
        })

    settlement_rows = sorted(settlements, key=lambda s: (when(s["created_at"]), str(s["id"])))
    previous = {}
    settlement_breakdowns = []
    settlement_bb_mismatch = 0
    settlement_hand_count_mismatch = 0
    settlement_point_mismatch = 0
    for i, settlement in enumerate(settlement_rows):
        boundary = json_value(settlement.get("boundaries_json"))
        included = [h for h in classified if
                    int(previous.get(h["table"], 0) or 0) < h["hand_no"] <=
                    int(boundary.get(h["table"], 0) or 0)]
        bb = sum((h["rake"] for h in included), Decimal("0"))
        points = sum((h["points"] for h in included), Decimal("0"))
        recorded_bb = money(settlement["settled_rake_bb"])
        recorded_points = money(settlement["settled_rake_points"])
        settlement_rate = settlement.get("points_per_bb")
        display_rate = money(settlement_rate) if settlement_rate is not None else current_rate
        displayed = recorded_bb * display_rate
        if abs(bb - recorded_bb) > Decimal("0.011"):
            settlement_bb_mismatch += 1
        if len(included) != int(settlement["hand_count"] or 0):
            settlement_hand_count_mismatch += 1
        if abs(points - recorded_points) > Decimal("0.011"):
            settlement_point_mismatch += 1
        settlement_breakdowns.append({
            "index": i + 1,
            "utc": when(settlement["created_at"]).isoformat(),
            "hand_count": len(included),
            "recorded_hand_count": int(settlement["hand_count"] or 0),
            "rake_bb_recalculated": two(bb),
            "rake_bb_recorded": two(recorded_bb),
            "rake_bb_difference_recorded_minus_recalculated": two(recorded_bb - bb),
            "points_at_historic_hand_rates": two(points),
            "points_recorded_at_settlement": two(recorded_points),
            "points_difference_recorded_minus_history": two(recorded_points - points),
            "points_current_ui": two(displayed),
            "points_ui_minus_history": two(displayed - points),
            "inferred_rate_hands": sum(h["inferred"] for h in included),
            "settlement_rate_saved": str(settlement_rate) if settlement_rate is not None else None,
        })
        previous = boundary

    unsettled = [h for h in classified if h["hand_no"] > int(previous.get(h["table"], 0) or 0)]
    pending_bb = sum((h["rake"] for h in unsettled), Decimal("0"))
    pending_points = sum((h["points"] for h in unsettled), Decimal("0"))
    recorded_paid = sum((money(s["settled_rake_points"]) for s in settlement_rows), Decimal("0"))
    historic_paid = sum((money(s["points_at_historic_hand_rates"]) for s in settlement_breakdowns), Decimal("0"))
    return {
        "scope": "nonvoided all tables; per-hand historic rates; read-only",
        "reliability_note": "Rate snapshots are exact where present. Missing snapshots infer rate from admin change history, defaulting to original 3pt/BB; historic setting changes near hand starts are uncertain. Old rake calculation anomalies are evaluated separately.",
        "current_rate": str(current_rate),
        "rate_changes_utc": [{"time": x[0].isoformat(), "rate": str(x[2])} for x in events],
        "totals": {
            "hands": len(classified),
            "all_rake_bb": two(all_bb),
            "all_historic_rate_points": two(all_points),
            "all_current_ui_points": two(all_bb * current_rate),
            "all_ui_minus_historic": two(all_bb * current_rate - all_points),
            "unsettled_hands": len(unsettled),
            "unsettled_rake_bb": two(pending_bb),
            "unsettled_historic_rate_points": two(pending_points),
            "unsettled_current_ui_points": two(pending_bb * current_rate),
            "unsettled_ui_minus_historic": two(pending_bb * current_rate - pending_points),
            "settlements": len(settlement_rows),
            "sum_recorded_settlement_points": two(recorded_paid),
            "sum_historic_rate_settlement_points": two(historic_paid),
            "settlement_recorded_minus_historic": two(recorded_paid - historic_paid),
            "snapshot_hands": len(classified) - missing_snapshot,
            "snapshot_rake_bb": two(snap_bb),
            "snapshot_points": two(snap_points),
            "inferred_rate_hands": missing_snapshot,
            "inferred_rake_bb": two(inferred_bb),
            "inferred_points": two(inferred_points),
            "inferred_rate_near_change_hands": missing_rate_near_change,
            "invalid_rate_hands_excluded": invalid_rates,
            "void_hands_excluded": void_hands,
            "void_rake_bb_excluded": two(void_bb),
            "settlement_bb_mismatches": settlement_bb_mismatch,
            "settlement_hand_count_mismatches": settlement_hand_count_mismatch,
            "settlement_point_mismatches": settlement_point_mismatch,
        },
        "by_rate": [{"rate": k[0], "source": k[1], "hands": v[0],
                     "rake_bb": two(v[1]), "rake_points": two(v[2])}
                    for k, v in sorted(rate_bins.items())],
        "by_month": [{"month": k, "hands": v[0], "rake_bb": two(v[1]), "rake_points": two(v[2])}
                     for k, v in sorted(month_bins.items())],
        "settlements": settlement_breakdowns,
    }


def run(db):
    with db.connect() as con:
        if bool(getattr(db, "IS_POSTGRES", False)):
            con.execute("SET TRANSACTION READ ONLY")
        hands = [dict(r) for r in con.execute(
            "SELECT table_id,hand_no,rake_bb,played_at,month,voided,points_per_bb "
            "FROM online_hands").fetchall()]
        settlements = [dict(r) for r in con.execute(
            "SELECT id,boundaries_json,settled_rake_bb,settled_rake_points,"
            "points_per_bb,hand_count,created_at FROM ring_rake_settlements").fetchall()]
        changes = [dict(r) for r in con.execute(
            "SELECT id,detail_json,created_at FROM admin_audit_log WHERE action='settings.update'").fetchall()]
        setting = con.execute("SELECT value FROM app_settings WHERE key='online_points_per_bb'").fetchone()
        effective_rate = setting["value"] if setting else getattr(db, "ONLINE_POINTS_PER_BB", 3)
        report = compute(hands, settlements, changes, effective_rate)
    print("JJ_RAKE_RECALC " + json.dumps(report, ensure_ascii=False, sort_keys=True), flush=True)
    return report
