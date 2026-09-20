"""Privacy-preserving Sit&Go anomaly alert outbox and webhook delivery.

Alerts are thresholded daily aggregates. They never contain user/event/table/hand
identifiers, cards, chip amounts, network identifiers, sessions, or user-entered text.
Webhook delivery runs outside the action path and failures never affect gameplay.
"""
from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from fastapi import Depends

ALERT_THRESHOLDS = {
    "reconcile_error": 1,
    "tick_error": 1,
    "restart_recovery": 1,
    "timeout_boundary_protected": 3,
    "stale_hand": 5,
    "stale_turn": 5,
    "late_action": 10,
    "missing_tokens": 10,
    "duplicate_action": 20,
}

_CRITICAL = frozenset({"reconcile_error", "tick_error", "restart_recovery"})
_ENV = "JJ_SITNGO_ALERT_WEBHOOK_URL"


def _now(now: datetime | None = None) -> datetime:
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc)


def _iso(now: datetime | None = None) -> str:
    return _now(now).isoformat()


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = str(value)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _webhook_config() -> tuple[str | None, str | None]:
    raw = str(os.environ.get(_ENV, "") or "").strip()
    if not raw:
        return None, None
    try:
        parsed = urlparse(raw)
    except Exception:
        return None, "invalid_url"
    host = (parsed.hostname or "").lower()
    local = host in {"127.0.0.1", "localhost", "::1"}
    if not parsed.netloc or parsed.scheme not in ({"https"} if not local else {"http", "https"}):
        return None, "invalid_url"
    return raw, None


def ensure_schema(db) -> None:
    with db.connect() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS sitngo_runtime_alerts(
                id TEXT PRIMARY KEY,
                day TEXT NOT NULL,
                metric TEXT NOT NULL,
                severity TEXT NOT NULL,
                threshold INTEGER NOT NULL,
                observed_count INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                sent_at TEXT,
                last_error_code TEXT NOT NULL DEFAULT '',
                UNIQUE(day,metric,threshold)
            )"""
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_sitngo_alert_status ON sitngo_runtime_alerts(status,created_at)"
        )


def consider(con, day: str, metric: str, observed_count: int, now: datetime | None = None) -> bool:
    threshold = ALERT_THRESHOLDS.get(metric)
    if threshold is None or int(observed_count) < int(threshold):
        return False
    stamp = _iso(now)
    severity = "critical" if metric in _CRITICAL else "warning"
    alert_id = f"sng-alert-{day}-{metric}-{threshold}"
    con.execute(
        """INSERT INTO sitngo_runtime_alerts(
               id,day,metric,severity,threshold,observed_count,status,attempts,
               next_attempt_at,created_at,updated_at,sent_at,last_error_code
           ) VALUES (?,?,?,?,?,?,'pending',0,NULL,?,?,NULL,'')
           ON CONFLICT(day,metric,threshold) DO UPDATE
           SET observed_count=excluded.observed_count,
               updated_at=excluded.updated_at""",
        (alert_id, day, metric, severity, int(threshold), int(observed_count), stamp, stamp),
    )
    return True


def _payload(row: dict) -> dict:
    severity = str(row["severity"])
    metric = str(row["metric"])
    observed = int(row["observed_count"])
    threshold = int(row["threshold"])
    day = str(row["day"])
    text = (
        f"[JJ Arena Sit&Go] {severity.upper()} {metric}: "
        f"count {observed} on {day} UTC (threshold {threshold})"
    )
    return {
        "type": "sitngo_runtime_alert",
        "source": "jj-arena",
        "alert_key": f"{day}:{metric}:{threshold}",
        "severity": severity,
        "metric": metric,
        "day": day,
        "observed_count": observed,
        "threshold": threshold,
        "text": text,
    }


def _post_json(url: str, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "JJ-Arena-SitNGo-Alert/1",
        },
    )
    with urlopen(request, timeout=3.0) as response:
        status = int(getattr(response, "status", 200) or 200)
        if status < 200 or status >= 300:
            raise HTTPError(url, status, "non-success webhook response", None, None)


def _error_code(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        return f"http_{int(exc.code)}"
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(exc, URLError):
        return "url_error"
    return type(exc).__name__.lower()[:48]


def dispatch_pending(db, now: datetime | None = None, limit: int = 8) -> dict:
    url, config_error = _webhook_config()
    if not url:
        return {
            "configured": False,
            "configuration_error": config_error,
            "attempted": 0,
            "sent": 0,
            "failed": 0,
        }

    current = _now(now)
    with db.connect() as con:
        rows = con.execute(
            """SELECT * FROM sitngo_runtime_alerts
               WHERE status='pending'
               ORDER BY created_at ASC,id ASC LIMIT ?""",
            (max(1, min(50, int(limit))),),
        ).fetchall()

    attempted = sent = failed = 0
    for raw in rows:
        row = dict(raw)
        next_attempt = _parse(row.get("next_attempt_at"))
        if next_attempt and next_attempt > current:
            continue
        attempted += 1
        try:
            _post_json(url, _payload(row))
        except Exception as exc:
            failed += 1
            attempts = int(row.get("attempts") or 0) + 1
            delay = min(3600, 60 * (2 ** min(attempts - 1, 6)))
            retry_at = current + timedelta(seconds=delay)
            code = _error_code(exc)
            try:
                with db.connect() as con:
                    con.execute(
                        """UPDATE sitngo_runtime_alerts
                           SET attempts=?,next_attempt_at=?,updated_at=?,last_error_code=?
                           WHERE id=? AND status='pending'""",
                        (attempts, _iso(retry_at), _iso(current), code, row["id"]),
                    )
            except Exception:
                pass
            print(f"JJ_SITNGO_ALERT_DELIVERY_ERROR metric={row['metric']} code={code}")
            continue

        sent += 1
        with db.connect() as con:
            con.execute(
                """UPDATE sitngo_runtime_alerts
                   SET status='sent',attempts=attempts+1,next_attempt_at=NULL,
                       updated_at=?,sent_at=?,last_error_code=''
                   WHERE id=? AND status='pending'""",
                (_iso(current), _iso(current), row["id"]),
            )
        print(f"JJ_SITNGO_ALERT_SENT metric={row['metric']} day={row['day']}")

    return {
        "configured": True,
        "configuration_error": None,
        "attempted": attempted,
        "sent": sent,
        "failed": failed,
    }


def admin_status(db, days: int = 7, now: datetime | None = None) -> dict:
    days = max(1, min(90, int(days)))
    current = _now(now)
    start = (current.date() - timedelta(days=days - 1)).isoformat()
    url, config_error = _webhook_config()
    with db.connect() as con:
        rows = con.execute(
            """SELECT day,metric,severity,threshold,observed_count,status,attempts,
                      created_at,updated_at,sent_at,last_error_code
               FROM sitngo_runtime_alerts
               WHERE day>=?
               ORDER BY created_at DESC,metric ASC LIMIT 50""",
            (start,),
        ).fetchall()
        pending = con.execute(
            "SELECT COUNT(*) n FROM sitngo_runtime_alerts WHERE status='pending'"
        ).fetchone()
    return {
        "window_days": days,
        "webhook_configured": bool(url),
        "webhook_configuration_error": config_error,
        "pending_count": int(pending["n"] or 0),
        "thresholds": dict(ALERT_THRESHOLDS),
        "recent": [dict(row) for row in rows],
        "privacy": {
            "stores_user_identity": False,
            "stores_event_or_hand_id": False,
            "stores_cards_or_chip_amounts": False,
            "stores_network_identifiers": False,
            "stores_session_identifiers": False,
            "stores_user_free_text": False,
            "exposes_webhook_url": False,
        },
    }


async def alert_loop(db) -> None:
    import asyncio

    while True:
        try:
            await asyncio.to_thread(dispatch_pending, db)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"JJ_SITNGO_ALERT_LOOP_ERROR {type(exc).__name__}")
        await asyncio.sleep(30)


def install(service) -> None:
    app, db, server = service.app, service.db, service.server
    if getattr(app.state, "jj_sitngo_alerting_installed", False):
        return
    ensure_schema(db)
    app.state.jj_sitngo_alerting_installed = True

    @app.get("/api/admin/sitngo/alerts")
    def admin_sitngo_alerts(days: int = 7, user=Depends(server.admin_user)):
        return admin_status(db, days=days)


__all__ = [
    "ALERT_THRESHOLDS",
    "admin_status",
    "alert_loop",
    "consider",
    "dispatch_pending",
    "ensure_schema",
    "install",
]
