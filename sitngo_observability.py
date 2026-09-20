"""Privacy-preserving aggregate observability for Sit&Go runtime safety.

Only coarse event counters are stored. No user id, event/table id, hand id, cards,
chip amounts, IP, user agent, session id, or free text is persisted.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from fastapi import Depends

METRICS = frozenset({
    "missing_tokens",
    "duplicate_action",
    "stale_hand",
    "stale_turn",
    "late_action",
    "timeout_boundary_protected",
    "timeout_auto_action",
    "restart_recovery",
})


def _day(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc).date().isoformat()


def ensure_schema(db) -> None:
    with db.connect() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS sitngo_runtime_metrics(
                day TEXT NOT NULL,
                metric TEXT NOT NULL,
                count BIGINT NOT NULL DEFAULT 0,
                PRIMARY KEY(day,metric)
            )"""
        )


def record(db, metric: str, now: datetime | None = None) -> bool:
    if metric not in METRICS:
        raise ValueError(f"unknown Sit&Go runtime metric: {metric}")
    try:
        day=_day(now)
        with db.connect() as con:
            con.execute(
                """INSERT INTO sitngo_runtime_metrics(day,metric,count)
                   VALUES (?,?,1)
                   ON CONFLICT(day,metric) DO UPDATE
                   SET count=sitngo_runtime_metrics.count+1""",
                (day, metric),
            )
            import sitngo_alerting
            if metric in sitngo_alerting.ALERT_THRESHOLDS:
                row=con.execute(
                    "SELECT count FROM sitngo_runtime_metrics WHERE day=? AND metric=?",
                    (day,metric),
                ).fetchone()
                sitngo_alerting.consider(con,day,metric,int(row["count"] or 0),now=now)
        return True
    except Exception:
        # Observability must never break tournament actions or timeout progress.
        return False


def summary(db, days: int = 7, now: datetime | None = None) -> dict:
    days=max(1,min(90,int(days)))
    end=(now or datetime.now(timezone.utc)).astimezone(timezone.utc).date()
    start=(end-timedelta(days=days-1)).isoformat()
    with db.connect() as con:
        rows=con.execute(
            "SELECT day,metric,count FROM sitngo_runtime_metrics WHERE day>=? ORDER BY day,metric",
            (start,),
        ).fetchall()
    totals={metric:0 for metric in sorted(METRICS)}
    trend={}
    for row in rows:
        metric=str(row["metric"])
        if metric not in METRICS:
            continue
        count=int(row["count"] or 0)
        totals[metric]+=count
        trend.setdefault(str(row["day"]),{})[metric]=count
    return {
        "window_days":days,
        "privacy":{
            "stores_user_identity":False,
            "stores_event_or_hand_id":False,
            "stores_cards_or_chip_amounts":False,
            "stores_network_identifiers":False,
            "stores_free_text":False,
        },
        "totals":totals,
        "trend":[{"date":day,**{m:int(values.get(m,0)) for m in sorted(METRICS)}} for day,values in sorted(trend.items())],
    }


def install(service) -> None:
    app,db,server=service.app,service.db,service.server
    if getattr(app.state,"jj_sitngo_observability_installed",False):
        return
    ensure_schema(db)
    import sitngo_alerting
    sitngo_alerting.install(service)
    app.state.jj_sitngo_observability_installed=True

    @app.get("/api/admin/sitngo/telemetry")
    def admin_sitngo_telemetry(days: int = 7, user=Depends(server.admin_user)):
        return summary(db,days=days)


__all__=["METRICS","ensure_schema","install","record","summary"]
