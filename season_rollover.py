"""Audited and guarded transition to the next official JJ season.

Activation never deletes or rewrites historical entries, hand results or ledger.
The date-filtered active ranking is empty when the new season has no results.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

import admin_role_delegation
import season_management


class ActivateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_current_season_id: str = Field(min_length=1, max_length=80)
    current_pin: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$")
    confirmation: Literal["START NEW SEASON"]


def today_jst() -> str:
    return datetime.now(timezone.utc).astimezone(ZoneInfo("Asia/Tokyo")).date().isoformat()


def _check_live_games(con) -> None:
    # Do not transfer a hand across the period boundary. All poker hand
    # settlements are official points, including re-entry/Sit&Go payouts.
    for row in con.execute("SELECT state_json FROM tables").fetchall():
        raw = row["state_json"]
        state = json.loads(raw) if isinstance(raw, str) else (raw or {})
        if state.get("status") == "playing":
            raise HTTPException(409, "進行中のRingハンドがあるため切り替えできません")
    busy = con.execute(
        "SELECT id FROM sitngo_events "
        "WHERE status IN ('registration_open','starting','running') LIMIT 1"
    ).fetchone()
    if busy:
        raise HTTPException(409, "進行中・受付中のSit&Goがあるため切り替えできません")


def install(app, db, server, admin_console) -> None:
    if getattr(app.state, "jj_season_rollover_installed", False):
        return
    app.state.jj_season_rollover_installed = True

    @app.get("/api/season/current")
    def current_season(user=Depends(server.current_user)):
        return season_management.active_season(db)

    @app.post("/api/admin/console/seasons/{season_id}/activate")
    def activate(season_id: str, payload: ActivateIn, user=Depends(server.admin_user)):
        actor_id = int(user["id"])
        admin_role_delegation._check_pin_limit(actor_id)
        with db.connect() as con:
            if getattr(db, "IS_POSTGRES", False):
                con.execute("SELECT pg_advisory_xact_lock(?)", (2026101002,))
            else:
                con.execute("BEGIN IMMEDIATE")

            actor = con.execute(
                "SELECT role,disabled,deleted_at,password_hash FROM users WHERE id=?",
                (actor_id,),
            ).fetchone()
            if (not actor or actor["role"] != "admin"
                    or actor["deleted_at"] or int(actor["disabled"] or 0)):
                raise HTTPException(403, "管理者権限が必要です")
            if not db.verify_password(payload.current_pin, actor["password_hash"]):
                admin_role_delegation._record_failed_pin(actor_id)
                raise HTTPException(403, "管理者PINが正しくありません")
            admin_role_delegation._clear_failed_pin(actor_id)

            current = season_management.active_season(db, con=con)
            if current["season_id"] != payload.expected_current_season_id:
                raise HTTPException(409, "現在のシーズンが変更されています。管理画面を更新してください")
            target = con.execute(
                "SELECT * FROM jj_seasons WHERE season_id=?", (season_id,)
            ).fetchone()
            if not target or target["status"] != "draft":
                raise HTTPException(409, "準備中のシーズンのみ開始できます")
            if current["end_exclusive"] != target["start_date"]:
                raise HTTPException(409, "次期開始日は現行シーズンの終了翌日と一致させてください")
            day = today_jst()
            if not target["start_date"] <= day < target["end_exclusive"]:
                raise HTTPException(409, "次期シーズンの開始日を迎えていません")
            _check_live_games(con)
            stamp = db.utcnow()
            con.execute(
                "UPDATE jj_seasons SET status='archived',locked_bounds=1,updated_at=?,updated_by=? "
                "WHERE season_id=? AND status='active'",
                (stamp, actor_id, current["season_id"]),
            )
            con.execute(
                "UPDATE jj_seasons SET status='active',locked_bounds=1,updated_at=?,updated_by=? "
                "WHERE season_id=? AND status='draft'",
                (stamp, actor_id, season_id),
            )
            admin_console._audit(
                db, actor_id, "season.activate", con=con,
                previous_season_id=current["season_id"],
                active_season_id=season_id,
                boundary_date=target["start_date"],
            )
            next_season = con.execute(
                "SELECT * FROM jj_seasons WHERE season_id=?", (season_id,)
            ).fetchone()
        return {"ok": True, "current":dict(next_season),
                "archived_season_id":current["season_id"]}

    # The immutable v1.24.4 endpoint still uses the 2026-09 to 2027-03
    # constants. Replace the read callable (not the core source) so every
    # existing GET /api/entries consumer, including the bundled admin points
    # dashboard, reads the active season.
    def current_entries(limit: int = 40, archive: bool = False,
                        user=Depends(server.current_user)):
        limit = max(1, min(int(limit), 200))
        start, end = season_management.bounds(db, "fall")
        with db.connect() as con:
            if archive:
                rows = con.execute(
                    "SELECT * FROM entries ORDER BY date DESC LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM entries WHERE date>=? AND date<? "
                    "ORDER BY date DESC LIMIT ?", (start, end, limit)
                ).fetchall()
        return [dict(row) for row in rows]

    server.entries = current_entries
    matches = [
        route for route in app.router.routes
        if getattr(route, "path", "") == "/api/entries"
        and "GET" in (getattr(route, "methods", None) or ())
    ]
    if not matches:
        raise RuntimeError("Could not find canonical GET /api/entries route")
    for route in matches:
        route.endpoint = route.dependant.call = current_entries
