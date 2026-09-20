from __future__ import annotations

"""Privacy-preserving UX telemetry for JJ Arena online poker.

The telemetry store deliberately contains no user id, account name, table id,
hand id, cards, chip amounts, chat, IP address, user-agent string, or free-form
client text. It is for product ergonomics only: decision latency, timeouts,
connection recovery, and coarse feature usage.
"""

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Literal

from fastapi import Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator

RETENTION_DAYS = 30
MAX_BATCH = 30

EVENT_DETAILS: dict[str, set[str]] = {
    "decision": {"fold", "check", "call", "raise", "allin"},
    "timeout": {"check", "fold", "unknown"},
    "fallback": {"ws_close"},
    "reconnect": {"ws_open", "fresh_state"},
    "ready": {"submit"},
    "action_result": {"rejected"},
    "review": {"table_open", "bookmark"},
    "sizing": {"preset", "slider", "step", "input", "allin"},
    "preaction": {"check", "check_fold"},
    "ui": {"settings", "focus", "history", "chat"},
}


class TelemetryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event: Literal["decision", "timeout", "fallback", "reconnect", "ready", "action_result", "review", "sizing", "preaction", "ui"]
    detail: str = Field(min_length=1, max_length=24)
    device: Literal["mobile", "tablet", "desktop"]
    duration_ms: int | None = Field(default=None, ge=0, le=120_000)

    @model_validator(mode="after")
    def validate_shape(self):
        if self.detail not in EVENT_DETAILS[self.event]:
            raise ValueError("unsupported telemetry detail")
        if self.event == "decision" and self.duration_ms is None:
            raise ValueError("decision telemetry requires duration_ms")
        if self.event not in {"decision", "ready"} and self.duration_ms is not None:
            raise ValueError("duration_ms is only allowed for decision/ready telemetry")
        return self


class TelemetryBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    events: list[TelemetryEvent] = Field(min_length=1, max_length=MAX_BATCH)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def ensure_schema(db) -> None:
    idcol = "BIGSERIAL PRIMARY KEY" if getattr(db, "IS_POSTGRES", False) else "INTEGER PRIMARY KEY AUTOINCREMENT"
    with db.connect() as con:
        con.execute(
            f"""CREATE TABLE IF NOT EXISTS ux_telemetry_events(
                id {idcol},
                event_type TEXT NOT NULL,
                detail TEXT NOT NULL,
                device TEXT NOT NULL,
                duration_ms INTEGER,
                created_at TEXT NOT NULL
            )"""
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_ux_telemetry_created ON ux_telemetry_events(created_at)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_ux_telemetry_event ON ux_telemetry_events(event_type,created_at)")


def prune(db, now: datetime | None = None) -> int:
    cutoff = _iso((now or _now()) - timedelta(days=RETENTION_DAYS))
    with db.connect() as con:
        cur = con.execute("DELETE FROM ux_telemetry_events WHERE created_at<?", (cutoff,))
        return int(getattr(cur, "rowcount", 0) or 0)


def record(db, events: list[TelemetryEvent], now: datetime | None = None) -> int:
    stamp = _iso(now or _now())
    rows = [(e.event, e.detail, e.device, e.duration_ms, stamp) for e in events]
    insert_sql = "INSERT INTO ux_telemetry_events(event_type,detail,device,duration_ms,created_at) VALUES (?,?,?,?,?)"
    with db.connect() as con:
        # The production PostgreSQL compatibility wrapper intentionally exposes
        # execute(), not sqlite3.Connection.executemany(). Keep telemetry on the
        # shared DB contract so SQLite and PostgreSQL behave identically.
        for row in rows:
            con.execute(insert_sql, row)
    prune(db, now=now)
    return len(rows)


def _percentile(values: list[int], q: float) -> int | None:
    if not values:
        return None
    ordered = sorted(int(v) for v in values)
    idx = max(0, min(len(ordered) - 1, ceil(q * len(ordered)) - 1))
    return ordered[idx]


def summary(db, days: int = 7, now: datetime | None = None) -> dict:
    days = max(1, min(30, int(days)))
    end = now or _now()
    start = end - timedelta(days=days)
    with db.connect() as con:
        rows = con.execute(
            "SELECT event_type,detail,device,duration_ms,created_at FROM ux_telemetry_events WHERE created_at>=? ORDER BY created_at ASC",
            (_iso(start),),
        ).fetchall()

    events = [dict(r) for r in rows]
    counts = Counter(str(r["event_type"]) for r in events)
    devices = Counter(str(r["device"]) for r in events)
    details: dict[str, Counter] = defaultdict(Counter)
    trend: dict[str, Counter] = defaultdict(Counter)
    decision_durations: list[int] = []
    ready_durations: list[int] = []
    for row in events:
        event = str(row["event_type"])
        detail = str(row["detail"])
        details[event][detail] += 1
        day = str(row["created_at"])[:10]
        trend[day][event] += 1
        if event == "decision" and row.get("duration_ms") is not None:
            decision_durations.append(int(row["duration_ms"]))
        if event == "ready" and row.get("duration_ms") is not None:
            ready_durations.append(int(row["duration_ms"]))

    decision_count = counts["decision"]
    timeout_count = counts["timeout"]
    opportunities = decision_count + timeout_count
    avg = round(sum(decision_durations) / len(decision_durations)) if decision_durations else None
    ready_avg = round(sum(ready_durations) / len(ready_durations)) if ready_durations else None
    reconnect_opens = int(details["reconnect"]["ws_open"])
    reconnect_successes = int(details["reconnect"]["fresh_state"])

    day_rows = []
    for offset in range(days - 1, -1, -1):
        key = (end - timedelta(days=offset)).date().isoformat()
        c = trend.get(key, Counter())
        day_rows.append({
            "date": key,
            "decisions": int(c["decision"]),
            "timeouts": int(c["timeout"]),
            "fallbacks": int(c["fallback"]),
            "reconnects": int(c["reconnect"]),
            "ready": int(c["ready"]),
            "action_rejections": int(c["action_result"]),
            "reviews": int(c["review"]),
        })

    def dist(event: str) -> list[dict]:
        return [
            {"name": name, "count": int(count)}
            for name, count in sorted(details.get(event, Counter()).items(), key=lambda x: (-x[1], x[0]))
        ]

    return {
        "window_days": days,
        "retention_days": RETENTION_DAYS,
        "privacy": {
            "stores_user_identity": False,
            "stores_hand_or_cards": False,
            "stores_chip_amounts": False,
            "stores_free_text": False,
        },
        "totals": {
            "events": len(events),
            "decisions": int(decision_count),
            "timeouts": int(timeout_count),
            "timeout_rate_pct": round((timeout_count / opportunities) * 100, 2) if opportunities else 0.0,
            "fallbacks": int(counts["fallback"]),
            "reconnects": reconnect_opens,
            "reconnect_successes": reconnect_successes,
            "ready_submits": int(counts["ready"]),
            "action_rejections": int(counts["action_result"]),
            "review_opens": int(details["review"]["table_open"]),
            "review_bookmarks": int(details["review"]["bookmark"]),
        },
        "decision_ms": {
            "average": avg,
            "p50": _percentile(decision_durations, 0.50),
            "p90": _percentile(decision_durations, 0.90),
            "max": max(decision_durations) if decision_durations else None,
        },
        "ready_ms": {
            "average": ready_avg,
            "p50": _percentile(ready_durations, 0.50),
            "p90": _percentile(ready_durations, 0.90),
            "max": max(ready_durations) if ready_durations else None,
            "samples": len(ready_durations),
        },
        "actions": dist("decision"),
        "action_results": dist("action_result"),
        "reviews": dist("review"),
        "reconnect_details": dist("reconnect"),
        "timeouts": dist("timeout"),
        "sizing": dist("sizing"),
        "preactions": dist("preaction"),
        "ui": dist("ui"),
        "devices": [{"name": name, "count": int(count)} for name, count in sorted(devices.items(), key=lambda x: (-x[1], x[0]))],
        "trend": day_rows,
    }


def install(app, server, db) -> None:
    if getattr(app.state, "jj_ux_telemetry_installed", False):
        return
    app.state.jj_ux_telemetry_installed = True
    ensure_schema(db)
    prune(db)

    @app.post("/api/ux-telemetry")
    def ingest(payload: TelemetryBatch, user=Depends(server.current_user)):
        return {"ok": True, "accepted": record(db, payload.events)}

    @app.get("/api/admin/console/ux-telemetry")
    def admin_summary(days: int = 7, user=Depends(server.admin_user)):
        return summary(db, days=days)


__all__ = [
    "EVENT_DETAILS", "MAX_BATCH", "RETENTION_DAYS", "TelemetryBatch", "TelemetryEvent",
    "ensure_schema", "install", "prune", "record", "summary",
]
