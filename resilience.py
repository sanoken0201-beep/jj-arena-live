from __future__ import annotations

import asyncio
import hashlib
import json
import time
import traceback
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Body, Depends, HTTPException, Request

KEEP_PER_TABLE = 40
ERROR_RETENTION_DAYS = 90
API_LATENCY_WINDOW = 500
_API_LATENCY_MS: deque[float] = deque(maxlen=API_LATENCY_WINDOW)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_schema(db) -> None:
    uid = "BIGINT" if getattr(db, "IS_POSTGRES", False) else "INTEGER"
    with db.connect() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS ops_error_log(
            id TEXT PRIMARY KEY,event_type TEXT NOT NULL,method TEXT,path TEXT,
            detail TEXT NOT NULL,created_at TEXT NOT NULL)""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_ops_error_created ON ops_error_log(created_at)")
        con.execute(f"""CREATE TABLE IF NOT EXISTS table_state_backups(
            id TEXT PRIMARY KEY,table_id TEXT NOT NULL REFERENCES tables(id) ON DELETE CASCADE,
            state_json TEXT NOT NULL,state_sha256 TEXT NOT NULL,created_by {uid} REFERENCES users(id),created_at TEXT NOT NULL)""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_table_backup_table ON table_state_backups(table_id,created_at)")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_table_backup_hash ON table_state_backups(table_id,state_sha256)")


def prune_error_log(db, now: datetime | None = None) -> None:
    """Keep operational exceptions useful without allowing unbounded DB growth."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    cutoff = (current.astimezone(timezone.utc) - timedelta(days=ERROR_RETENTION_DAYS)).isoformat()
    with db.connect() as con:
        con.execute("DELETE FROM ops_error_log WHERE created_at<?", (cutoff,))


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * max(0.0, min(1.0, fraction))
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def api_latency_snapshot() -> dict[str, int | float | None]:
    samples = list(_API_LATENCY_MS)
    return {
        "samples": len(samples),
        "window": API_LATENCY_WINDOW,
        "p50_ms": round(_percentile(samples, 0.50), 2) if samples else None,
        "p95_ms": round(_percentile(samples, 0.95), 2) if samples else None,
        "max_ms": round(max(samples), 2) if samples else None,
    }


def websocket_snapshot(server) -> dict[str, Any]:
    connections = getattr(getattr(server, "hub", None), "connections", {}) or {}
    per_table: dict[str, int] = {}
    for table_id, rows in connections.items():
        try:
            count = len(rows or [])
        except TypeError:
            count = 0
        if count:
            per_table[str(table_id)] = int(count)
    return {"connections": sum(per_table.values()), "by_table": per_table}


def db_pool_snapshot(db) -> dict[str, Any]:
    if not bool(getattr(db, "IS_POSTGRES", False)):
        return {"backend": "sqlite", "enabled": False, "active": False}
    try:
        import runtime_performance

        pool = getattr(runtime_performance, "_POOL", None)
    except Exception:
        pool = None
    if pool is None:
        return {"backend": "postgres", "enabled": True, "active": False}
    try:
        raw = dict(pool.get_stats() or {})
    except Exception:
        return {"backend": "postgres", "enabled": True, "active": True, "stats_available": False}
    allowed = (
        "pool_min",
        "pool_max",
        "pool_size",
        "pool_available",
        "requests_waiting",
        "requests_num",
        "requests_queued",
        "requests_errors",
        "requests_wait_ms",
        "usage_ms",
        "connections_num",
        "connections_errors",
        "connections_lost",
    )
    stats = {key: raw[key] for key in allowed if key in raw}
    return {
        "backend": "postgres",
        "enabled": True,
        "active": True,
        "stats_available": True,
        **stats,
    }


async def event_loop_probe_ms() -> float:
    started = time.perf_counter()
    await asyncio.sleep(0)
    return round((time.perf_counter() - started) * 1000.0, 3)


def record_error(db, event_type: str, detail: str, method: str = "", path: str = "") -> None:
    try:
        with db.connect() as con:
            con.execute("INSERT INTO ops_error_log(id,event_type,method,path,detail,created_at) VALUES (?,?,?,?,?,?)",
                        ("err-" + uuid.uuid4().hex, event_type[:80], method[:20], path[:500], str(detail)[:5000], _now()))
    except Exception:
        pass


def backup_state(db, state: dict[str, Any], created_by: int | None = None) -> None:
    tid = str(state.get("id") or "")
    if not tid:
        return
    raw = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode()).hexdigest()
    try:
        with db.connect() as con:
            con.execute("""INSERT INTO table_state_backups(id,table_id,state_json,state_sha256,created_by,created_at)
                VALUES (?,?,?,?,?,?) ON CONFLICT(table_id,state_sha256) DO NOTHING""",
                ("tsb-" + uuid.uuid4().hex, tid, raw, digest, created_by, _now()))
            rows = con.execute("SELECT id FROM table_state_backups WHERE table_id=? ORDER BY created_at DESC", (tid,)).fetchall()
            for row in rows[KEEP_PER_TABLE:]:
                con.execute("DELETE FROM table_state_backups WHERE id=?", (row["id"],))
    except Exception as exc:
        record_error(db, "table_backup", f"{type(exc).__name__}: {exc}", path=tid)


def restore_invalid_tables(db) -> list[str]:
    restored = []
    with db.connect() as con:
        rows = con.execute("SELECT id,state_json FROM tables").fetchall()
    for row in rows:
        valid = False
        try:
            state = json.loads(row["state_json"])
            valid = isinstance(state, dict) and str(state.get("id")) == str(row["id"])
        except Exception:
            pass
        if valid:
            continue
        with db.connect() as con:
            backups = con.execute("SELECT id,state_json FROM table_state_backups WHERE table_id=? ORDER BY created_at DESC", (row["id"],)).fetchall()
        recovered = None
        for backup in backups:
            try:
                state = json.loads(backup["state_json"])
                if isinstance(state, dict) and str(state.get("id")) == str(row["id"]):
                    recovered = backup
                    break
            except Exception:
                continue
        if recovered:
            with db.connect() as con:
                con.execute("UPDATE tables SET state_json=?,updated_at=? WHERE id=?", (recovered["state_json"], _now(), row["id"]))
            restored.append(str(row["id"]))
            record_error(db, "table_auto_restore", f"restored from {recovered['id']}", path=str(row["id"]))
    return restored


def install(app, server, db, admin_console) -> None:
    if getattr(app.state, "jj_resilience_installed", False):
        return
    app.state.jj_resilience_installed = True
    _ensure_schema(db)
    prune_error_log(db)
    restore_invalid_tables(db)

    old_save = server.save_table
    if not getattr(server, "_jj_backup_save_wrapped", False):
        def save_table_with_backup(state):
            result = old_save(state)
            backup_state(db, state)
            return result
        server.save_table = save_table_with_backup
        server._jj_backup_save_wrapped = True

    @app.middleware("http")
    async def capture_errors(request: Request, call_next):
        track_latency = request.url.path.startswith("/api/")
        started = time.perf_counter() if track_latency else 0.0
        try:
            response = await call_next(request)
            if response.status_code >= 500:
                record_error(db, "http_5xx", f"HTTP {response.status_code}", request.method, request.url.path)
            return response
        except Exception as exc:
            record_error(db, "http_exception", "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)), request.method, request.url.path)
            raise
        finally:
            if track_latency:
                _API_LATENCY_MS.append((time.perf_counter() - started) * 1000.0)

    @app.get("/api/admin/console/resilience", include_in_schema=False)
    async def resilience_status(user=Depends(server.admin_user)):
        loop_probe = await event_loop_probe_ms()
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        with db.connect() as con:
            errors = [dict(r) for r in con.execute("SELECT * FROM ops_error_log ORDER BY created_at DESC LIMIT 12").fetchall()]
            count = con.execute("SELECT COUNT(*) c FROM ops_error_log WHERE created_at>=?", (since,)).fetchone()
            backups = con.execute("SELECT COUNT(*) c FROM table_state_backups").fetchone()
            per_table = [dict(r) for r in con.execute("SELECT table_id,COUNT(*) copies,MAX(created_at) latest FROM table_state_backups GROUP BY table_id ORDER BY table_id").fetchall()]
        runtime = {
            "api_latency": api_latency_snapshot(),
            "websocket": websocket_snapshot(server),
            "db_pool": db_pool_snapshot(db),
            "event_loop_probe_ms": loop_probe,
        }
        return {"errors_24h": int(count["c"] or 0), "recent_errors": errors,
                "backups": int(backups["c"] or 0), "backups_by_table": per_table,
                "keep_per_table": KEEP_PER_TABLE, "error_retention_days": ERROR_RETENTION_DAYS,
                "runtime": runtime}

    @app.get("/api/admin/console/table-backups", include_in_schema=False)
    def table_backups(table_id: str | None = None, user=Depends(server.admin_user)):
        with db.connect() as con:
            if table_id:
                rows = con.execute("SELECT id,table_id,state_sha256,created_at,LENGTH(state_json) bytes FROM table_state_backups WHERE table_id=? ORDER BY created_at DESC LIMIT 80", (table_id,)).fetchall()
            else:
                rows = con.execute("SELECT id,table_id,state_sha256,created_at,LENGTH(state_json) bytes FROM table_state_backups ORDER BY created_at DESC LIMIT 80").fetchall()
        return [dict(r) for r in rows]

    @app.post("/api/admin/console/table-backups/{backup_id}/restore", include_in_schema=False)
    def restore_backup(backup_id: str, payload: dict = Body(default={}), user=Depends(server.admin_user)):
        if str(payload.get("confirm") or "") != "RESTORE":
            raise HTTPException(400, "confirm=RESTORE が必要です")
        with db.connect() as con:
            row = con.execute("SELECT * FROM table_state_backups WHERE id=?", (backup_id,)).fetchone()
        if not row:
            raise HTTPException(404, "backup not found")
        try:
            state = json.loads(row["state_json"])
        except Exception:
            raise HTTPException(409, "backup state is invalid")
        current = server.load_table(str(row["table_id"]))
        backup_state(db, current, int(user["id"]))
        server.save_table(state)
        try:
            admin_console._audit(db, int(user["id"]), "table.restore", None, table_id=row["table_id"], backup_id=backup_id)
        except Exception:
            pass
        return {"ok": True, "table_id": row["table_id"], "backup_id": backup_id}
