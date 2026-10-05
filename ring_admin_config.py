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
DEFAULT_MIN_BUYIN_BB = 150
DEFAULT_MAX_BUYIN_BB = 150
MAX_CONFIGURED_BUYIN_BB = 1000

_INSTALLED = False
_ROUTE_ENDPOINTS: list[tuple[str, str, object]] = []
_user_buyin_locks: dict[int, asyncio.Lock] = {}
_rake_reset_lock = asyncio.Lock()


class RingSeatIn(BaseModel):
    seat: int = Field(ge=0, le=5)
    buyin_bb: int | None = Field(default=None, ge=1, le=MAX_CONFIGURED_BUYIN_BB)


class RingJoinIn(BaseModel):
    buyin_bb: int | None = Field(default=None, ge=1, le=MAX_CONFIGURED_BUYIN_BB)


class RingPresenceIn(BaseModel):
    mode: str = Field(pattern="^(sitout|cancel_sitout|return|rebuy|unready)$")
    buyin_bb: int | None = Field(default=None, ge=1, le=MAX_CONFIGURED_BUYIN_BB)


class RingConfigPatch(BaseModel):
    rake_percent: Decimal | None = Field(default=None, ge=0, le=100)
    rake_cap_bb: Decimal | None = Field(default=None, ge=0, le=100)
    daily_reentry_limit: int | None = Field(default=None, ge=0, le=50)
    min_buyin_bb: int | None = Field(default=None, ge=1, le=MAX_CONFIGURED_BUYIN_BB)
    max_buyin_bb: int | None = Field(default=None, ge=1, le=MAX_CONFIGURED_BUYIN_BB)


class ReentryResetIn(BaseModel):
    reason: str = Field(default="管理者による当日リエントリー回数リセット", min_length=1, max_length=300)


class RakeResetIn(BaseModel):
    note: str = Field(default="オフライン活動でレーキバック", max_length=300)


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
            min_buyin_bb INTEGER NOT NULL DEFAULT 150,
            max_buyin_bb INTEGER NOT NULL DEFAULT 150,
            updated_by {uid} REFERENCES users(id),
            updated_at TEXT NOT NULL)""")
        if db.IS_POSTGRES:
            con.execute("ALTER TABLE ring_runtime_config ADD COLUMN IF NOT EXISTS min_buyin_bb INTEGER NOT NULL DEFAULT 150")
            con.execute("ALTER TABLE ring_runtime_config ADD COLUMN IF NOT EXISTS max_buyin_bb INTEGER NOT NULL DEFAULT 150")
        else:
            config_columns = {str(row["name"]) for row in con.execute("PRAGMA table_info(ring_runtime_config)").fetchall()}
            if "min_buyin_bb" not in config_columns:
                con.execute("ALTER TABLE ring_runtime_config ADD COLUMN min_buyin_bb INTEGER NOT NULL DEFAULT 150")
            if "max_buyin_bb" not in config_columns:
                con.execute("ALTER TABLE ring_runtime_config ADD COLUMN max_buyin_bb INTEGER NOT NULL DEFAULT 150")
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
        con.execute(f"""CREATE TABLE IF NOT EXISTS ring_rake_settlements(
            id TEXT PRIMARY KEY,
            boundaries_json TEXT NOT NULL,
            settled_rake_bb NUMERIC NOT NULL,
            settled_rake_points NUMERIC NOT NULL,
            points_per_bb NUMERIC,
            hand_count INTEGER NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            created_by {uid} REFERENCES users(id),
            created_at TEXT NOT NULL)""")
        if db.IS_POSTGRES:
            con.execute("ALTER TABLE ring_rake_settlements ADD COLUMN IF NOT EXISTS points_per_bb NUMERIC")
        else:
            settlement_columns = {str(row["name"]) for row in con.execute("PRAGMA table_info(ring_rake_settlements)").fetchall()}
            if "points_per_bb" not in settlement_columns:
                con.execute("ALTER TABLE ring_rake_settlements ADD COLUMN points_per_bb NUMERIC")
        con.execute("CREATE INDEX IF NOT EXISTS idx_ring_rake_settlement_created ON ring_rake_settlements(created_at)")
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
                    id,rake_bps,rake_cap_hundredths_bb,daily_reentry_limit,
                    min_buyin_bb,max_buyin_bb,updated_by,updated_at)
                    VALUES (1,?,?,?,?,?,?,?)""",
                (
                    _scaled_exact(DEFAULT_RAKE_PERCENT, 100, "レーキ率"),
                    _scaled_exact(DEFAULT_RAKE_CAP_BB, 100, "cap"),
                    DEFAULT_DAILY_REENTRY_LIMIT,
                    DEFAULT_MIN_BUYIN_BB,
                    DEFAULT_MAX_BUYIN_BB,
                    None,
                    stamp,
                ),
            )


def _config_row(con) -> dict:
    row = con.execute(
        """SELECT rake_bps,rake_cap_hundredths_bb,daily_reentry_limit,
                  min_buyin_bb,max_buyin_bb,updated_by,updated_at
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
        "min_buyin_bb": int(row["min_buyin_bb"]),
        "max_buyin_bb": int(row["max_buyin_bb"]),
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


def _ordered_buyin_stamp(con, user_id: int, day: str) -> str:
    """Return a timestamp that is strictly after the latest admin reset."""
    stamp = _now()
    reset_at = _latest_reset(con, user_id, day)
    if reset_at:
        reset_stamp = datetime.fromisoformat(reset_at)
        if stamp <= reset_stamp:
            stamp = reset_stamp + timedelta(microseconds=1)
    return stamp.isoformat()


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
    event_id = "ring-buyin-" + uuid.uuid4().hex
    with db.connect() as con:
        _lock_user_row(con, db, user_id)
        stamp = _ordered_buyin_stamp(con, user_id, day)
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


def _resolve_buyin_bb(cfg: dict, requested_bb: int | None) -> int:
    minimum = int(cfg["min_buyin_bb"])
    maximum = int(cfg["max_buyin_bb"])
    if minimum > maximum:
        raise RuntimeError("ring buy-in config is invalid")
    chosen = max(minimum, min(DEFAULT_MAX_BUYIN_BB, maximum)) if requested_bb is None else int(requested_bb)
    if chosen < minimum or chosen > maximum:
        raise HTTPException(400, f"バイインは {minimum}bb〜{maximum}bb の範囲で指定してください")
    return chosen


def _resolve_buyin_stack(state: dict, cfg: dict, requested_bb: int | None) -> tuple[int, int]:
    chosen = _resolve_buyin_bb(cfg, requested_bb)
    bb = max(1, int(state.get("big_blind") or 100))
    return chosen * bb, chosen


def _apply_state_buyins(state: dict, cfg: dict) -> None:
    bb = max(1, int(state.get("big_blind") or 1))
    state["min_buyin"] = int(cfg["min_buyin_bb"]) * bb
    state["max_buyin"] = int(cfg["max_buyin_bb"]) * bb


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
            _apply_state_buyins(state, cfg)
            if state.get("status") != "playing":
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
            cfg = get_config(db)
            _apply_state_buyins(state, cfg)
            _apply_state_rake(state, cfg)
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
                fraction = state.get("rake_percent", getattr(db, "RAKE_PERCENT", 0.05))
            if cap_bb is None:
                bb = max(1, int(state.get("big_blind") or getattr(db, "TABLE_BB", 1) or 1))
                if state.get("rake_cap") is not None:
                    cap_bb = Decimal(int(state.get("rake_cap") or 0)) / Decimal(bb)
                else:
                    cap_bb = Decimal(str(getattr(db, "RAKE_CAP_BB", 3)))
            con.execute(
                "UPDATE online_hands SET rake_percent=?,rake_cap_bb=? WHERE hand_id=?",
                (float(fraction), float(cap_bb), result["hand_id"]),
            )
        return result

    record_with_policy._jj_ring_config_wrapped = True
    db._record_online_hand = record_with_policy


def decorate_table_summaries(db, rows: list[dict], *, con=None) -> list[dict]:
    if con is None:
        cfg = get_config(db)
    else:
        cfg = _public_config(_config_row(con))
    minimum = int(cfg["min_buyin_bb"])
    maximum = int(cfg["max_buyin_bb"])
    default = max(minimum, min(DEFAULT_MAX_BUYIN_BB, maximum))
    out = []
    for raw in rows:
        item = dict(raw)
        bb = max(1, int(item.get("big_blind") or getattr(db, "TABLE_BB", 100) or 100))
        item.update(
            min_buyin_bb=minimum,
            max_buyin_bb=maximum,
            default_buyin_bb=default,
            starting_stack=default * bb,
            starting_stack_bb=default,
        )
        out.append(item)
    return out


def _to_decimal(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _round_amount(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


def _rake_points_per_bb(db) -> Decimal:
    """Use the same BB→ranking-point conversion as online results.

    TABLE_BB is a chip denomination (100 chips per BB), not a point multiplier.
    Keeping those concepts separate prevents a 100x-looking rakeback display.
    """
    value = _to_decimal(getattr(db, "ONLINE_POINTS_PER_BB", 3))
    return value if value > 0 else Decimal("3")


def _latest_rake_settlement(con) -> dict | None:
    row = con.execute(
        """SELECT id,boundaries_json,settled_rake_bb,settled_rake_points,points_per_bb,
                  hand_count,note,created_by,created_at
           FROM ring_rake_settlements ORDER BY created_at DESC,id DESC LIMIT 1"""
    ).fetchone()
    if not row:
        return None
    item = dict(row)
    try:
        item["boundaries"] = json.loads(item.pop("boundaries_json") or "{}")
    except Exception:
        item["boundaries"] = {}
        item.pop("boundaries_json", None)
    return item


def _rake_window(con, boundaries: dict) -> tuple[Decimal, int]:
    total = Decimal("0")
    hands = 0
    rows = con.execute("SELECT DISTINCT table_id FROM online_hands ORDER BY table_id").fetchall()
    for row in rows:
        table_id = str(row["table_id"])
        try:
            boundary = int(boundaries.get(table_id, 0) or 0)
        except (TypeError, ValueError):
            boundary = 0
        current = con.execute(
            """SELECT COALESCE(SUM(rake_bb),0) rake_bb,COUNT(*) hands
               FROM online_hands
               WHERE table_id=? AND hand_no>? AND COALESCE(voided,0)=0""",
            (table_id, boundary),
        ).fetchone()
        total += _to_decimal(current["rake_bb"])
        hands += int(current["hands"] or 0)
    return total, hands


def _all_time_rake(con) -> tuple[Decimal, int]:
    row = con.execute(
        "SELECT COALESCE(SUM(rake_bb),0) rake_bb,COUNT(*) hands FROM online_hands WHERE COALESCE(voided,0)=0"
    ).fetchone()
    return _to_decimal(row["rake_bb"]), int(row["hands"] or 0)


def _current_rake_boundaries(con) -> dict[str, int]:
    rows = con.execute(
        "SELECT table_id,COALESCE(MAX(hand_no),0) hand_no FROM online_hands GROUP BY table_id ORDER BY table_id"
    ).fetchall()
    return {str(row["table_id"]): int(row["hand_no"] or 0) for row in rows}


def rake_summary(db) -> dict:
    with db.connect() as con:
        last = _latest_rake_settlement(con)
        boundaries = (last or {}).get("boundaries") or {}
        current_bb, current_hands = _rake_window(con, boundaries)
        all_bb, all_hands = _all_time_rake(con)
        recent = con.execute(
            """SELECT id,settled_rake_bb,settled_rake_points,points_per_bb,hand_count,note,created_at
               FROM ring_rake_settlements ORDER BY created_at DESC,id DESC LIMIT 10"""
        ).fetchall()
    multiplier = _rake_points_per_bb(db)

    def settlement_public(raw) -> dict:
        item = dict(raw)
        rake_bb = _to_decimal(item.get("settled_rake_bb"))
        stored_rate = item.get("points_per_bb")
        rate = multiplier if stored_rate is None else _to_decimal(stored_rate)
        if rate <= 0:
            rate = multiplier
        return {
            "id": item["id"],
            "settled_rake_bb": _round_amount(rake_bb),
            # Legacy rows created by the broken 100x conversion may contain an
            # inflated stored value. Recompute from BB using the snapshotted
            # conversion rate when available, or the current canonical rate.
            "settled_rake_points": _round_amount(rake_bb * rate),
            "points_per_bb": _round_amount(rate),
            "hand_count": int(item["hand_count"] or 0),
            "note": str(item["note"] or ""),
            "created_at": item["created_at"],
        }

    return {
        "points_per_bb": _round_amount(multiplier),
        "current": {
            "rake_bb": _round_amount(current_bb),
            "rake_points": _round_amount(current_bb * multiplier),
            "hands": current_hands,
        },
        "all_time": {
            "rake_bb": _round_amount(all_bb),
            "rake_points": _round_amount(all_bb * multiplier),
            "hands": all_hands,
        },
        "last_reset": settlement_public(last) if last else None,
        "recent_resets": [settlement_public(row) for row in recent],
    }


def _register_routes(app, server, db) -> None:
    @app.post("/api/tables/{table_id}/seat", include_in_schema=False)
    async def limited_seat(table_id: str, payload: RingSeatIn, user=Depends(server.current_user)):
        uid = int(user["id"])
        async with _user_lock(uid):
            async with server.table_membership_lock:
                other = server.seated_table_for_user(uid, exclude=table_id)
                if other:
                    raise HTTPException(400, "別のテーブルに着席中です")
                async with server.get_table_lock(table_id):
                    state = server.load_table(table_id)
                    if server._jj_table_user(state, uid):
                        raise HTTPException(400, "すでに着席しています")
                    cfg = get_config(db)
                    stack, _chosen_bb = _resolve_buyin_stack(state, cfg, payload.buyin_bb)
                    event = _reserve_buyin(db, uid, table_id, "seat", force_reentry=False)
                    try:
                        server.seat_player(
                            state,
                            user_id=uid,
                            name=user["name"],
                            seat=payload.seat,
                            stack=stack,
                        )
                        server.save_table(state)
                    except Exception:
                        _undo_buyin(db, event["id"])
                        raise
        await server.hub.broadcast(table_id)
        return server.public_state(state, uid)

    @app.post("/api/tables/{table_id}/join", include_in_schema=False)
    async def limited_join(
        table_id: str,
        payload: RingJoinIn | None = None,
        user=Depends(server.current_user),
    ):
        uid = int(user["id"])
        requested = payload.buyin_bb if payload is not None else None
        async with _user_lock(uid):
            async with server.table_membership_lock:
                async with server.get_table_lock(table_id):
                    state = server.load_table(table_id)
                    existing = server._jj_table_user(state, uid)
                    if existing:
                        return server.public_state(state, uid)

                other = server.seated_table_for_user(uid, exclude=table_id)
                if other:
                    raise HTTPException(400, "別のテーブルに着席中です")

                async with server.get_table_lock(table_id):
                    state = server.load_table(table_id)
                    existing = server._jj_table_user(state, uid)
                    if existing:
                        return server.public_state(state, uid)
                    occupied = {int(player.get("seat", -1)) for player in state.get("seats", [])}
                    free = [
                        seat
                        for seat in range(int(state.get("max_seats", 6)))
                        if seat not in occupied
                    ]
                    if not free:
                        raise HTTPException(409, "このテーブルは満席です")
                    button = int(state.get("button_seat", -1))
                    free.sort(
                        key=lambda seat: (
                            (seat - button) % int(state.get("max_seats", 6))
                        )
                    )
                    chosen = free[0]
                    cfg = get_config(db)
                    stack, _chosen_bb = _resolve_buyin_stack(state, cfg, requested)
                    live_session = bool(state.get("session_active")) or state.get("status") == "playing"
                    event = _reserve_buyin(db, uid, table_id, "join", force_reentry=False)
                    try:
                        server.seat_player(
                            state,
                            user_id=uid,
                            name=user["name"],
                            seat=chosen,
                            stack=stack,
                        )
                        player = server._jj_table_user(state, uid)
                        if player and live_session:
                            player["sitting_out"] = False
                            player["sit_out_next"] = False
                            player["ready"] = False
                            player["in_hand"] = False
                            player["folded"] = False
                            player["all_in"] = False
                            player["round_bet"] = 0
                            player["contributed"] = 0
                            player["cards"] = []
                        server.save_table(state)
                    except Exception:
                        _undo_buyin(db, event["id"])
                        raise
        await server.hub.broadcast(table_id)
        return server.public_state(state, uid)

    @app.post("/api/tables/{table_id}/presence", include_in_schema=False)
    async def limited_presence(table_id: str, payload: RingPresenceIn, user=Depends(server.current_user)):
        if payload.mode != "rebuy":
            return await server.update_table_presence(
                table_id,
                server.TablePresenceIn(mode=payload.mode),
                user,
            )
        uid = int(user["id"])
        async with _user_lock(uid):
            async with server.get_table_lock(table_id):
                state = server.load_table(table_id)
                player = server._jj_table_user(state, uid)
                if not player:
                    raise HTTPException(400, "このテーブルに着席していません")
                if state.get("status") == "playing":
                    raise HTTPException(400, "ハンド終了後にRebuyしてください")
                if int(player.get("stack", 0)) != 0:
                    raise HTTPException(400, "Rebuyは0bbのときだけ利用できます")
                cfg = get_config(db)
                stack, _chosen_bb = _resolve_buyin_stack(state, cfg, payload.buyin_bb)
                event = _reserve_buyin(db, uid, table_id, "presence_rebuy", force_reentry=True)
                try:
                    player.update({
                        "stack": stack,
                        "in_hand": False,
                        "folded": False,
                        "all_in": False,
                        "round_bet": 0,
                        "contributed": 0,
                        "cards": [],
                        "sitting_out": False,
                        "sit_out_next": False,
                        "ready": False,
                    })
                    active = server._jj_table_active_players(state)
                    if len(active) < 2 and state.get("status") != "playing":
                        state["session_active"] = False
                        state["next_hand_at_epoch"] = None
                    server.save_table(state)
                except Exception:
                    _undo_buyin(db, event["id"])
                    raise
        await server.hub.broadcast(table_id)
        return server.public_state(state, uid)

    @app.post("/api/tables/{table_id}/rebuy", include_in_schema=False)
    async def limited_rebuy(
        table_id: str,
        payload: RingJoinIn | None = None,
        user=Depends(server.current_user),
    ):
        uid = int(user["id"])
        requested = payload.buyin_bb if payload is not None else None
        async with _user_lock(uid):
            async with server.get_table_lock(table_id):
                state = server.load_table(table_id)
                if state.get("status") == "playing":
                    raise HTTPException(400, "ハンド中はリバイできません")
                player = server._jj_table_user(state, uid)
                if not player:
                    raise HTTPException(400, "着席していません")
                if int(player.get("stack", 0)) != 0:
                    raise HTTPException(400, "Rebuyは0bbのときだけ利用できます")
                cfg = get_config(db)
                stack, _chosen_bb = _resolve_buyin_stack(state, cfg, requested)
                event = _reserve_buyin(db, uid, table_id, "rebuy", force_reentry=True)
                try:
                    player.update({
                        "stack": stack,
                        "in_hand": False,
                        "folded": False,
                        "all_in": False,
                        "round_bet": 0,
                        "contributed": 0,
                        "cards": [],
                        "sitting_out": False,
                        "sit_out_next": False,
                        "ready": False,
                    })
                    server.touch_presence(table_id, uid)
                    server.save_table(state)
                except Exception:
                    _undo_buyin(db, event["id"])
                    raise
        await server.hub.broadcast(table_id)
        return server.public_state(state, uid)

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
            minimum = before["min_buyin_bb"] if payload.min_buyin_bb is None else int(payload.min_buyin_bb)
            maximum = before["max_buyin_bb"] if payload.max_buyin_bb is None else int(payload.max_buyin_bb)
            if minimum > maximum:
                raise HTTPException(400, "ミニマムバイインはMAXバイイン以下にしてください")
            bps = _scaled_exact(percent, 100, "レーキ率")
            cap100 = _scaled_exact(cap, 100, "cap")
            stamp = _now().isoformat()
            con.execute(
                """UPDATE ring_runtime_config
                   SET rake_bps=?,rake_cap_hundredths_bb=?,daily_reentry_limit=?,
                       min_buyin_bb=?,max_buyin_bb=?,updated_by=?,updated_at=?
                   WHERE id=1""",
                (bps, cap100, int(limit), minimum, maximum, int(user["id"]), stamp),
            )
            after = {
                "rake_percent": float(Decimal(bps) / Decimal(100)),
                "rake_cap_bb": float(Decimal(cap100) / Decimal(100)),
                "daily_reentry_limit": int(limit),
                "min_buyin_bb": minimum,
                "max_buyin_bb": maximum,
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
                _apply_state_buyins(state, after)
                if state.get("status") != "playing":
                    _apply_state_rake(state, after)
                server.save_table(state)
            await server.hub.broadcast(table_id)
        return after

    @app.get("/api/admin/console/ring-rake", include_in_schema=False)
    def admin_ring_rake(user=Depends(server.admin_user)):
        return rake_summary(db)

    @app.post("/api/admin/console/ring-rake/reset", include_in_schema=False)
    async def reset_ring_rake(payload: RakeResetIn = RakeResetIn(), user=Depends(server.admin_user)):
        table_ids = [table_id for table_id, _name in getattr(db, "FIXED_TABLES", ())]
        locks = [server.get_table_lock(table_id) for table_id in table_ids]
        async with _rake_reset_lock:
            for lock in locks:
                await lock.acquire()
            try:
                with db.connect() as con:
                    previous = _latest_rake_settlement(con)
                    boundaries = (previous or {}).get("boundaries") or {}
                    current_bb, hand_count = _rake_window(con, boundaries)
                    if current_bb <= 0:
                        raise HTTPException(409, "未精算のレーキはありません")
                    multiplier = _rake_points_per_bb(db)
                    settled_points = current_bb * multiplier
                    new_boundaries = _current_rake_boundaries(con)
                    settlement_id = "ring-rake-" + uuid.uuid4().hex
                    stamp_dt = _now()
                    if previous and previous.get("created_at"):
                        previous_stamp = datetime.fromisoformat(str(previous["created_at"]))
                        if stamp_dt <= previous_stamp:
                            stamp_dt = previous_stamp + timedelta(microseconds=1)
                    stamp = stamp_dt.isoformat()
                    note = payload.note.strip() or "オフライン活動でレーキバック"
                    con.execute(
                        """INSERT INTO ring_rake_settlements(
                             id,boundaries_json,settled_rake_bb,settled_rake_points,points_per_bb,
                             hand_count,note,created_by,created_at)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (
                            settlement_id,
                            json.dumps(new_boundaries, ensure_ascii=False, sort_keys=True),
                            float(current_bb),
                            float(settled_points),
                            float(multiplier),
                            int(hand_count),
                            note,
                            int(user["id"]),
                            stamp,
                        ),
                    )
                    con.execute(
                        """INSERT INTO ring_config_audit(
                             id,action,actor_id,target_user_id,before_json,after_json,created_at)
                           VALUES (?,?,?,?,?,?,?)""",
                        (
                            "ring-audit-" + uuid.uuid4().hex,
                            "rake_settlement_reset",
                            int(user["id"]),
                            None,
                            json.dumps({
                                "rake_bb": _round_amount(current_bb),
                                "rake_points": _round_amount(settled_points),
                                "hands": int(hand_count),
                            }, ensure_ascii=False, sort_keys=True),
                            json.dumps({
                                "rake_bb": 0,
                                "rake_points": 0,
                                "settlement_id": settlement_id,
                            }, ensure_ascii=False, sort_keys=True),
                            stamp,
                        ),
                    )
            finally:
                for lock in reversed(locks):
                    lock.release()
        return rake_summary(db)

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
