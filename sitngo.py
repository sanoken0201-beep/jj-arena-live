from __future__ import annotations

import asyncio
import json
import secrets
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

JST = ZoneInfo("Asia/Tokyo")
MAX_PLAYERS = 6
MIN_PLAYERS = 2
STARTING_STACK = 10_000
LEVEL_MINUTES = 10
TARGET_MINUTES = 90
PREPARED_MINUTES = 150

BLIND_STRUCTURE = [
    {"level": 1, "small_blind": 100, "big_blind": 200, "bb_ante": 200, "minutes": 10},
    {"level": 2, "small_blind": 200, "big_blind": 400, "bb_ante": 400, "minutes": 10},
    {"level": 3, "small_blind": 300, "big_blind": 600, "bb_ante": 600, "minutes": 10},
    {"level": 4, "small_blind": 400, "big_blind": 800, "bb_ante": 800, "minutes": 10},
    {"level": 5, "small_blind": 500, "big_blind": 1_000, "bb_ante": 1_000, "minutes": 10},
    {"level": 6, "small_blind": 700, "big_blind": 1_400, "bb_ante": 1_400, "minutes": 10},
    {"level": 7, "small_blind": 1_000, "big_blind": 2_000, "bb_ante": 2_000, "minutes": 10},
    {"level": 8, "small_blind": 1_500, "big_blind": 3_000, "bb_ante": 3_000, "minutes": 10},
    {"level": 9, "small_blind": 2_000, "big_blind": 4_000, "bb_ante": 4_000, "minutes": 10},
    {"level": 10, "small_blind": 3_000, "big_blind": 6_000, "bb_ante": 6_000, "minutes": 10},
    {"level": 11, "small_blind": 4_000, "big_blind": 8_000, "bb_ante": 8_000, "minutes": 10},
    {"level": 12, "small_blind": 6_000, "big_blind": 12_000, "bb_ante": 12_000, "minutes": 10},
    {"level": 13, "small_blind": 8_000, "big_blind": 16_000, "bb_ante": 16_000, "minutes": 10},
    {"level": 14, "small_blind": 10_000, "big_blind": 20_000, "bb_ante": 20_000, "minutes": 10},
    {"level": 15, "small_blind": 15_000, "big_blind": 30_000, "bb_ante": 30_000, "minutes": 10},
]


class SitNGoCreateIn(BaseModel):
    name: str = Field(default="JJ Sit&Go", min_length=1, max_length=80)
    starts_at: str = Field(min_length=10, max_length=50)


class SitNGoUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    starts_at: str | None = Field(default=None, min_length=10, max_length=50)


class SitNGoCancelIn(BaseModel):
    reason: str = Field(default="運営により中止", max_length=300)


def _parse_aware(value: str) -> datetime:
    raw = str(value or "").strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise HTTPException(400, "開催日時の形式が不正です") from exc
    if dt.tzinfo is None:
        raise HTTPException(400, "開催日時にはタイムゾーンが必要です")
    return dt.astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _registration_open_for(starts_at: datetime) -> datetime:
    """Open at most 60 minutes before the event, never before that JST date."""
    local_start = starts_at.astimezone(JST)
    local_midnight = local_start.replace(hour=0, minute=0, second=0, microsecond=0)
    return max(starts_at - timedelta(hours=1), local_midnight.astimezone(timezone.utc))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SitNGoService:
    def __init__(self, app, db, server):
        self.app = app
        self.db = db
        self.server = server
        self._lock = threading.RLock()
        self._ensure_schema()
        from sitngo_points import TournamentPoints
        self.points = TournamentPoints(self)

    def _ensure_schema(self) -> None:
        uid = "BIGINT" if getattr(self.db, "IS_POSTGRES", False) else "INTEGER"
        with self.db.connect() as con:
            con.execute(
                f"""CREATE TABLE IF NOT EXISTS sitngo_events(
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    starts_at TEXT NOT NULL,
                    registration_opens_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    max_players INTEGER NOT NULL DEFAULT 6,
                    min_players INTEGER NOT NULL DEFAULT 2,
                    starting_stack INTEGER NOT NULL DEFAULT 10000,
                    level_minutes INTEGER NOT NULL DEFAULT 10,
                    target_minutes INTEGER NOT NULL DEFAULT 90,
                    prepared_minutes INTEGER NOT NULL DEFAULT 150,
                    structure_json TEXT NOT NULL,
                    created_by {uid},
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    cancelled_at TEXT,
                    cancel_reason TEXT NOT NULL DEFAULT ''
                )"""
            )
            con.execute(
                f"""CREATE TABLE IF NOT EXISTS sitngo_registrations(
                    event_id TEXT NOT NULL REFERENCES sitngo_events(id) ON DELETE CASCADE,
                    user_id {uid} NOT NULL REFERENCES users(id),
                    status TEXT NOT NULL,
                    registered_at TEXT NOT NULL,
                    cancelled_at TEXT,
                    seat INTEGER,
                    PRIMARY KEY(event_id,user_id)
                )"""
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_sitngo_events_starts ON sitngo_events(starts_at,status)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_sitngo_reg_status ON sitngo_registrations(event_id,status,registered_at)")

    def _audit(self, actor_id: int, action: str, **detail) -> None:
        try:
            with self.db.connect() as con:
                con.execute(
                    "INSERT INTO admin_audit_log(actor_id,action,target_user_id,detail_json,created_at) VALUES (?,?,?,?,?)",
                    (actor_id, action, None, json.dumps(detail, ensure_ascii=False, separators=(",", ":")), self.db.utcnow()),
                )
        except Exception:
            # Audit logging must not make tournament scheduling unavailable if an
            # older rollback database has not installed the admin table yet.
            pass

    def _row(self, event_id: str):
        with self.db.connect() as con:
            row = con.execute("SELECT * FROM sitngo_events WHERE id=?", (event_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Sit&Goが見つかりません")
        return dict(row)

    def _registrations(self, event_id: str, *, include_cancelled: bool = False) -> list[dict]:
        where = "event_id=?" if include_cancelled else "event_id=? AND status<>'cancelled'"
        with self.db.connect() as con:
            rows = con.execute(
                f"""SELECT r.event_id,r.user_id,r.status,r.registered_at,r.cancelled_at,r.seat,u.name
                    FROM sitngo_registrations r JOIN users u ON u.id=r.user_id
                    WHERE {where}
                    ORDER BY r.registered_at ASC,r.user_id ASC""",
                (event_id,),
            ).fetchall()
        out = [dict(row) for row in rows]
        order = 0
        for item in out:
            if item["status"] != "cancelled":
                order += 1
                item["registration_order"] = order
            else:
                item["registration_order"] = None
        return out

    def reconcile(self, now: datetime | None = None) -> list[str]:
        now = (now or _utcnow()).astimezone(timezone.utc)
        changed: list[str] = []
        with self._lock:
            with self.db.connect() as con:
                con.execute("UPDATE sitngo_events SET updated_at=updated_at WHERE status IN ('scheduled','registration_open','starting')")
                rows = con.execute(
                    "SELECT * FROM sitngo_events WHERE status IN ('scheduled','registration_open','starting') ORDER BY starts_at,id"
                ).fetchall()
                for raw in rows:
                    event = dict(raw)
                    event_id = str(event["id"])
                    starts = _parse_aware(str(event["starts_at"]))
                    opens = _parse_aware(str(event["registration_opens_at"]))
                    status = str(event["status"])
                    if now >= starts:
                        regs = con.execute(
                            "SELECT user_id,registered_at FROM sitngo_registrations WHERE event_id=? AND status='registered' ORDER BY registered_at,user_id",
                            (event_id,),
                        ).fetchall()
                        minimum = int(event.get("min_players") or MIN_PLAYERS)
                        if len(regs) >= minimum:
                            participants = [int(row["user_id"]) for row in regs]
                            rng = secrets.SystemRandom()
                            rng.shuffle(participants)
                            seats = rng.sample(range(int(event.get("max_players") or MAX_PLAYERS)), len(participants))
                            if hasattr(self, 'runtime'):
                                busy = con.execute("SELECT id FROM sitngo_events WHERE status='running' AND id<>? LIMIT 1", (event_id,)).fetchone()
                                if busy:
                                    if status != "starting":
                                        stamp = _iso(now)
                                        con.execute(
                                            "UPDATE sitngo_events SET status='starting',updated_at=? WHERE id=?",
                                            (stamp, event_id),
                                        )
                                        changed.append(event_id)
                                    continue
                                self.runtime.create(con, event, list(zip(participants, seats)), now)
                            for user_id, seat in zip(participants, seats):
                                con.execute(
                                    "UPDATE sitngo_registrations SET status='active',seat=?,cancelled_at=NULL WHERE event_id=? AND user_id=? AND status='registered'",
                                    (seat, event_id, user_id),
                                )
                            stamp = _iso(now)
                            con.execute(
                                "UPDATE sitngo_events SET status='running',started_at=?,updated_at=?,cancel_reason='' WHERE id=?",
                                (stamp, stamp, event_id),
                            )
                        else:
                            self.points.refund(con, event_id)
                            stamp = _iso(now)
                            con.execute(
                                "UPDATE sitngo_events SET status='cancelled',cancelled_at=?,updated_at=?,cancel_reason=? WHERE id=?",
                                (stamp, stamp, "minimum_players_not_met", event_id),
                            )
                            con.execute(
                                "UPDATE sitngo_registrations SET status='cancelled',cancelled_at=? WHERE event_id=? AND status='registered'",
                                (stamp, event_id),
                            )
                        changed.append(event_id)
                    elif now >= opens and status == "scheduled":
                        stamp = _iso(now)
                        con.execute(
                            "UPDATE sitngo_events SET status='registration_open',updated_at=? WHERE id=?",
                            (stamp, event_id),
                        )
                        changed.append(event_id)
        return changed

    def _event_payload(self, row: dict, user_id: int | None = None, *, admin: bool = False) -> dict:
        regs = self._registrations(str(row["id"]), include_cancelled=admin)
        active_regs = [r for r in regs if r["status"] != "cancelled"]
        mine = next((r for r in active_regs if user_id is not None and int(r["user_id"]) == int(user_id)), None)
        now = _utcnow()
        starts = _parse_aware(str(row["starts_at"]))
        opens = _parse_aware(str(row["registration_opens_at"]))
        status = str(row["status"])
        full = len(active_regs) >= int(row.get("max_players") or MAX_PLAYERS)
        before_start = now < starts
        registration_window = opens <= now < starts and status in {"registration_open", "scheduled"}
        payload = {
            "id": str(row["id"]),
            "name": str(row["name"]),
            "starts_at": str(row["starts_at"]),
            "registration_opens_at": str(row["registration_opens_at"]),
            "status": status,
            "max_players": int(row.get("max_players") or MAX_PLAYERS),
            "min_players": int(row.get("min_players") or MIN_PLAYERS),
            "starting_stack": int(row.get("starting_stack") or STARTING_STACK),
            "level_minutes": int(row.get("level_minutes") or LEVEL_MINUTES),
            "target_minutes": int(row.get("target_minutes") or TARGET_MINUTES),
            "prepared_minutes": int(row.get("prepared_minutes") or PREPARED_MINUTES),
            "participant_count": len(active_regs),
            "full": full,
            "is_registered": mine is not None,
            "registration_order": mine.get("registration_order") if mine else None,
            "seat": mine.get("seat") if mine else None,
            "can_register": bool(registration_window and not full and mine is None),
            "can_cancel_registration": bool(before_start and mine is not None and mine.get("status") == "registered"),
            "started_at": row.get("started_at"),
            "cancelled_at": row.get("cancelled_at"),
            "cancel_reason": row.get("cancel_reason") or "",
            "structure": BLIND_STRUCTURE,
            "bb_ante": True,
        }
        if hasattr(self, 'runtime') and status in {'running', 'finished'}:
            try:
                game = self.runtime.public(self.runtime.load(str(row['id'])), user_id)
                payload.update(table_id=row['id'], tournament=game['tournament'])
            except HTTPException:
                payload['table_id'] = None
        payload.update(self.points.describe(str(row["id"]), len(active_regs)))
        if status in {'running', 'finished'} or admin:
            payload["participants"] = [
                {
                    "user_id": int(r["user_id"]),
                    "name": r["name"],
                    "status": r["status"],
                    "seat": r.get("seat"),
                    "registered_at": r["registered_at"],
                    "registration_order": r.get("registration_order"),
                }
                for r in regs
            ]
        return payload

    def next_event(self, user_id: int) -> dict:
        self.reconcile()
        now = _iso(_utcnow())
        with self.db.connect() as con:
            row = con.execute(
                """SELECT e.* FROM sitngo_events e
                   LEFT JOIN sitngo_registrations r
                     ON r.event_id=e.id AND r.user_id=? AND r.status<>'cancelled'
                   WHERE e.status IN ('scheduled','registration_open','starting','running')
                   ORDER BY CASE
                     WHEN r.user_id IS NOT NULL AND e.status='running' THEN 0
                     WHEN r.user_id IS NOT NULL AND e.status='starting' THEN 1
                     WHEN e.status='running' THEN 2
                     WHEN r.user_id IS NOT NULL THEN 3
                     ELSE 4
                   END,e.starts_at ASC,e.id ASC LIMIT 1""",
                (user_id,),
            ).fetchone()
            if not row:
                row = con.execute(
                    "SELECT * FROM sitngo_events WHERE starts_at>=? AND status<>'cancelled' ORDER BY starts_at,id LIMIT 1",
                    (now,),
                ).fetchone()
        with self.db.connect() as con:
            recent = con.execute("SELECT * FROM sitngo_events WHERE status='finished' ORDER BY updated_at DESC LIMIT 5").fetchall()
        return {"event": self._event_payload(dict(row), user_id) if row else None, "structure": BLIND_STRUCTURE,
                "recent": [self._event_payload(dict(r), user_id) for r in recent]}

    def admin_events(self, actor_id: int) -> dict:
        self.reconcile()
        with self.db.connect() as con:
            rows = con.execute("SELECT * FROM sitngo_events ORDER BY starts_at DESC,id DESC LIMIT 100").fetchall()
        return {
            "events": [self._event_payload(dict(row), actor_id, admin=True) for row in rows],
            "defaults": {
                "max_players": MAX_PLAYERS,
                "min_players": MIN_PLAYERS,
                "starting_stack": STARTING_STACK,
                "level_minutes": LEVEL_MINUTES,
                "target_minutes": TARGET_MINUTES,
                "prepared_minutes": PREPARED_MINUTES,
                "bb_ante": True,
                "structure": BLIND_STRUCTURE,
            },
        }

    def create_event(self, payload: SitNGoCreateIn, actor_id: int) -> dict:
        starts = _parse_aware(payload.starts_at)
        if starts <= _utcnow() + timedelta(minutes=1):
            raise HTTPException(400, "開催日時は現在より1分以上先に設定してください")
        event_id = "sng-" + uuid.uuid4().hex
        opens = _registration_open_for(starts)
        stamp = self.db.utcnow()
        with self._lock, self.db.connect() as con:
            con.execute(
                """INSERT INTO sitngo_events(
                    id,name,starts_at,registration_opens_at,status,max_players,min_players,
                    starting_stack,level_minutes,target_minutes,prepared_minutes,structure_json,
                    created_by,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    event_id,
                    payload.name.strip() or "JJ Sit&Go",
                    _iso(starts),
                    _iso(opens),
                    "scheduled",
                    MAX_PLAYERS,
                    MIN_PLAYERS,
                    STARTING_STACK,
                    LEVEL_MINUTES,
                    TARGET_MINUTES,
                    PREPARED_MINUTES,
                    json.dumps(BLIND_STRUCTURE, ensure_ascii=False, separators=(",", ":")),
                    actor_id,
                    stamp,
                    stamp,
                ),
            )
        self._audit(actor_id, "sitngo.create", event_id=event_id, starts_at=_iso(starts), name=payload.name.strip())
        return self._event_payload(self._row(event_id), actor_id, admin=True)

    def update_event(self, event_id: str, payload: SitNGoUpdateIn, actor_id: int) -> dict:
        self.reconcile()
        with self._lock, self.db.connect() as con:
            con.execute("UPDATE sitngo_events SET updated_at=updated_at WHERE id=?", (event_id,))
            row = con.execute("SELECT * FROM sitngo_events WHERE id=?", (event_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Sit&Goが見つかりません")
            event = dict(row)
            if event["status"] not in {"scheduled", "registration_open"}:
                raise HTTPException(400, "受付前または受付中の大会だけ変更できます")
            sets: list[str] = []
            args: list[object] = []
            changed: dict[str, object] = {}
            if payload.name is not None:
                name = payload.name.strip()
                if not name:
                    raise HTTPException(400, "大会名を入力してください")
                sets.append("name=?")
                args.append(name)
                changed["name"] = name
            if payload.starts_at is not None:
                starts = _parse_aware(payload.starts_at)
                if starts <= _utcnow() + timedelta(minutes=1):
                    raise HTTPException(400, "開催日時は現在より1分以上先に設定してください")
                opens = _registration_open_for(starts)
                status = "registration_open" if _utcnow() >= opens else "scheduled"
                sets.extend(["starts_at=?", "registration_opens_at=?", "status=?"])
                args.extend([_iso(starts), _iso(opens), status])
                changed["starts_at"] = _iso(starts)
            if sets:
                sets.append("updated_at=?")
                args.append(self.db.utcnow())
                args.append(event_id)
                con.execute(f"UPDATE sitngo_events SET {','.join(sets)} WHERE id=?", args)
        if changed:
            self._audit(actor_id, "sitngo.update", event_id=event_id, changed=changed)
        return self._event_payload(self._row(event_id), actor_id, admin=True)

    def cancel_event(self, event_id: str, reason: str, actor_id: int) -> dict:
        self.reconcile()
        with self._lock, self.db.connect() as con:
            con.execute("UPDATE sitngo_events SET updated_at=updated_at WHERE id=?", (event_id,))
            row = con.execute("SELECT * FROM sitngo_events WHERE id=?", (event_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Sit&Goが見つかりません")
            if row["status"] in {"running", "finished"}:
                raise HTTPException(400, "開始後の大会はこの操作では中止できません")
            self.points.refund(con, event_id)
            stamp = self.db.utcnow()
            con.execute(
                "UPDATE sitngo_events SET status='cancelled',cancelled_at=?,cancel_reason=?,updated_at=? WHERE id=?",
                (stamp, (reason or "運営により中止").strip(), stamp, event_id),
            )
            con.execute(
                "UPDATE sitngo_registrations SET status='cancelled',cancelled_at=? WHERE event_id=? AND status='registered'",
                (stamp, event_id),
            )
        self._audit(actor_id, "sitngo.cancel", event_id=event_id, reason=reason)
        return self._event_payload(self._row(event_id), actor_id, admin=True)

    def delete_event(self, event_id: str, actor_id: int) -> dict:
        self.reconcile()
        with self._lock, self.db.connect() as con:
            con.execute("UPDATE sitngo_events SET updated_at=updated_at WHERE id=?", (event_id,))
            row = con.execute("SELECT status FROM sitngo_events WHERE id=?", (event_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Sit&Goが見つかりません")
            count = con.execute("SELECT COUNT(*) n FROM sitngo_registrations WHERE event_id=?", (event_id,)).fetchone()
            if int(count["n"] or 0) > 0:
                raise HTTPException(400, "参加履歴がある大会は削除せず中止してください")
            if row["status"] not in {"scheduled", "cancelled"}:
                raise HTTPException(400, "この大会は削除できません")
            con.execute("DELETE FROM sitngo_payout_settings WHERE event_id=?", (event_id,))
            con.execute("DELETE FROM sitngo_terms WHERE event_id=?", (event_id,))
            con.execute("DELETE FROM sitngo_events WHERE id=?", (event_id,))
        self._audit(actor_id, "sitngo.delete", event_id=event_id)
        return {"ok": True}

    def register(self, event_id: str, user_id: int) -> dict:
        if hasattr(self, "runtime") and self.runtime.ring_seated(user_id):
            raise HTTPException(409, "リングの席を離れてから大会に参加登録してください")
        self.reconcile()
        now = _utcnow()
        with self._lock, self.db.connect() as con:
            con.execute("UPDATE sitngo_events SET updated_at=updated_at WHERE id=?", (event_id,))
            event_row = con.execute("SELECT * FROM sitngo_events WHERE id=?", (event_id,)).fetchone()
            if not event_row:
                raise HTTPException(404, "Sit&Goが見つかりません")
            event = dict(event_row)
            starts = _parse_aware(str(event["starts_at"]))
            opens = _parse_aware(str(event["registration_opens_at"]))
            if not (opens <= now < starts) or event["status"] not in {"scheduled", "registration_open"}:
                raise HTTPException(400, "現在は参加受付時間ではありません")
            existing = con.execute(
                "SELECT status FROM sitngo_registrations WHERE event_id=? AND user_id=?",
                (event_id, user_id),
            ).fetchone()
            if existing and existing["status"] != "cancelled":
                raise HTTPException(409, "すでに参加登録済みです")
            count = con.execute(
                "SELECT COUNT(*) n FROM sitngo_registrations WHERE event_id=? AND status='registered'",
                (event_id,),
            ).fetchone()
            if int(count["n"] or 0) >= int(event.get("max_players") or MAX_PLAYERS):
                raise HTTPException(409, "満席です")
            self.points.charge(con, event_id, user_id)
            stamp = _iso(now)
            if existing:
                con.execute(
                    "UPDATE sitngo_registrations SET status='registered',registered_at=?,cancelled_at=NULL,seat=NULL WHERE event_id=? AND user_id=?",
                    (stamp, event_id, user_id),
                )
            else:
                con.execute(
                    "INSERT INTO sitngo_registrations(event_id,user_id,status,registered_at,cancelled_at,seat) VALUES (?,?, 'registered', ?, NULL, NULL)",
                    (event_id, user_id, stamp),
                )
            if event["status"] == "scheduled":
                con.execute("UPDATE sitngo_events SET status='registration_open',updated_at=? WHERE id=?", (stamp, event_id))
        return self._event_payload(self._row(event_id), user_id)

    def cancel_registration(self, event_id: str, user_id: int) -> dict:
        self.reconcile()
        now = _utcnow()
        with self._lock, self.db.connect() as con:
            con.execute("UPDATE sitngo_events SET updated_at=updated_at WHERE id=?", (event_id,))
            event = con.execute("SELECT * FROM sitngo_events WHERE id=?", (event_id,)).fetchone()
            if not event:
                raise HTTPException(404, "Sit&Goが見つかりません")
            starts = _parse_aware(str(event["starts_at"]))
            if now >= starts or event["status"] in {"running", "finished", "cancelled"}:
                raise HTTPException(400, "開始後は参加を取り消せません")
            reg = con.execute(
                "SELECT status FROM sitngo_registrations WHERE event_id=? AND user_id=?",
                (event_id, user_id),
            ).fetchone()
            if not reg or reg["status"] != "registered":
                raise HTTPException(400, "参加登録されていません")
            self.points.refund(con, event_id, user_id)
            stamp = _iso(now)
            con.execute(
                "UPDATE sitngo_registrations SET status='cancelled',cancelled_at=?,seat=NULL WHERE event_id=? AND user_id=?",
                (stamp, event_id, user_id),
            )
        return self._event_payload(self._row(event_id), user_id)

    async def lifecycle_loop(self) -> None:
        if hasattr(self, "runtime"):
            return await self.runtime.run()
        while True:
            try:
                await asyncio.to_thread(self.reconcile)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"JJ_SITNGO_RECONCILE_ERROR {type(exc).__name__}: {exc}")
            await asyncio.sleep(5)


def install(app, db, server) -> SitNGoService:
    existing = getattr(app.state, "jj_sitngo", None)
    if existing:
        return existing

    service = SitNGoService(app, db, server)
    from sitngo_runtime import TournamentRuntime
    import sys
    service.runtime = TournamentRuntime(service, sys.modules["poker_engine"])
    app.state.jj_sitngo = service

    @app.get("/api/sitngo/next")
    def sitngo_next(user=Depends(server.current_user)):
        return service.next_event(int(user["id"]))

    @app.post("/api/sitngo/{event_id}/register")
    async def sitngo_register(event_id: str, user=Depends(server.current_user)):
        async with server.table_membership_lock:
            return service.register(event_id, int(user["id"]))

    @app.post("/api/sitngo/{event_id}/cancel-registration")
    def sitngo_cancel_registration(event_id: str, user=Depends(server.current_user)):
        return service.cancel_registration(event_id, int(user["id"]))

    @app.get("/api/admin/sitngo")
    def admin_sitngo(user=Depends(server.admin_user)):
        return service.admin_events(int(user["id"]))

    @app.post("/api/admin/sitngo")
    def admin_create_sitngo(payload: SitNGoCreateIn, user=Depends(server.admin_user)):
        return service.create_event(payload, int(user["id"]))

    @app.patch("/api/admin/sitngo/{event_id}")
    def admin_update_sitngo(event_id: str, payload: SitNGoUpdateIn, user=Depends(server.admin_user)):
        return service.update_event(event_id, payload, int(user["id"]))

    @app.post("/api/admin/sitngo/{event_id}/cancel")
    def admin_cancel_sitngo(event_id: str, payload: SitNGoCancelIn, user=Depends(server.admin_user)):
        return service.cancel_event(event_id, payload.reason, int(user["id"]))

    @app.delete("/api/admin/sitngo/{event_id}")
    def admin_delete_sitngo(event_id: str, user=Depends(server.admin_user)):
        return service.delete_event(event_id, int(user["id"]))

    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def sitngo_lifespan(app_instance):
        async with original_lifespan(app_instance):
            service.reconcile()
            task = asyncio.create_task(service.lifecycle_loop(), name="jj-sitngo-lifecycle")
            try:
                yield
            finally:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    app.router.lifespan_context = sitngo_lifespan
    return service


__all__ = [
    "BLIND_STRUCTURE",
    "LEVEL_MINUTES",
    "MAX_PLAYERS",
    "MIN_PLAYERS",
    "PREPARED_MINUTES",
    "SitNGoCreateIn",
    "SitNGoService",
    "SitNGoUpdateIn",
    "STARTING_STACK",
    "TARGET_MINUTES",
    "install",
]
