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
        with db.connect() as con:
            con.execute(
                """INSERT INTO sitngo_runtime_metrics(day,metric,count)
                   VALUES (?,?,1)
                   ON CONFLICT(day,metric) DO UPDATE
                   SET count=sitngo_runtime_metrics.count+1""",
                (_day(now), metric),
            )
        return True
    except Exception:
        # Observability must never break tournament actions or timeout progress.
        return False


def classify_alerts(totals: dict[str, int], window_days: int) -> list[dict]:
    """Derive conservative operator alerts from aggregate safety counters.

    Normal user timeouts and their automatic actions are intentionally excluded.
    """
    days=max(1,int(window_days))
    missing=int(totals.get("missing_tokens",0))
    stale=int(totals.get("stale_hand",0))+int(totals.get("stale_turn",0))
    restart=int(totals.get("restart_recovery",0))
    duplicate=int(totals.get("duplicate_action",0))
    boundary=int(totals.get("timeout_boundary_protected",0))
    alerts=[]
    def add(code,severity,title,detail,count):
        alerts.append(dict(code=code,severity=severity,title=title,detail=detail,count=int(count)))
    if missing >= 5:
        add("missing_tokens","critical","古い操作画面の可能性があります",
            f"{days}日間でaction token不足を{missing}件検知しました。キャッシュ更新や古いクライアントが残っていないか確認してください。",missing)
    elif missing >= 1:
        add("missing_tokens","warning","action token不足を検知しました",
            f"{days}日間で{missing}件です。単発なら再読込で解消する場合があります。増加する場合は配信中のブラウザ資産を確認してください。",missing)
    if stale >= 10:
        add("stale_action","critical","古いhand/turnからの操作が多発しています",
            f"{days}日間でstale hand/turnを合計{stale}件検知しました。WebSocket同期・再接続・多重送信を確認してください。",stale)
    elif stale >= 3:
        add("stale_action","warning","stale actionが増えています",
            f"{days}日間でstale hand/turnを合計{stale}件検知しました。継続する場合は同期状態を確認してください。",stale)
    if restart >= 1:
        add("restart_recovery","warning","大会中の再起動復旧が発生しました",
            f"{days}日間で{restart}件です。復旧自体は保護されていますが、意図しない再起動でないか確認してください。",restart)
    if duplicate >= 5:
        add("duplicate_action","info","action再送が増えています",
            f"{days}日間で重複actionを{duplicate}件吸収しました。二重処理は防止されています。",duplicate)
    if boundary >= 1:
        add("timeout_boundary","info","timeout境界競合を保護しました",
            f"{days}日間で{boundary}件です。プレイヤー操作は保護されており、発生傾向の確認用情報です。",boundary)
    order={"critical":0,"warning":1,"info":2}
    return sorted(alerts,key=lambda x:(order[x["severity"]],x["code"]))


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
    alerts=classify_alerts(totals,days)
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
        "alerts":alerts,
        "alert_status":next((severity for severity in ("critical","warning","info") if any(a["severity"]==severity for a in alerts)),"ok"),
    }


def install(service) -> None:
    app,db,server=service.app,service.db,service.server
    if getattr(app.state,"jj_sitngo_observability_installed",False):
        return
    ensure_schema(db)
    app.state.jj_sitngo_observability_installed=True

    @app.get("/api/admin/sitngo/telemetry")
    def admin_sitngo_telemetry(days: int = 7, user=Depends(server.admin_user)):
        return summary(db,days=days)


__all__=["METRICS","classify_alerts","ensure_schema","install","record","summary"]
