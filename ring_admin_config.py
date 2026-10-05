from __future__ import annotations

"""Administrator-controlled Ring buy-ins and auditable rakeback settlement.

The immutable materialized Ring core stays unchanged. This extension owns only:
- the allowed buy-in range for future seats/rebuys;
- Ring seat/join/rebuy route adapters that accept a buy-in amount;
- an administrator view of collected rake;
- append-only rakeback settlement markers.

Existing seated stacks, completed hands, ranking results, and historical rake rows
are never rewritten by a settings change or rake reset.
"""

import asyncio
import json
import uuid
from decimal import Decimal
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

import admin_console


MIN_BUYIN_KEY = "ring_min_buyin_bb"
MAX_BUYIN_KEY = "ring_max_buyin_bb"
DEFAULT_BUYIN_BB = 150
MAX_CONFIGURED_BUYIN_BB = 1000


class RingSettingsPatch(BaseModel):
    min_buyin_bb: int = Field(ge=1, le=MAX_CONFIGURED_BUYIN_BB)
    max_buyin_bb: int = Field(ge=1, le=MAX_CONFIGURED_BUYIN_BB)


class RingSeatIn(BaseModel):
    seat: int = Field(ge=0, le=5)
    buyin_bb: int | None = Field(default=None, ge=1, le=MAX_CONFIGURED_BUYIN_BB)


class RingJoinIn(BaseModel):
    buyin_bb: int | None = Field(default=None, ge=1, le=MAX_CONFIGURED_BUYIN_BB)


class RingPresenceIn(BaseModel):
    mode: str = Field(pattern="^(sitout|cancel_sitout|return|rebuy|unready)$")
    buyin_bb: int | None = Field(default=None, ge=1, le=MAX_CONFIGURED_BUYIN_BB)


class RingRakeResetIn(BaseModel):
    note: str = Field(default="オフライン活動でレーキバック", max_length=200)


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _round_amount(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


def _get_setting(db, key: str, default: int) -> int:
    raw = admin_console._get(db, key, str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(1, min(MAX_CONFIGURED_BUYIN_BB, value))


def _settings(db) -> tuple[int, int]:
    minimum = _get_setting(db, MIN_BUYIN_KEY, DEFAULT_BUYIN_BB)
    maximum = _get_setting(db, MAX_BUYIN_KEY, DEFAULT_BUYIN_BB)
    if minimum > maximum:
        # Fail safe around manually corrupted app_settings without widening play.
        minimum = maximum = DEFAULT_BUYIN_BB
    return minimum, maximum


def _default_buyin_bb(minimum: int, maximum: int) -> int:
    return max(minimum, min(DEFAULT_BUYIN_BB, maximum))


def _ensure_schema(db) -> None:
    uid = "BIGINT" if getattr(db, "IS_POSTGRES", False) else "INTEGER"
    now = db.utcnow()
    with db.connect() as con:
        admin = con.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()
        actor = admin["id"] if admin else None
        for key, value in (
            (MIN_BUYIN_KEY, str(DEFAULT_BUYIN_BB)),
            (MAX_BUYIN_KEY, str(DEFAULT_BUYIN_BB)),
        ):
            if not con.execute("SELECT 1 FROM app_settings WHERE key=?", (key,)).fetchone():
                con.execute(
                    "INSERT INTO app_settings(key,value,updated_by,updated_at) VALUES (?,?,?,?)",
                    (key, value, actor, now),
                )
        con.execute(
            f"""CREATE TABLE IF NOT EXISTS ring_rake_settlements(
              id TEXT PRIMARY KEY,
              boundaries_json TEXT NOT NULL,
              settled_rake_bb REAL NOT NULL,
              settled_rake_points REAL NOT NULL,
              hand_count INTEGER NOT NULL,
              note TEXT NOT NULL DEFAULT '',
              created_by {uid} REFERENCES users(id),
              created_at TEXT NOT NULL
            )"""
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_ring_rake_settlement_created "
            "ON ring_rake_settlements(created_at)"
        )


def _apply_persisted_buyins_at_startup(db) -> None:
    minimum, maximum = _settings(db)
    with db.connect() as con:
        for table_id, _name in tuple(getattr(db, "FIXED_TABLES", ()) or ()):
            row = con.execute("SELECT state_json FROM tables WHERE id=?", (table_id,)).fetchone()
            if not row:
                continue
            state = json.loads(row["state_json"])
            bb = max(1, int(state.get("big_blind") or getattr(db, "TABLE_BB", 100) or 100))
            state["min_buyin"] = minimum * bb
            state["max_buyin"] = maximum * bb
            con.execute(
                "UPDATE tables SET state_json=?,updated_at=? WHERE id=?",
                (json.dumps(state, ensure_ascii=False), db.utcnow(), table_id),
            )


def _buyin_bounds(state: dict[str, Any]) -> tuple[int, int, int]:
    bb = max(1, int(state.get("big_blind") or 100))
    minimum = max(1, int(state.get("min_buyin") or DEFAULT_BUYIN_BB * bb))
    maximum = max(minimum, int(state.get("max_buyin") or minimum))
    return minimum, maximum, bb


def _resolve_buyin_stack(state: dict[str, Any], requested_bb: int | None) -> tuple[int, int]:
    minimum, maximum, bb = _buyin_bounds(state)
    min_bb = max(1, minimum // bb)
    max_bb = max(min_bb, maximum // bb)
    chosen_bb = (
        _default_buyin_bb(min_bb, max_bb)
        if requested_bb is None
        else int(requested_bb)
    )
    chips = chosen_bb * bb
    if chips < minimum or chips > maximum:
        raise HTTPException(
            400,
            f"バイインは {min_bb}bb〜{max_bb}bb の範囲で指定してください",
        )
    return chips, chosen_bb


def _latest_settlement(con) -> dict[str, Any] | None:
    row = con.execute(
        "SELECT id,boundaries_json,settled_rake_bb,settled_rake_points,hand_count,note,created_by,created_at "
        "FROM ring_rake_settlements ORDER BY created_at DESC,id DESC LIMIT 1"
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


def _rake_window(con, boundaries: dict[str, Any]) -> tuple[Decimal, int]:
    total = Decimal("0")
    hands = 0
    table_rows = con.execute(
        "SELECT DISTINCT table_id FROM online_hands ORDER BY table_id"
    ).fetchall()
    for row in table_rows:
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
        "SELECT COALESCE(SUM(rake_bb),0) rake_bb,COUNT(*) hands "
        "FROM online_hands WHERE COALESCE(voided,0)=0"
    ).fetchone()
    return _to_decimal(row["rake_bb"]), int(row["hands"] or 0)


def _current_boundaries(con) -> dict[str, int]:
    rows = con.execute(
        "SELECT table_id,COALESCE(MAX(hand_no),0) hand_no "
        "FROM online_hands GROUP BY table_id ORDER BY table_id"
    ).fetchall()
    return {str(row["table_id"]): int(row["hand_no"] or 0) for row in rows}


def _rake_payload(db, con) -> dict[str, Any]:
    last = _latest_settlement(con)
    boundaries = (last or {}).get("boundaries") or {}
    current_bb, current_hands = _rake_window(con, boundaries)
    all_bb, all_hands = _all_time_rake(con)
    bb_points = Decimal(str(int(getattr(db, "TABLE_BB", 100) or 100)))
    recent = con.execute(
        """SELECT id,settled_rake_bb,settled_rake_points,hand_count,note,created_at
           FROM ring_rake_settlements
           ORDER BY created_at DESC,id DESC LIMIT 10"""
    ).fetchall()
    last_public = None
    if last:
        last_public = {
            "id": last["id"],
            "settled_rake_bb": float(last["settled_rake_bb"] or 0),
            "settled_rake_points": float(last["settled_rake_points"] or 0),
            "hand_count": int(last["hand_count"] or 0),
            "note": str(last["note"] or ""),
            "created_at": last["created_at"],
        }
    return {
        "current": {
            "rake_bb": _round_amount(current_bb),
            "rake_points": _round_amount(current_bb * bb_points),
            "hands": current_hands,
        },
        "all_time": {
            "rake_bb": _round_amount(all_bb),
            "rake_points": _round_amount(all_bb * bb_points),
            "hands": all_hands,
        },
        "last_reset": last_public,
        "recent_resets": [dict(row) for row in recent],
    }


def ring_status(db) -> dict[str, Any]:
    minimum, maximum = _settings(db)
    with db.connect() as con:
        rake = _rake_payload(db, con)
    return {
        "min_buyin_bb": minimum,
        "max_buyin_bb": maximum,
        "default_buyin_bb": _default_buyin_bb(minimum, maximum),
        "rake": rake,
    }


def decorate_table_summaries(server, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decorated = []
    for raw in rows:
        item = dict(raw)
        try:
            state = server.load_table(str(item["id"]))
            minimum, maximum, bb = _buyin_bounds(state)
            min_bb = max(1, minimum // bb)
            max_bb = max(min_bb, maximum // bb)
            default_bb = _default_buyin_bb(min_bb, max_bb)
            item.update(
                min_buyin_bb=min_bb,
                max_buyin_bb=max_bb,
                default_buyin_bb=default_bb,
                starting_stack=default_bb * bb,
                starting_stack_bb=default_bb,
            )
        except Exception:
            pass
        decorated.append(item)
    return decorated


def _prioritize_route(app, path: str, method: str, endpoint) -> None:
    routes = list(app.router.routes)
    replacement = next(
        (route for route in routes if getattr(route, "endpoint", None) is endpoint),
        None,
    )
    if replacement is None:
        raise RuntimeError(f"Ring override route missing: {method} {path}")
    routes.remove(replacement)
    indexes = [
        index
        for index, route in enumerate(routes)
        if getattr(route, "path", None) == path
        and method in (getattr(route, "methods", None) or set())
    ]
    if not indexes:
        raise RuntimeError(f"Canonical Ring route missing: {method} {path}")
    routes.insert(min(indexes), replacement)
    app.router.routes[:] = routes


def install(app, db, server, poker_engine) -> None:
    if getattr(app.state, "jj_ring_admin_config_installed", False):
        return
    app.state.jj_ring_admin_config_installed = True

    _ensure_schema(db)
    _apply_persisted_buyins_at_startup(db)
    rake_reset_lock = asyncio.Lock()

    @app.get("/api/admin/console/ring")
    def admin_ring_status(user=Depends(server.admin_user)):
        return ring_status(db)

    @app.patch("/api/admin/console/ring")
    async def update_ring_settings(
        payload: RingSettingsPatch,
        user=Depends(server.admin_user),
    ):
        minimum = int(payload.min_buyin_bb)
        maximum = int(payload.max_buyin_bb)
        if minimum > maximum:
            raise HTTPException(400, "ミニマムバイインはMAXバイイン以下にしてください")

        table_ids = [table_id for table_id, _name in tuple(db.FIXED_TABLES)]
        locks = [server.get_table_lock(table_id) for table_id in table_ids]
        for lock in locks:
            await lock.acquire()
        try:
            now = db.utcnow()
            with db.connect() as con:
                before_min, before_max = _settings(db)
                for table_id in table_ids:
                    row = con.execute(
                        "SELECT state_json FROM tables WHERE id=?", (table_id,)
                    ).fetchone()
                    if not row:
                        continue
                    state = json.loads(row["state_json"])
                    bb = max(
                        1,
                        int(state.get("big_blind") or getattr(db, "TABLE_BB", 100) or 100),
                    )
                    state["min_buyin"] = minimum * bb
                    state["max_buyin"] = maximum * bb
                    con.execute(
                        "UPDATE tables SET state_json=?,updated_at=? WHERE id=?",
                        (json.dumps(state, ensure_ascii=False), now, table_id),
                    )
                for key, value in (
                    (MIN_BUYIN_KEY, str(minimum)),
                    (MAX_BUYIN_KEY, str(maximum)),
                ):
                    if con.execute(
                        "SELECT 1 FROM app_settings WHERE key=?", (key,)
                    ).fetchone():
                        con.execute(
                            "UPDATE app_settings SET value=?,updated_by=?,updated_at=? WHERE key=?",
                            (value, user["id"], now, key),
                        )
                    else:
                        con.execute(
                            "INSERT INTO app_settings(key,value,updated_by,updated_at) VALUES (?,?,?,?)",
                            (key, value, user["id"], now),
                        )
                admin_console._audit(
                    db,
                    int(user["id"]),
                    "ring.settings.update",
                    None,
                    con=con,
                    before={
                        "min_buyin_bb": before_min,
                        "max_buyin_bb": before_max,
                    },
                    after={
                        "min_buyin_bb": minimum,
                        "max_buyin_bb": maximum,
                    },
                )
        finally:
            for lock in reversed(locks):
                lock.release()
        return ring_status(db)

    @app.post("/api/admin/console/ring/rake-reset")
    async def reset_ring_rake(
        payload: RingRakeResetIn = RingRakeResetIn(),
        user=Depends(server.admin_user),
    ):
        async with rake_reset_lock:
            with db.connect() as con:
                previous = _latest_settlement(con)
                boundaries = (previous or {}).get("boundaries") or {}
                current_bb, hand_count = _rake_window(con, boundaries)
                if current_bb <= 0:
                    raise HTTPException(409, "未精算のレーキはありません")
                point_multiplier = Decimal(str(int(getattr(db, "TABLE_BB", 100) or 100)))
                settled_points = current_bb * point_multiplier
                new_boundaries = _current_boundaries(con)
                settlement_id = "rake-" + uuid.uuid4().hex
                created_at = db.utcnow()
                con.execute(
                    """INSERT INTO ring_rake_settlements(
                         id,boundaries_json,settled_rake_bb,settled_rake_points,
                         hand_count,note,created_by,created_at
                       ) VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        settlement_id,
                        json.dumps(new_boundaries, ensure_ascii=False, sort_keys=True),
                        float(current_bb),
                        float(settled_points),
                        int(hand_count),
                        payload.note.strip(),
                        user["id"],
                        created_at,
                    ),
                )
                admin_console._audit(
                    db,
                    int(user["id"]),
                    "ring.rake.reset",
                    None,
                    con=con,
                    settlement_id=settlement_id,
                    settled_rake_bb=_round_amount(current_bb),
                    settled_rake_points=_round_amount(settled_points),
                    hand_count=int(hand_count),
                    note=payload.note.strip(),
                )
            return ring_status(db)

    @app.post("/api/tables/{table_id}/seat", include_in_schema=False)
    async def seat_with_buyin(
        table_id: str,
        payload: RingSeatIn,
        user=Depends(server.current_user),
    ):
        async with server.table_membership_lock:
            other = server.seated_table_for_user(user["id"], exclude=table_id)
            if other:
                raise HTTPException(400, "別のテーブルに着席中です")
            async with server.get_table_lock(table_id):
                state = server.load_table(table_id)
                stack, _chosen_bb = _resolve_buyin_stack(state, payload.buyin_bb)
                try:
                    server.seat_player(
                        state,
                        user_id=user["id"],
                        name=user["name"],
                        seat=payload.seat,
                        stack=stack,
                    )
                except ValueError as exc:
                    raise HTTPException(400, str(exc)) from exc
                server.save_table(state)
        await server.hub.broadcast(table_id)
        return server.public_state(state, user["id"])

    @app.post("/api/tables/{table_id}/join", include_in_schema=False)
    async def join_with_buyin(
        table_id: str,
        payload: RingJoinIn | None = None,
        user=Depends(server.current_user),
    ):
        requested = payload.buyin_bb if payload is not None else None
        async with server.table_membership_lock:
            async with server.get_table_lock(table_id):
                state = server.load_table(table_id)
                existing = server._jj_table_user(state, user["id"])
                if existing:
                    return server.public_state(state, user["id"])

            other = server.seated_table_for_user(user["id"], exclude=table_id)
            if other:
                raise HTTPException(400, "別のテーブルに着席中です")

            async with server.get_table_lock(table_id):
                state = server.load_table(table_id)
                existing = server._jj_table_user(state, user["id"])
                if existing:
                    return server.public_state(state, user["id"])
                occupied = {
                    int(player.get("seat", -1)) for player in state.get("seats", [])
                }
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
                stack, _chosen_bb = _resolve_buyin_stack(state, requested)
                live_session = bool(state.get("session_active")) or state.get("status") == "playing"
                try:
                    server.seat_player(
                        state,
                        user_id=user["id"],
                        name=user["name"],
                        seat=chosen,
                        stack=stack,
                    )
                except ValueError as exc:
                    raise HTTPException(400, str(exc)) from exc

                player = server._jj_table_user(state, user["id"])
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

        await server.hub.broadcast(table_id)
        return server.public_state(state, user["id"])

    @app.post("/api/tables/{table_id}/presence", include_in_schema=False)
    async def presence_with_buyin(
        table_id: str,
        payload: RingPresenceIn,
        user=Depends(server.current_user),
    ):
        async with server.get_table_lock(table_id):
            state = server.load_table(table_id)
            player = server._jj_table_user(state, user["id"])
            if not player:
                raise HTTPException(400, "このテーブルに着席していません")
            mode = payload.mode
            if mode == "sitout":
                if state.get("status") == "playing" and player.get("in_hand"):
                    player["sit_out_next"] = True
                else:
                    player["sitting_out"] = True
                    player["sit_out_next"] = False
                    player["ready"] = False
            elif mode == "cancel_sitout":
                player["sit_out_next"] = False
            elif mode == "unready":
                if state.get("status") == "playing" or bool(state.get("session_active")):
                    raise HTTPException(400, "開始後はREADYを取り消せません")
                player["ready"] = False
            elif mode == "return":
                if int(player.get("stack", 0)) <= 0:
                    raise HTTPException(400, "0bbのため復帰するにはRebuyが必要です")
                player["sitting_out"] = False
                player["sit_out_next"] = False
                if not bool(state.get("session_active")):
                    player["ready"] = False
            elif mode == "rebuy":
                if state.get("status") == "playing":
                    raise HTTPException(400, "ハンド終了後にRebuyしてください")
                if int(player.get("stack", 0)) != 0:
                    raise HTTPException(400, "Rebuyは0bbのときだけ利用できます")
                stack, _chosen_bb = _resolve_buyin_stack(state, payload.buyin_bb)
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
        await server.hub.broadcast(table_id)
        return server.public_state(state, user["id"])

    @app.post("/api/tables/{table_id}/rebuy", include_in_schema=False)
    async def legacy_rebuy_with_buyin(
        table_id: str,
        payload: RingJoinIn | None = None,
        user=Depends(server.current_user),
    ):
        requested = payload.buyin_bb if payload is not None else None
        async with server.get_table_lock(table_id):
            state = server.load_table(table_id)
            if state.get("status") == "playing":
                raise HTTPException(400, "ハンド中はリバイできません")
            player = server._jj_table_user(state, user["id"])
            if not player:
                raise HTTPException(400, "着席していません")
            if int(player.get("stack", 0)) != 0:
                raise HTTPException(400, "Rebuyは0bbのときだけ利用できます")
            stack, _chosen_bb = _resolve_buyin_stack(state, requested)
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
            server.touch_presence(table_id, user["id"])
            server.save_table(state)
        await server.hub.broadcast(table_id)
        return server.public_state(state, user["id"])

    _prioritize_route(app, "/api/tables/{table_id}/seat", "POST", seat_with_buyin)
    _prioritize_route(app, "/api/tables/{table_id}/join", "POST", join_with_buyin)
    _prioritize_route(app, "/api/tables/{table_id}/presence", "POST", presence_with_buyin)
    _prioritize_route(app, "/api/tables/{table_id}/rebuy", "POST", legacy_rebuy_with_buyin)


__all__ = [
    "DEFAULT_BUYIN_BB",
    "MAX_BUYIN_KEY",
    "MIN_BUYIN_KEY",
    "decorate_table_summaries",
    "install",
    "ring_status",
]
