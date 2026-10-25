"""Read-only point-source history and current-account economy analytics.

No point rows are created, repaired or reclassified here.  The three requested
sources are disjoint; other ledger entries remain visible for reconciliation.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import Depends, Query

import admin_console
import season_management

JST = ZoneInfo("Asia/Tokyo")
SOURCES = ("club", "online", "quiz", "other")


def _money(value):
    return Decimal(str(value or 0))


def _number(value):
    return round(float(value), 2)


def _jst_date_sql(db, field):
    if getattr(db, "IS_POSTGRES", False):
        return f"to_char((CAST({field} AS timestamptz) AT TIME ZONE 'Asia/Tokyo'), 'YYYY-MM-DD')"
    return f"date({field}, '+9 hours')"


def _local_day(timestamp):
    value = str(timestamp or "")
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(JST).date().isoformat()
    except (ValueError, OverflowError):
        return value[:10]


def _sort_timestamp(value, source):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=JST if source == "club" else timezone.utc)
        return parsed.timestamp()
    except (ValueError, OverflowError):
        return 0


def calculate(db, *, season="fall", source="all", offset=0, limit=50):
    """Apply exactly the inclusion rules used by the official rankings."""
    start, end = season_management.bounds(db, season)
    utc_start, utc_end = season_management.utc_bounds(start, end)
    today = datetime.now(JST).date()
    daily = {}

    def add(day, kind, amount):
        if not day or day < start or day >= end:
            return
        bucket = daily.setdefault(day, {key: Decimal("0") for key in SOURCES})
        bucket[kind] += _money(amount)

    want_all = source == "all"
    need = offset + limit + 1
    events = []

    def event(*, id, kind, player, points, occurred_at, detail, day=None):
        if not (want_all or kind == source):
            return
        item = {
            "id": str(id), "source": kind, "player": str(player),
            "points": _number(_money(points)),
            "date": day or _local_day(occurred_at),
            "occurred_at": str(occurred_at), "detail": str(detail or ""),
            "_sort": _sort_timestamp(occurred_at, kind),
        }
        events.append(item)

    with db.connect() as con:
        deleted_aware = "deleted_at" in admin_console._cols(db, con, "users")
        generations = admin_console._account_generations(con) if deleted_aware else {}

        # Club entries are keyed by name, not by user ID. Account-generation
        # filtering must run per row, not after an SQL GROUP BY name/date.
        entries = con.execute(
            """SELECT id,name,points,date,created_at,game_type
               FROM entries WHERE name!='運営調整' AND date>=? AND date<?
               ORDER BY date DESC,created_at DESC,id DESC""",
            (start, end),
        ).fetchall()
        for row in entries:
            if deleted_aware and not admin_console._club_entry_is_current(row, generations):
                continue
            add(str(row["date"])[:10], "club", row["points"])
            if want_all or source == "club":
                event(id=row["id"], kind="club", player=row["name"],
                      points=row["points"], occurred_at=row["date"],
                      day=str(row["date"])[:10], detail=row["game_type"] or "入力")

        deleted_online = " AND (r.user_id IS NULL OR u.deleted_at IS NULL)" if deleted_aware else ""
        date_online = _jst_date_sql(db, "h.played_at")
        join_online = "LEFT JOIN users u ON u.id=r.user_id" if deleted_aware else ""
        base_online = f"""FROM online_hand_results r
              JOIN online_hands h ON h.hand_id=r.hand_id
              {join_online}
              WHERE COALESCE(h.voided,0)=0 AND h.played_at>=? AND h.played_at<?
              {deleted_online}"""
        grouped_online = con.execute(
            f"""SELECT {date_online} day,SUM(r.points) points
                {base_online} GROUP BY {date_online}""",
            (utc_start, utc_end),
        ).fetchall()
        for row in grouped_online:
            add(str(row["day"]), "online", row["points"])
        if want_all or source == "online":
            result_rows = con.execute(
                f"""SELECT r.id,r.ranking_name,r.points,r.table_id,r.hand_id,
                           h.played_at FROM online_hand_results r
                    JOIN online_hands h ON h.hand_id=r.hand_id
                    {join_online}
                    WHERE COALESCE(h.voided,0)=0
                      AND h.played_at>=? AND h.played_at<? {deleted_online}
                    ORDER BY h.played_at DESC,r.id DESC LIMIT ?""",
                (utc_start, utc_end, need),
            ).fetchall()
            for row in result_rows:
                event(id=row["id"], kind="online", player=row["ranking_name"],
                      points=row["points"], occurred_at=row["played_at"],
                      detail=f"{row['table_id']} · {row['hand_id']}")

        deleted_ledger = "AND u.deleted_at IS NULL" if deleted_aware else ""
        date_ledger = _jst_date_sql(db, "l.effective_at")
        kind_sql = "CASE WHEN l.kind='quiz_reward' THEN 'quiz' ELSE 'other' END"
        base_ledger = f"""FROM point_ledger l JOIN users u ON u.id=l.user_id
            WHERE l.effective_at>=? AND l.effective_at<? {deleted_ledger}"""
        grouped_ledger = con.execute(
            f"""SELECT {date_ledger} day,{kind_sql} source,SUM(l.amount) points
                {base_ledger} GROUP BY {date_ledger},{kind_sql}""",
            (utc_start, utc_end),
        ).fetchall()
        for row in grouped_ledger:
            add(str(row["day"]), str(row["source"]), row["points"])
        if want_all or source in {"quiz", "other"}:
            kind_filter = ("AND l.kind='quiz_reward'" if source == "quiz" else
                           "AND l.kind<>'quiz_reward'" if source == "other" else "")
            ledger_rows = con.execute(
                f"""SELECT l.id,l.amount,l.kind,l.reason,l.effective_at,
                           COALESCE(NULLIF(u.ranking_name,''),u.name) player
                    {base_ledger} {kind_filter}
                    ORDER BY l.effective_at DESC,l.id DESC LIMIT ?""",
                (utc_start, utc_end, need),
            ).fetchall()
            for row in ledger_rows:
                event(id=row["id"], kind="quiz" if row["kind"] == "quiz_reward" else "other",
                      player=row["player"], points=row["amount"],
                      occurred_at=row["effective_at"], detail=row["reason"] or row["kind"])

    # The chart is computed from source totals, not from the paged history.
    # A zero-baseline season needs no stored balance snapshot or migration.
    if start == "0000-01-01":
        chart_start = min(daily) if daily else today.isoformat()
    else:
        chart_start = start
    last_season_day = date.fromisoformat(end) - timedelta(days=1)
    chart_end = min(last_season_day, max(today, date.fromisoformat(max(daily, default=chart_start))))
    if chart_start > chart_end.isoformat():
        chart_start = chart_end.isoformat()
    cursor = date.fromisoformat(chart_start)
    points = {key: Decimal("0") for key in SOURCES}
    timeline = []
    while cursor <= chart_end:
        day = cursor.isoformat()
        change = daily.get(day, {})
        for key in SOURCES:
            points[key] += change.get(key, Decimal("0"))
        cumulative = sum(points.values())
        timeline.append({
            "date": day,
            **{key: _number(change.get(key, 0)) for key in SOURCES},
            "change": _number(sum(change.values())),
            "cumulative": _number(cumulative),
            "quiz_cumulative": _number(points["quiz"]),
        })
        cursor += timedelta(days=1)

    totals = {key: _number(value) for key, value in points.items()}
    total = _number(sum(points.values()))
    seven = today - timedelta(days=6)
    thirty = today - timedelta(days=29)
    last7 = _number(sum(_money(row["change"]) for row in timeline if row["date"] >= seven.isoformat() and row["date"] <= today.isoformat()))
    last30 = _number(sum(_money(row["change"]) for row in timeline if row["date"] >= thirty.isoformat() and row["date"] <= today.isoformat()))

    events.sort(key=lambda item: (item["_sort"], item["id"]), reverse=True)
    page = events[offset:offset + limit]
    for item in page:
        item.pop("_sort")

    return {
        "season": season, "start": start, "end_exclusive": end,
        "as_of": today.isoformat(), "time_zone": "Asia/Tokyo",
        "totals": {**totals, "total": total}, "last_7_days": last7,
        "last_30_days": last30, "daily": timeline,
        "history": page, "next_offset": offset + limit if len(events) > offset + limit else None,
        "source": source,
        "definition": "現在のランキング対象データ。削除済みアカウント・無効化ハンド・運営調整入力は対象外。補正とSit&Goはその他。",
    }


def install(app, server, db):
    if getattr(app.state, "jj_point_economy_installed", False):
        return
    app.state.jj_point_economy_installed = True

    @app.get("/api/admin/point-economy")
    def economy(
        season: str = "fall",
        source: str = Query(default="all", pattern="^(all|club|online|quiz|other)$"),
        offset: int = Query(default=0, ge=0, le=100_000),
        limit: int = Query(default=50, ge=1, le=100),
        user=Depends(server.admin_user),
    ):
        return calculate(db, season=season, source=source, offset=offset, limit=limit)
