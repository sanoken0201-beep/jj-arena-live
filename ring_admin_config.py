"""Admin-controlled ring rake and JST-calendar re-entry limits."""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

JST = ZoneInfo("Asia/Tokyo")
DEFAULT_RAKE_PERCENT = Decimal("5.00")
DEFAULT_RAKE_CAP_BB = Decimal("3.00")
DEFAULT_DAILY_REENTRY_LIMIT = 3

_INSTALLED = False
_ROUTE_ENDPOINTS: list[tuple[str, str, object]] = []
_user_buyin_locks: dict[int, asyncio.Lock] = {}


class RingSeatIn(BaseModel):
    seat: int = Field(ge=0, le=5)


class RingPresenceIn(BaseModel):
    mode: str = Field(pattern="^(sitout|cancel_sitout|return|rebuy|unready)$")


class RingConfigPatch(BaseModel):
    rake_percent: Decimal | None = Field(default=None, ge=0, le=100)
    rake_cap_bb: Decimal | None = Field(default=None, ge=0, le=100)
    daily_reentry_limit: int | None = Field(default=None, ge=0, le=50)


class ReentryResetIn(BaseModel):
    reason: str = Field(default="管理者による当日リエントリー回数リセット", min_length=1, max_length=300)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _jst_day(now: datetime | None = None) -> str:
    return (now or _now()).astimezone(JST).date().isoformat()


def _day_bounds(day: str) -> tuple[str, str]:
    start = datetime.combine(date.fromisoformat(day), time(), JST).astimezone(timezone.utc)
    return start.isoformat(), (start + timedelta(days=1)).isoformat()


def _scaled_exact(value: Decimal, scale: int, label: str) -> int:
    try:
        scaled = value * scale
        if scaled != scaled.to_integral_value():
            raise HTTPException(400, f"{label}は小数点以下2桁まで指定できます")
        return int(scaled)
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(400, f"{label}の値が不正です") from exc


def _ensure_schema(db) -> None:
    uid = "BIGINT" if db.IS_POSTGRES else "INTEGER"
    with db.connect() as con:
        con.execute(f"""CREATE TABLE IF NOT EXISTS ring_runtime_config(
            id INTEGER PRIMARY KEY,
            rake_bps INTEGER NOT NULL,
            rake_cap_hundredths_bb INTEGER NOT NULL,
            daily_reentry_limit INTEGER NOT NULL,
            updated_by {uid} REFERENCES users(id),
            updated_at TEXT NOT NULL)""")
        con.execute(f"""CREATE TABLE IF NOT EXISTS ring_buyin_events(
            id TEXT PRIMARY KEY,
            user_id {uid} NOT NULL REFERENCES users(id),
            table_id TEXT NOT NULL,
            jst_date TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK(event_type IN ('initial','reentry')),
            source TEXT NOT NULL,
            created_at TEXT NOT NULL)""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_ring_buyin_user_day ON ring_buyin_events(user_id,jst_date,created_at)")
        con.execute(f"""CREATE TABLE IF NOT EXISTS ring_reentry_resets(
            id TEXT PRIMARY KEY,
            user_id {uid} NOT NULL REFERENCES users(id),
            jst_date TEXT NOT NULL,
            reset_at TEXT NOT NULL,
            reset_by {uid} NOT NULL REFERENCES users(id),
            previous_count INTEGER NOT NULL,
            reason TEXT NOT NULL)""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_ring_reset_user_day ON ring_reentry_resets(user_id,jst_date,reset_at)")
        con.execute(f"""CREATE TABLE IF NOT EXISTS ring_config_audit(
            id TEXT PRIMARY KEY,
            action TEXT NOT NULL,
            actor_id {uid} NOT NULL REFERENCES users(id),
            target_user_id {uid} REFERENCES users(id),
            before_json TEXT,
            after_json TEXT,
            created_at TEXT NOT NULL)""")
        row = con.execute("SELECT id FROM ring_runtime_config WHERE id=1").fetchone()
        if not row:
            stamp = _now().isoformat()
            con.execute(
                """INSERT INTO ring_runtime_config(
                    id,rake_bps,rake_cap_hundredths_bb,daily_reentry_limit,updated_by,updated_at)
                    VALUES (1,?,?,?,?,?)""",
                (
                    _scaled_exact(DEFAULT_RAKE_PERCENT, 100, "レーキ率"),
                    _scaled_exact(DEFAULT_RAKE_CAP_BB, 100, "cap"),
                    DEFAULT_DAILY_REENTRY_LIMIT,
                    None,
                    stamp,
                ),
            )


def _config_row(con) -> dict:
    row = con.execute(
        """SELECT rake_bps,rake_cap_hundredths_bb,daily_reentry_limit,updated_by,updated_at
           FROM ring_runtime_config WHERE id=1"""
    ).fetchone()
    if not row:
        raise RuntimeError("ring runtime config is missing")
    return dict(row)


def _public_config(row: dict) -> dict:
    return {
        "rake_percent": float(Decimal(int(row["rake_bps"])) / Decimal(100)),
        "rake_cap_bb": float(Decimal(int(row["rake_cap_hundredths_bb"])) / Decimal(100)),
        "daily_reentry_limit": int(row["daily_reentry_limit"]),
        "updated_by": row.get("updated_by"),
        "updated_at": row.get("updated_at"),
    }


def get_config(db) -> dict:
    with db.connect() as con:
        return _public_config(_config_row(con))


def _lock_user_row(con, db, user_id: int) -> None:
    if db.IS_POSTGRES:
        row = con.execute("SELECT id FROM users WHERE id=? FOR UPDATE", (user_id,)).fetchone()
    else:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(404, "ユーザーが見つかりません")


def _latest_reset(con, user_id: int, day: str) -> str | None:
    row = con.execute(
        """SELECT reset_at FROM ring_reentry_resets
           WHERE user_id=? AND jst_date=? ORDER BY reset_at DESC LIMIT 1""",
        (user_id, day),
    ).fetchone()
    return str(row["reset_at"]) if row else None


def _reentry_used(con, user_id: int, day: str) -> int:
    reset_at = _latest_reset(con, user_id, day)
    if reset_at:
        row = con.execute(
            """SELECT COUNT(*) n FROM ring_buyin_events
               WHERE user_id=? AND jst_date=? AND event_type='reentry' AND created_at>?""",
            (user_id, day, reset_at),
        ).fetchone()
    else:
        row = con.execute(
            """SELECT COUNT(*) n FROM ring_buyin_events
               WHERE user_id=? AND jst_date=? AND event_type='reentry'""",
            (user_id, day),
        ).fetchone()
    return int(row["n"] or 0)


def _has_buyin_today(con, user_id: int, day: str) -> bool:
    return bool(con.execute(
        "SELECT 1 FROM ring_buyin_events WHERE user_id=? AND jst_date=? LIMIT 1",
        (user_id, day),
    ).fetchone())


def usage(db, user_id: int, day: str | None = None) -> dict:
    day = day or _jst_day()
    with db.connect() as con:
        cfg = _config_row(con)
        used = _reentry_used(con, user_id, day)
        total_buyins = int(con.execute(
            "SELECT COUNT(*) n FROM ring_buyin_events WHERE user_id=? AND jst_date=?",
            (user_id, day),
        ).fetchone()["n"] or 0)
        reset = _latest_reset(con, user_id, day)
    limit = int(cfg["daily_reentry_limit"])
    return {
        "date": day,
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "total_buyins": total_buyins,
        "last_reset_at": reset,
    }


def player_config(db, user_id: int) -> dict:
    cfg = get_config(db)
    cfg["reentries"] = usage(db, user_id)
    return cfg


def _reserve_buyin(db, user_id: int, table_id: str, source: str, *, force_reentry: bool) -> dict:
    day = _jst_day()
    stamp = _now().isoformat()
    event_id = "ring-buyin-" + uuid.uuid4().hex
    with db.connect() as con:
        _lock_user_row(con, db, user_id)
        cfg = _config_row(con)
        is_reentry = force_reentry or _has_buyin_today(con, user_id, day)
        used = _reentry_used(con, user_id, day)
        limit = int(cfg["daily_reentry_limit"])
        if is_reentry and used >= limit:
            raise HTTPException(
                409,
                f"本日のリエントリー上限（{limit}回）に達しています。日本時間0:00に更新されます",
            )
        con.execute(
            """INSERT INTO ring_buyin_events(id,user_id,table_id,jst_date,event_type,source,created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (event_id, user_id, table_id, day, "reentry" if is_reentry else "initial", source, stamp),
        )
    return {"id": event_id, "event_type": "reentry" if is_reentry else "initial", "date": day}


def _undo_buyin(db, event_id: str) -> None:
    try:
        with db.connect() as con:
            con.execute("DELETE FROM ring_buyin_events WHERE id=?", (event_id,))
    except Exception:
        pass


def _user_lock(user_id: int) -> asyncio.Lock:
    lock = _user_buyin_locks.get(int(user_id))
    if lock is None:
        lock = asyncio.Lock()
        _user_buyin_locks[int(user_id)] = lock
    return lock


def _apply_state_rake(state: dict, cfg: dict) -> None:
    bb = max(1, int(state.get("big_blind") or 1))
    percent = Decimal(str(cfg["rake_percent"])) / Decimal(100)
    cap_bb = Decimal(str(cfg["rake_cap_bb"]))
    state["rake_percent"] = float(percent)
    state["rake_cap"] = int(Decimal(bb) * cap_bb)


def _snapshot_hand_rake(state: dict, cfg: dict) -> None:
    hand = state.get("hand")
    if not isinstance(hand, dict):
        return
    hand["rake_percent_snapshot"] = float(Decimal(str(cfg["rake_percent"])) / Decimal(100))
    hand["rake_cap_bb_snapshot"] = float(Decimal(str(cfg["rake_cap_bb"])))


def _apply_waiting_tables(db) -> None:
    cfg = get_config(db)
    with db.connect() as con:
        rows = con.execute("SELECT id,state_json FROM tables").fetchall()
        fixed = {table_id for table_id, _name in getattr(db, "FIXED_TABLES", ())}
        for row in rows:
            if row["id"] not in fixed:
                continue
            state = json.loads(row["state_json"])
            if state.get("status") == "playing":
                continue
            _apply_state_rake(state, cfg)
            con.execute(
                "UPDATE tables SET state_json=?,updated_at=? WHERE id=?",
                (json.dumps(state, ensure_ascii=False), _now().isoformat(), row["id"]),
            )


def _seed_today_initial_buyins(db) -> None:
    day = _jst_day()
    start, end = _day_bounds(day)
    users: set[int] = set()
    with db.connect() as con:
        try:
            rows = con.execute(
                """SELECT DISTINCT r.user_id FROM online_hand_results r
                   JOIN online_hands h ON h.hand_id=r.hand_id
                   WHERE r.user_id IS NOT NULL AND h.played_at>=? AND h.played_at<?""",
                (start, end),
            ).fetchall()
            users.update(int(row["user_id"]) for row in rows if row["user_id"] is not None)
        except Exception:
            pass
        try:
            table_rows = con.execute("SELECT id,state_json FROM tables").fetchall()
            for row in table_rows:
                state = json.loads(row["state_json"])
                users.update(int(player["user_id"]) for player in state.get("seats", []) if player.get("user_id") is not None)
        except Exception:
            pass
        for uid in users:
            if _has_buyin_today(con, uid, day):
                continue
            con.execute(
                """INSERT INTO ring_buyin_events(id,user_id,table_id,jst_date,event_type,source,created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                ("ring-seed-" + day + "-" + str(uid), uid, "legacy", day, "initial", "deployment_seed", _now().isoformat()),
            )


def _install_hand_snapshot(server, db, poker_engine) -> None:
    if getattr(server, "_jj_ring_config_start_installed", False):
        return
    base_start = server.start_hand

    def start_hand_with_config(state: dict):
        cfg = get_config(db)
        _apply_state_rake(state, cfg)
        result = base_start(state)
        _snapshot_hand_rake(state, cfg)
        return result

    server.start_hand = start_hand_with_config
    poker_engine.start_hand = start_hand_with_config
    server._jj_ring_config_start_installed = True


def _install_waiting_table_policy(server, db) -> None:
    """Refresh the advertised policy as soon as a hand/session returns to waiting."""
    if getattr(server, "_jj_ring_config_save_installed", False):
        return
    original_save = server.save_table

    def save_table_with_config(state: dict):
        if state.get("status") != "playing":
            _apply_state_rake(state, get_config(db))
        return original_save(state)

    server.save_table = save_table_with_config
    server._jj_ring_config_save_installed = True


def _install_hand_history_policy(db) -> None:
    with db.connect() as con:
        if db.IS_POSTGRES:
            con.execute("ALTER TABLE online_hands ADD COLUMN IF NOT EXISTS rake_percent NUMERIC")
            con.execute("ALTER TABLE online_hands ADD COLUMN IF NOT EXISTS rake_cap_bb NUMERIC")
        else:
            columns = {str(row["name"]) for row in con.execute("PRAGMA table_info(online_hands)").fetchall()}
            if "rake_percent" not in columns:
                con.execute("ALTER TABLE online_hands ADD COLUMN rake_percent NUMERIC")
            if "rake_cap_bb" not in columns:
                con.execute("ALTER TABLE online_hands ADD COLUMN rake_cap_bb NUMERIC")

    original = db._record_online_hand
    if getattr(original, "_jj_ring_config_wrapped", False):
        return

    def record_with_policy(con, state):
        result = original(con, state)
        if result and result.get("hand_id"):
            hand = state.get("hand") or {}
            fraction = hand.get("rake_percent_snapshot")
            cap_bb = hand.get("rake_cap_bb_snapshot")
            if fraction is None:
                fraction = state.get("rake_percent")
            if cap_bb is None:
                bb = max(1, int(state.get("big_blind") or 1))
                cap_bb = Decimal(int(state.get("rake_cap") or 0)) / Decimal(bb)
            con.execute(
                "UPDATE online_hands SET rake_percent=?,rake_cap_bb=? WHERE hand_id=?",
                (float(fraction), float(cap_bb), result["hand_id"]),
            )
        return result

    record_with_policy._jj_ring_config_wrapped = True
    db._record_online_hand = record_with_policy


def _register_routes(app, server, db) -> None:
    original_sit = server.sit
    original_join = server.join_table
    original_presence = server.update_table_presence
    original_rebuy = server.rebuy

    @app.post("/api/tables/{table_id}/seat", include_in_schema=False)
    async def limited_seat(table_id: str, payload: RingSeatIn, user=Depends(server.current_user)):
        uid = int(user["id"])
        async with _user_lock(uid):
            state = server.load_table(table_id)
            if any(int(player.get("user_id", -1)) == uid for player in state.get("seats", [])):
                return await original_sit(table_id, server.SeatIn(seat=payload.seat), user)
            event = _reserve_buyin(db, uid, table_id, "seat", force_reentry=False)
            try:
                return await original_sit(table_id, server.SeatIn(seat=payload.seat), user)
            except Exception:
                _undo_buyin(db, event["id"])
                raise

    @app.post("/api/tables/{table_id}/join", include_in_schema=False)
    async def limited_join(table_id: str, user=Depends(server.current_user)):
        uid = int(user["id"])
        async with _user_lock(uid):
            state = server.load_table(table_id)
            if any(int(player.get("user_id", -1)) == uid for player in state.get("seats", [])):
                return await original_join(table_id, user)
            event = _reserve_buyin(db, uid, table_id, "join", force_reentry=False)
            try:
                return await original_join(table_id, user)
            except Exception:
                _undo_buyin(db, event["id"])
                raise

    @app.post("/api/tables/{table_id}/presence", include_in_schema=False)
    async def limited_presence(table_id: str, payload: RingPresenceIn, user=Depends(server.current_user)):
        if payload.mode != "rebuy":
            return await original_presence(table_id, server.TablePresenceIn(mode=payload.mode), user)
        uid = int(user["id"])
        async with _user_lock(uid):
            event = _reserve_buyin(db, uid, table_id, "presence_rebuy", force_reentry=True)
            try:
                return await original_presence(table_id, server.TablePresenceIn(mode=payload.mode), user)
            except Exception:
                _undo_buyin(db, event["id"])
                raise

    @app.post("/api/tables/{table_id}/rebuy", include_in_schema=False)
    async def limited_rebuy(table_id: str, user=Depends(server.current_user)):
        uid = int(user["id"])
        async with _user_lock(uid):
            event = _reserve_buyin(db, uid, table_id, "rebuy", force_reentry=True)
            try:
                return await original_rebuy(table_id, user)
            except Exception:
                _undo_buyin(db, event["id"])
                raise

    for path, method, endpoint in (
        ("/api/tables/{table_id}/seat", "POST", limited_seat),
        ("/api/tables/{table_id}/join", "POST", limited_join),
        ("/api/tables/{table_id}/presence", "POST", limited_presence),
        ("/api/tables/{table_id}/rebuy", "POST", limited_rebuy),
    ):
        _ROUTE_ENDPOINTS.append((path, method, endpoint))

    @app.get("/api/admin/console/ring-config", include_in_schema=False)
    def admin_ring_config(user=Depends(server.admin_user)):
        cfg = get_config(db)
        return cfg

    @app.patch("/api/admin/console/ring-config", include_in_schema=False)
    async def update_ring_config(payload: RingConfigPatch, user=Depends(server.admin_user)):
        with db.connect() as con:
            before_row = _config_row(con)
            before = _public_config(before_row)
            percent = Decimal(str(before["rake_percent"])) if payload.rake_percent is None else payload.rake_percent
            cap = Decimal(str(before["rake_cap_bb"])) if payload.rake_cap_bb is None else payload.rake_cap_bb
            limit = before["daily_reentry_limit"] if payload.daily_reentry_limit is None else payload.daily_reentry_limit
            bps = _scaled_exact(percent, 100, "レーキ率")
            cap100 = _scaled_exact(cap, 100, "cap")
            stamp = _now().isoformat()
            con.execute(
                """UPDATE ring_runtime_config
                   SET rake_bps=?,rake_cap_hundredths_bb=?,daily_reentry_limit=?,updated_by=?,updated_at=?
                   WHERE id=1""",
                (bps, cap100, int(limit), int(user["id"]), stamp),
            )
            after = {
                "rake_percent": float(Decimal(bps) / Decimal(100)),
                "rake_cap_bb": float(Decimal(cap100) / Decimal(100)),
                "daily_reentry_limit": int(limit),
                "updated_by": int(user["id"]),
                "updated_at": stamp,
            }
            con.execute(
                """INSERT INTO ring_config_audit(id,action,actor_id,target_user_id,before_json,after_json,created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    "ring-audit-" + uuid.uuid4().hex,
                    "config_update",
                    int(user["id"]),
                    None,
                    json.dumps(before, ensure_ascii=False, sort_keys=True),
                    json.dumps(after, ensure_ascii=False, sort_keys=True),
                    stamp,
                ),
            )
        # Apply only to tables that are currently between hands. Table locks
        # prevent a config save from overwriting a hand that starts concurrently.
        for table_id, _name in getattr(db, "FIXED_TABLES", ()):
            async with server.get_table_lock(table_id):
                state = server.load_table(table_id)
                if state.get("status") != "playing":
                    _apply_state_rake(state, after)
                    server.save_table(state)
            await server.hub.broadcast(table_id)
        return after

    @app.get("/api/admin/console/ring-reentries", include_in_schema=False)
    def admin_reentries(user=Depends(server.admin_user)):
        day = _jst_day()
        cfg = get_config(db)
        with db.connect() as con:
            rows = con.execute(
                """SELECT e.user_id,u.name,COALESCE(NULLIF(u.ranking_name,''),u.name) ranking_name,
                          SUM(CASE WHEN e.event_type='reentry' THEN 1 ELSE 0 END) reentries,
                          COUNT(*) total_buyins
                   FROM ring_buyin_events e JOIN users u ON u.id=e.user_id
                   WHERE e.jst_date=?
                   GROUP BY e.user_id,u.name,u.ranking_name ORDER BY ranking_name""",
                (day,),
            ).fetchall()
        items = []
        for row in rows:
            info = usage(db, int(row["user_id"]), day)
            items.append({
                "user_id": int(row["user_id"]),
                "name": row["name"],
                "ranking_name": row["ranking_name"],
                **info,
            })
        return {"date": day, "limit": cfg["daily_reentry_limit"], "items": items}

    @app.post("/api/admin/console/ring-reentries/{user_id}/reset", include_in_schema=False)
    def reset_reentries(user_id: int, payload: ReentryResetIn, user=Depends(server.admin_user)):
        day = _jst_day()
        stamp = _now().isoformat()
        with db.connect() as con:
            _lock_user_row(con, db, user_id)
            previous = _reentry_used(con, user_id, day)
            con.execute(
                """INSERT INTO ring_reentry_resets(id,user_id,jst_date,reset_at,reset_by,previous_count,reason)
                   VALUES (?,?,?,?,?,?,?)""",
                ("ring-reset-" + uuid.uuid4().hex, user_id, day, stamp, int(user["id"]), previous, payload.reason.strip()),
            )
            con.execute(
                """INSERT INTO ring_config_audit(id,action,actor_id,target_user_id,before_json,after_json,created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    "ring-audit-" + uuid.uuid4().hex,
                    "reentry_reset",
                    int(user["id"]),
                    user_id,
                    json.dumps({"used": previous, "date": day}, ensure_ascii=False, sort_keys=True),
                    json.dumps({"used": 0, "date": day}, ensure_ascii=False, sort_keys=True),
                    stamp,
                ),
            )
        return {"ok": True, "user_id": user_id, "date": day, "previous_count": previous, "used": 0}


def prioritize_routes(app) -> None:
    routes = list(app.router.routes)
    for path, method, endpoint in _ROUTE_ENDPOINTS:
        replacement = next((route for route in routes if getattr(route, "endpoint", None) is endpoint), None)
        if replacement is None:
            raise RuntimeError(f"ring override route missing: {method} {path}")
        routes.remove(replacement)
        matches = [
            index for index, route in enumerate(routes)
            if getattr(route, "path", None) == path and method in (getattr(route, "methods", None) or set())
        ]
        if not matches:
            raise RuntimeError(f"canonical ring route missing: {method} {path}")
        routes.insert(min(matches), replacement)
    app.router.routes[:] = routes


def install(app, server, db, poker_engine) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _ensure_schema(db)
    _install_hand_history_policy(db)
    _install_hand_snapshot(server, db, poker_engine)
    _install_waiting_table_policy(server, db)
    _apply_waiting_tables(db)
    _seed_today_initial_buyins(db)
    _register_routes(app, server, db)
    _INSTALLED = True
