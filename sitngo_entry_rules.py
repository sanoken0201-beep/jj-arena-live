"""Late-registration and re-entry rules for root-level Sit&Go tournaments.

The existing tournament remains freezeout by default.  An administrator may
open a post-start entry window and optionally allow a bounded number of
re-entries per player.  Late entries/re-entries are queued while a hand is in
progress and are activated only between hands; the blind clock never resets.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import Field

import sitngo_admin_config

DEFAULT_LATE_REGISTRATION_MINUTES = 0
DEFAULT_MAX_REENTRIES = 0
MAX_LATE_REGISTRATION_MINUTES = 60
MAX_REENTRIES = 5
REENTRY_FINISH_GRACE_SECONDS = 30
PENDING_STATUSES = {"pending_late", "pending_reentry"}


class EntryConfiguredSitNGoCreateIn(sitngo_admin_config.ConfiguredSitNGoCreateIn):
    late_registration_minutes: int = Field(
        default=DEFAULT_LATE_REGISTRATION_MINUTES,
        ge=0,
        le=MAX_LATE_REGISTRATION_MINUTES,
    )
    max_reentries: int = Field(default=DEFAULT_MAX_REENTRIES, ge=0, le=MAX_REENTRIES)


class EntryConfiguredSitNGoUpdateIn(sitngo_admin_config.ConfiguredSitNGoUpdateIn):
    late_registration_minutes: int | None = Field(
        default=None,
        ge=0,
        le=MAX_LATE_REGISTRATION_MINUTES,
    )
    max_reentries: int | None = Field(default=None, ge=0, le=MAX_REENTRIES)


def _validate_entry_config(late_minutes: Any, max_reentries: Any) -> tuple[int, int]:
    try:
        late = int(late_minutes)
        reentries = int(max_reentries)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "レイトレジ・リエントリー設定が不正です") from exc
    if not 0 <= late <= MAX_LATE_REGISTRATION_MINUTES:
        raise HTTPException(400, f"レイトレジは0〜{MAX_LATE_REGISTRATION_MINUTES}分で設定してください")
    if not 0 <= reentries <= MAX_REENTRIES:
        raise HTTPException(400, f"リエントリー回数は0〜{MAX_REENTRIES}回で設定してください")
    if reentries and late <= 0:
        raise HTTPException(400, "リエントリーを許可する場合は開始後受付時間を1分以上にしてください")
    return late, reentries


def _column_names(db, table: str) -> set[str]:
    with db.connect() as con:
        if getattr(db, "IS_POSTGRES", False):
            rows = con.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=?",
                (table,),
            ).fetchall()
            return {str(row["column_name"]) for row in rows}
        rows = con.execute(f"PRAGMA table_info({table})").fetchall()
        return {str(row["name"]) for row in rows}


def _ensure_entry_schema(service) -> None:
    event_columns = _column_names(service.db, "sitngo_events")
    reg_columns = _column_names(service.db, "sitngo_registrations")
    with service.db.connect() as con:
        if "late_registration_minutes" not in event_columns:
            con.execute("ALTER TABLE sitngo_events ADD COLUMN late_registration_minutes INTEGER NOT NULL DEFAULT 0")
        if "max_reentries" not in event_columns:
            con.execute("ALTER TABLE sitngo_events ADD COLUMN max_reentries INTEGER NOT NULL DEFAULT 0")
        if "reentry_count" not in reg_columns:
            con.execute("ALTER TABLE sitngo_registrations ADD COLUMN reentry_count INTEGER NOT NULL DEFAULT 0")


def _event_started_at(row: dict[str, Any]) -> datetime | None:
    raw = row.get("started_at")
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _entry_deadline(row: dict[str, Any]) -> datetime | None:
    started = _event_started_at(row)
    minutes = int(row.get("late_registration_minutes") or 0)
    if started is None or minutes <= 0:
        return None
    return started + timedelta(minutes=minutes)


def _entry_window_open(row: dict[str, Any], now: datetime | None = None) -> bool:
    if str(row.get("status")) != "running":
        return False
    deadline = _entry_deadline(row)
    return bool(deadline and (now or datetime.now(timezone.utc)) < deadline)


def _pending_rows(runtime, event_id: str) -> list[dict[str, Any]]:
    with runtime.db.connect() as con:
        rows = con.execute(
            "SELECT r.user_id,r.status,r.seat,r.reentry_count,u.name "
            "FROM sitngo_registrations r JOIN users u ON u.id=r.user_id "
            "WHERE r.event_id=? AND r.status IN ('pending_late','pending_reentry') "
            "ORDER BY r.registered_at,r.user_id",
            (event_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _registration_row(runtime, event_id: str, user_id: int) -> dict[str, Any] | None:
    with runtime.db.connect() as con:
        row = con.execute(
            "SELECT event_id,user_id,status,seat,reentry_count,registered_at,cancelled_at "
            "FROM sitngo_registrations WHERE event_id=? AND user_id=?",
            (event_id, user_id),
        ).fetchone()
    return dict(row) if row else None


def _activate_pending(runtime, state: dict[str, Any]) -> bool:
    """Seat queued entrants between hands and preserve the tournament clock."""
    if state.get("status") == "playing":
        return False
    event_id = str(state["id"])
    pending = _pending_rows(runtime, event_id)
    if not pending:
        return False
    tournament = state["tournament"]
    stack = int(tournament.get("starting_stack") or state.get("min_buyin") or 0)
    if stack <= 0:
        raise RuntimeError("Sit&Go starting stack missing for queued entry")
    changed = False
    with runtime.db.connect() as con:
        for row in pending:
            uid = int(row["user_id"])
            status = str(row["status"])
            if status == "pending_reentry":
                player = next((p for p in state["seats"] if int(p["user_id"]) == uid), None)
                if player is None or int(player.get("stack") or 0) != 0 or player.get("in_hand"):
                    continue
                seat = int(player["seat"])
                runtime.engine.remove_player(state, uid)
                runtime.engine.seat_player(state, user_id=uid, name=row["name"], seat=seat, stack=stack)
                tournament["results"] = [x for x in tournament.get("results", []) if int(x["user_id"]) != uid]
                tournament["total_chips"] = int(tournament["total_chips"]) + stack
                tournament["total_entries"] = int(tournament.get("total_entries") or tournament.get("entrants") or 0) + 1
                tournament.setdefault("entry_history", []).append(
                    {"user_id": uid, "kind": "reentry", "hand_no": int(state.get("hand_no") or 0) + 1, "stack": stack}
                )
                con.execute(
                    "UPDATE sitngo_registrations SET status='active',seat=?,reentry_count=reentry_count+1,cancelled_at=NULL "
                    "WHERE event_id=? AND user_id=? AND status='pending_reentry'",
                    (seat, event_id, uid),
                )
                changed = True
            elif status == "pending_late":
                used = {int(p["seat"]) for p in state["seats"]}
                seat = next((value for value in range(int(state.get("max_seats") or 6)) if value not in used), None)
                if seat is None:
                    continue
                runtime.engine.seat_player(state, user_id=uid, name=row["name"], seat=seat, stack=stack)
                tournament["entrants"] = int(tournament.get("entrants") or 0) + 1
                tournament["total_entries"] = int(tournament.get("total_entries") or tournament["entrants"] - 1) + 1
                tournament["total_chips"] = int(tournament["total_chips"]) + stack
                tournament.setdefault("entry_history", []).append(
                    {"user_id": uid, "kind": "late", "hand_no": int(state.get("hand_no") or 0) + 1, "stack": stack}
                )
                con.execute(
                    "UPDATE sitngo_registrations SET status='active',seat=?,cancelled_at=NULL "
                    "WHERE event_id=? AND user_id=? AND status='pending_late'",
                    (seat, event_id, uid),
                )
                changed = True
    if changed:
        tournament.pop("reentry_grace_until_epoch", None)
        tournament.pop("finish_grace_hand_id", None)
        state["session_active"] = True
        state["next_hand_at_epoch"] = max(time.time() + 0.2, float(state.get("showdown_hold_until_epoch") or 0))
    return changed


def install(sitngo_module, sitngo_runtime) -> None:
    if getattr(sitngo_module, "_JJ_ENTRY_RULES_INSTALLED", False):
        return

    # The admin-structure layer is installed first, so extending its Pydantic
    # models preserves stack/structure fields while adding entry policy fields.
    sitngo_module.SitNGoCreateIn = EntryConfiguredSitNGoCreateIn
    sitngo_module.SitNGoUpdateIn = EntryConfiguredSitNGoUpdateIn

    service_cls = sitngo_module.SitNGoService
    runtime_cls = sitngo_runtime.TournamentRuntime
    original_ensure = service_cls._ensure_schema
    original_regs = service_cls._registrations
    original_payload = service_cls._event_payload
    original_create = service_cls.create_event
    original_update = service_cls.update_event
    original_register = service_cls.register
    original_runtime_create = runtime_cls.create
    original_finish = runtime_cls.finish
    original_tick = runtime_cls.tick
    original_public = runtime_cls.public
    original_dispatch = runtime_cls.install_dispatch
    original_install = sitngo_module.install

    def ensure_schema(self):
        original_ensure(self)
        _ensure_entry_schema(self)

    def registrations(self, event_id: str, *, include_cancelled: bool = False):
        values = original_regs(self, event_id, include_cancelled=include_cancelled)
        with self.db.connect() as con:
            rows = con.execute(
                "SELECT user_id,reentry_count FROM sitngo_registrations WHERE event_id=?",
                (event_id,),
            ).fetchall()
        counts = {int(row["user_id"]): int(row["reentry_count"] or 0) for row in rows}
        for value in values:
            value["reentry_count"] = counts.get(int(value["user_id"]), 0)
        return values

    def event_payload(self, row, user_id=None, *, admin=False):
        row = dict(row)
        payload = original_payload(self, row, user_id, admin=admin)
        late = int(row.get("late_registration_minutes") or 0)
        reentries = int(row.get("max_reentries") or 0)
        deadline = _entry_deadline(row)
        now = sitngo_module._utcnow()
        regs = self._registrations(str(row["id"]), include_cancelled=True)
        mine = next((r for r in regs if user_id is not None and int(r["user_id"]) == int(user_id)), None)
        unique_entries = sum(1 for r in regs if r["status"] != "cancelled")
        open_now = _entry_window_open(row, now)
        can_late = bool(open_now and unique_entries < int(row.get("max_players") or sitngo_module.MAX_PLAYERS) and (mine is None or mine["status"] == "cancelled"))
        can_reenter = bool(
            open_now
            and reentries > 0
            and mine is not None
            and mine["status"] == "finished"
            and int(mine.get("reentry_count") or 0) < reentries
        )
        payload.update(
            late_registration_minutes=late,
            max_reentries=reentries,
            late_registration_deadline=deadline.isoformat() if deadline else None,
            late_registration_open=open_now,
            can_late_register=can_late,
            can_reenter=can_reenter,
            entry_pending=bool(mine and mine["status"] in PENDING_STATUSES),
            reentry_count=int(mine.get("reentry_count") or 0) if mine else 0,
            reentry=bool(reentries),
        )
        return payload

    def create_event(self, payload: EntryConfiguredSitNGoCreateIn, actor_id: int):
        late, reentries = _validate_entry_config(payload.late_registration_minutes, payload.max_reentries)
        result = original_create(self, payload, actor_id)
        with self.db.connect() as con:
            con.execute(
                "UPDATE sitngo_events SET late_registration_minutes=?,max_reentries=?,updated_at=? WHERE id=?",
                (late, reentries, self.db.utcnow(), result["id"]),
            )
        self._audit(actor_id, "sitngo.entry_config", event_id=result["id"], late_registration_minutes=late, max_reentries=reentries)
        return self._event_payload(self._row(result["id"]), actor_id, admin=True)

    def update_event(self, event_id: str, payload: EntryConfiguredSitNGoUpdateIn, actor_id: int):
        current = self._row(event_id)
        late = int(current.get("late_registration_minutes") or 0) if payload.late_registration_minutes is None else payload.late_registration_minutes
        reentries = int(current.get("max_reentries") or 0) if payload.max_reentries is None else payload.max_reentries
        late, reentries = _validate_entry_config(late, reentries)
        result = original_update(self, event_id, payload, actor_id)
        if payload.late_registration_minutes is not None or payload.max_reentries is not None:
            with self.db.connect() as con:
                con.execute(
                    "UPDATE sitngo_events SET late_registration_minutes=?,max_reentries=?,updated_at=? WHERE id=?",
                    (late, reentries, self.db.utcnow(), event_id),
                )
            self._audit(actor_id, "sitngo.entry_config", event_id=event_id, late_registration_minutes=late, max_reentries=reentries)
        return self._event_payload(self._row(event_id), actor_id, admin=True)

    def register(self, event_id: str, user_id: int):
        self.reconcile()
        event = self._row(event_id)
        if str(event["status"]) != "running":
            return original_register(self, event_id, user_id)
        if hasattr(self, "runtime") and self.runtime.ring_seated(user_id):
            raise HTTPException(409, "リングの席を離れてから大会に参加してください")
        now = sitngo_module._utcnow()
        if not _entry_window_open(event, now):
            raise HTTPException(400, "途中参加の受付は終了しています")
        with self._lock, self.db.connect() as con:
            existing = con.execute(
                "SELECT status FROM sitngo_registrations WHERE event_id=? AND user_id=?",
                (event_id, user_id),
            ).fetchone()
            if existing and existing["status"] != "cancelled":
                if existing["status"] == "finished":
                    raise HTTPException(409, "このプレイヤーは途中参加ではなくリエントリーを使用してください")
                raise HTTPException(409, "すでにこの大会に参加しています")
            unique_count = con.execute(
                "SELECT COUNT(*) n FROM sitngo_registrations WHERE event_id=? AND status<>'cancelled'",
                (event_id,),
            ).fetchone()
            if int(unique_count["n"] or 0) >= int(event.get("max_players") or sitngo_module.MAX_PLAYERS):
                raise HTTPException(409, "6人の参加枠がすでに使用されています")
            stamp = sitngo_module._iso(now)
            if existing:
                con.execute(
                    "UPDATE sitngo_registrations SET status='pending_late',registered_at=?,cancelled_at=NULL,seat=NULL,reentry_count=0 WHERE event_id=? AND user_id=?",
                    (stamp, event_id, user_id),
                )
            else:
                con.execute(
                    "INSERT INTO sitngo_registrations(event_id,user_id,status,registered_at,cancelled_at,seat,reentry_count) VALUES (?,?, 'pending_late', ?, NULL, NULL, 0)",
                    (event_id, user_id, stamp),
                )
        self.runtime.signal()
        return self._event_payload(self._row(event_id), user_id)

    def reenter(self, event_id: str, user_id: int):
        self.reconcile()
        event = self._row(event_id)
        now = sitngo_module._utcnow()
        if not _entry_window_open(event, now):
            raise HTTPException(400, "リエントリー受付は終了しています")
        maximum = int(event.get("max_reentries") or 0)
        if maximum <= 0:
            raise HTTPException(400, "この大会はリエントリー不可です")
        with self._lock, self.db.connect() as con:
            reg = con.execute(
                "SELECT status,reentry_count FROM sitngo_registrations WHERE event_id=? AND user_id=?",
                (event_id, user_id),
            ).fetchone()
            if not reg:
                raise HTTPException(400, "リエントリーには一度参加している必要があります")
            if reg["status"] != "finished":
                if reg["status"] == "pending_reentry":
                    raise HTTPException(409, "リエントリー処理中です")
                raise HTTPException(409, "敗退後にのみリエントリーできます")
            if int(reg["reentry_count"] or 0) >= maximum:
                raise HTTPException(409, "リエントリー上限に達しています")
            state = self.runtime.load(event_id)
            player = next((p for p in state["seats"] if int(p["user_id"]) == int(user_id)), None)
            if player is None or int(player.get("stack") or 0) != 0:
                raise HTTPException(409, "敗退状態を確認できません")
            con.execute(
                "UPDATE sitngo_registrations SET status='pending_reentry',registered_at=?,cancelled_at=NULL WHERE event_id=? AND user_id=?",
                (sitngo_module._iso(now), event_id, user_id),
            )
        self.runtime.signal()
        return self._event_payload(self._row(event_id), user_id)

    def runtime_create(self, con, event, participants, now):
        original_runtime_create(self, con, event, participants, now)
        row = con.execute("SELECT state_json FROM sitngo_games WHERE event_id=?", (event["id"],)).fetchone()
        if not row:
            return
        state = json.loads(row["state_json"])
        t = state["tournament"]
        late = int(event.get("late_registration_minutes") or 0)
        t.update(
            starting_stack=int(event["starting_stack"]),
            late_registration_minutes=late,
            max_reentries=int(event.get("max_reentries") or 0),
            entry_window_deadline_epoch=now.timestamp() + late * 60 if late else now.timestamp(),
            total_entries=len(participants),
            entry_history=[{"user_id": int(uid), "kind": "initial", "hand_no": 1, "stack": int(event["starting_stack"])} for uid, _ in participants],
        )
        con.execute(
            "UPDATE sitngo_games SET state_json=?,updated_at=? WHERE event_id=?",
            (json.dumps(state, ensure_ascii=False), self.db.utcnow(), event["id"]),
        )

    def finish(self, state):
        before_results = {int(x["user_id"]) for x in state.get("tournament", {}).get("results", [])}
        original_finish(self, state)
        t = state.get("tournament") or {}
        if not t or t.get("status") != "finished":
            return
        now = time.time()
        deadline = float(t.get("entry_window_deadline_epoch") or 0)
        if now >= deadline:
            return
        current_hand = (state.get("hand") or {}).get("id")
        if t.get("finish_grace_hand_id") == current_hand:
            return
        pending = _pending_rows(self, str(state["id"]))
        newly_busted = [x for x in t.get("results", []) if int(x["user_id"]) not in before_results and int(x.get("place") or 0) > 1]
        eligible = False
        maximum = int(t.get("max_reentries") or 0)
        if maximum > 0:
            for result in newly_busted:
                reg = _registration_row(self, str(state["id"]), int(result["user_id"]))
                if reg and int(reg.get("reentry_count") or 0) < maximum:
                    eligible = True
                    break
        if not pending and not eligible:
            return
        t["results"] = [x for x in t.get("results", []) if int(x.get("place") or 0) != 1]
        t["status"] = "running"
        t.pop("finished_at", None)
        t["finish_grace_hand_id"] = current_hand
        grace = min(deadline, now + REENTRY_FINISH_GRACE_SECONDS) if eligible and not pending else now
        t["reentry_grace_until_epoch"] = grace
        state["session_active"] = False
        state["next_hand_at_epoch"] = grace

    async def tick(self, eid, *, now=None, recover=False):
        now = time.time() if now is None else now
        state = self.load(eid)
        t = state.get("tournament") or {}
        if t.get("status") == "running" and state.get("status") == "waiting":
            pending = _pending_rows(self, eid)
            if pending:
                async with self.server.get_table_lock(eid):
                    state = self.load(eid)
                    if _activate_pending(self, state):
                        self.save(state, notify=False)
                await self.server.hub.broadcast(eid)
                return min(float(state.get("next_hand_at_epoch") or now + 0.2), now + 0.2)
            grace = float(t.get("reentry_grace_until_epoch") or 0)
            if grace:
                if now < grace:
                    return grace
                async with self.server.get_table_lock(eid):
                    state = self.load(eid)
                    t = state["tournament"]
                    if _pending_rows(self, eid):
                        if _activate_pending(self, state):
                            self.save(state, notify=False)
                        await self.server.hub.broadcast(eid)
                        return now + 0.2
                    alive = [p for p in state["seats"] if int(p.get("stack") or 0) > 0]
                    if len(alive) == 1:
                        winner = alive[0]
                        if not any(int(x.get("place") or 0) == 1 for x in t.get("results", [])):
                            t["results"].append({
                                "user_id": winner["user_id"],
                                "name": winner["name"],
                                "place": 1,
                                "hand_no": state.get("hand_no", 0),
                                "starting_stack": winner["stack"],
                                "prize_points": 0,
                            })
                        t["status"] = "finished"
                        t["finished_at"] = self.db.utcnow()
                        t.pop("reentry_grace_until_epoch", None)
                        state["session_active"] = False
                        state["next_hand_at_epoch"] = None
                        self.save(state, notify=False)
                    else:
                        t.pop("reentry_grace_until_epoch", None)
                        state["session_active"] = True
                        state["next_hand_at_epoch"] = now + 0.2
                        self.save(state, notify=False)
                await self.server.hub.broadcast(eid)
                return None if len(alive) == 1 else now + 0.2
        return await original_tick(self, eid, now=now, recover=recover)

    def public(self, state, viewer=None):
        value = original_public(self, state, viewer)
        t = value.get("tournament") or {}
        deadline = float(t.get("entry_window_deadline_epoch") or 0)
        t["late_registration_open"] = bool(t.get("status") == "running" and deadline > time.time())
        t["entry_window_deadline"] = datetime.fromtimestamp(deadline, timezone.utc).isoformat() if deadline else None
        return value

    def install_dispatch(self, ring):
        original_dispatch(self, ring)
        previous = self.server.seated_table_for_user

        def membership(uid, exclude=None):
            value = previous(uid, exclude=exclude)
            if value:
                return value
            with self.db.connect() as con:
                row = con.execute(
                    "SELECT r.event_id FROM sitngo_registrations r JOIN sitngo_events e ON e.id=r.event_id "
                    "WHERE r.user_id=? AND r.status IN ('pending_late','pending_reentry') AND e.status='running' AND e.id<>? LIMIT 1",
                    (uid, exclude or ""),
                ).fetchone()
            return row["event_id"] if row else None

        self.server.seated_table_for_user = membership

    def install_app(app, db, server):
        service = original_install(app, db, server)
        if not getattr(app.state, "jj_sitngo_reentry_route", False):
            @app.post("/api/sitngo/{event_id}/reentry")
            async def sitngo_reentry(event_id: str, user=Depends(server.current_user)):
                async with server.table_membership_lock:
                    return service.reenter(event_id, int(user["id"]))
            app.state.jj_sitngo_reentry_route = True
        return service

    service_cls._ensure_schema = ensure_schema
    service_cls._registrations = registrations
    service_cls._event_payload = event_payload
    service_cls.create_event = create_event
    service_cls.update_event = update_event
    service_cls.register = register
    service_cls.reenter = reenter
    runtime_cls.create = runtime_create
    runtime_cls.finish = finish
    runtime_cls.tick = tick
    runtime_cls.public = public
    runtime_cls.install_dispatch = install_dispatch
    sitngo_module.install = install_app
    sitngo_module._JJ_ENTRY_RULES_INSTALLED = True


__all__ = [
    "DEFAULT_LATE_REGISTRATION_MINUTES",
    "DEFAULT_MAX_REENTRIES",
    "EntryConfiguredSitNGoCreateIn",
    "EntryConfiguredSitNGoUpdateIn",
    "MAX_LATE_REGISTRATION_MINUTES",
    "MAX_REENTRIES",
    "REENTRY_FINISH_GRACE_SECONDS",
    "install",
]
