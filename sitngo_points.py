"""Transactional point integration for JJ Arena Sit&Go.

This module keeps tournament entry debits, cancellation refunds and finishing
payouts in the existing append-only point_ledger.  It is installed only around
root-level Sit&Go classes; materialized_v1244 and ring settlement remain
untouched.

Contracts:
* entry fee is event-owned and charged exactly once per registration cycle;
* official spendable points use the same fall-season total shown by rankings;
* a player cannot register when the authoritative balance is insufficient;
* cancellation before start and event cancellation refund exactly once;
* the prize pool is the sum of non-refunded entry debits at start/finish;
* <=5 entrants: first place receives the whole pool;
* 6 entrants: first receives 70%, second receives the remaining pool;
* tied finishing places share the prize slots occupied by the tie group;
* settlement is append-only and exactly-once at the database boundary.
"""
from __future__ import annotations

import json
import uuid
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import HTTPException

ENTRY_KIND = "sitngo_entry"
REFUND_KIND = "sitngo_refund"
PRIZE_KIND = "sitngo_prize"
MAX_ENTRY_FEE = 1_000_000
SIX_PLAYER_FIRST_PERCENT = 70
CENT = Decimal("0.01")


def _d(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)
    except Exception as exc:
        raise RuntimeError(f"invalid point amount: {value!r}") from exc


def _db_amount(db, value: Decimal):
    value = value.quantize(CENT, rounding=ROUND_HALF_UP)
    return value if getattr(db, "IS_POSTGRES", False) else float(value)


def _columns(db, con, table: str) -> set[str]:
    if getattr(db, "IS_POSTGRES", False):
        rows = con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=?",
            (table,),
        ).fetchall()
        return {str(row["column_name"]) for row in rows}
    return {str(row["name"]) for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


def _begin_write(db, con) -> None:
    if not getattr(db, "IS_POSTGRES", False):
        con.execute("BEGIN IMMEDIATE")


def _event_actor(con, event: dict) -> int:
    actor = int(event.get("created_by") or 0)
    if actor > 0:
        return actor
    row = con.execute("SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()
    if not row:
        raise RuntimeError("Sit&Go point settlement requires an administrator account")
    return int(row["id"])


def _effective_bounds(server) -> tuple[str, str]:
    return (
        str(getattr(server, "FALL_SEASON_START", "2026-09-01")),
        str(getattr(server, "FALL_SEASON_END", "2027-04-01")),
    )


def _ranking_identity(con, db, user_id: int, *, lock: bool) -> tuple[dict, str]:
    suffix = " FOR UPDATE" if lock and getattr(db, "IS_POSTGRES", False) else ""
    row = con.execute(
        "SELECT id,name,role,disabled,ranking_name FROM users WHERE id=?" + suffix,
        (int(user_id),),
    ).fetchone()
    if not row:
        raise HTTPException(404, "アカウントが見つかりません")
    user = dict(row)
    if int(user.get("disabled") or 0):
        raise HTTPException(403, "このアカウントは利用できません")
    identity = str(user.get("ranking_name") or user.get("name") or "").strip()
    if not identity:
        raise HTTPException(409, "ランキング紐付け名を確認してください")
    duplicate = con.execute(
        """SELECT COUNT(*) n FROM users
           WHERE COALESCE(disabled,0)=0
             AND COALESCE(NULLIF(ranking_name,''),name)=?""",
        (identity,),
    ).fetchone()
    if int(duplicate["n"] or 0) > 1:
        raise HTTPException(409, "同じランキング名に複数アカウントが紐付いています。管理者に確認してください")
    return user, identity


def official_balance(con, db, server, user_id: int, *, lock: bool = False) -> Decimal:
    """Return the account's authoritative fall-season point total.

    The calculation intentionally mirrors the production ranking: club entries,
    non-void online results, and every append-only point-ledger transaction.
    """
    _, identity = _ranking_identity(con, db, int(user_id), lock=lock)
    start, end = _effective_bounds(server)
    club = con.execute(
        """SELECT COALESCE(SUM(points),0) total FROM entries
           WHERE name=? AND date>=? AND date<?""",
        (identity, start, end),
    ).fetchone()
    try:
        online = con.execute(
            """SELECT COALESCE(SUM(r.points),0) total
               FROM online_hand_results r
               JOIN online_hands h ON h.hand_id=r.hand_id
               WHERE r.ranking_name=? AND COALESCE(h.voided,0)=0
                 AND h.played_at>=? AND h.played_at<?""",
            (identity, start, end),
        ).fetchone()
        online_total = _d(online["total"])
    except Exception:
        online_total = Decimal("0.00")
    ledger = con.execute(
        """SELECT COALESCE(SUM(l.amount),0) total
           FROM point_ledger l
           JOIN users u ON u.id=l.user_id
           WHERE COALESCE(NULLIF(u.ranking_name,''),u.name)=?
             AND l.effective_at>=? AND l.effective_at<?""",
        (identity, start, end),
    ).fetchone()
    return (_d(club["total"]) + online_total + _d(ledger["total"])).quantize(CENT)


def _insert_ledger(
    con,
    db,
    *,
    txid: str,
    user_id: int,
    amount: Decimal,
    kind: str,
    reason: str,
    actor_id: int,
    effective_at: str,
) -> None:
    con.execute(
        """INSERT INTO point_ledger(
               id,user_id,amount,kind,reason,effective_at,created_by,created_at,reversal_of
           ) VALUES (?,?,?,?,?,?,?,?,NULL)""",
        (
            txid,
            int(user_id),
            _db_amount(db, amount),
            kind,
            reason,
            effective_at,
            int(actor_id),
            effective_at,
        ),
    )


def _active_entry(con, event_id: str, user_id: int):
    return con.execute(
        """SELECT * FROM sitngo_point_entries
           WHERE event_id=? AND user_id=? AND refund_tx_id IS NULL
           ORDER BY cycle DESC LIMIT 1""",
        (event_id, int(user_id)),
    ).fetchone()


def _refund_entry(con, db, row, *, actor_id: int, reason: str, effective_at: str) -> Decimal:
    if not row or row["refund_tx_id"]:
        return Decimal("0.00")
    fee = _d(row["fee_points"])
    if fee <= 0:
        return Decimal("0.00")
    refund_id = "sng-refund-" + uuid.uuid4().hex
    _insert_ledger(
        con,
        db,
        txid=refund_id,
        user_id=int(row["user_id"]),
        amount=fee,
        kind=REFUND_KIND,
        reason=reason,
        actor_id=actor_id,
        effective_at=effective_at,
    )
    updated = con.execute(
        """UPDATE sitngo_point_entries
           SET refund_tx_id=?,refunded_at=?
           WHERE event_id=? AND user_id=? AND cycle=? AND refund_tx_id IS NULL""",
        (
            refund_id,
            effective_at,
            row["event_id"],
            int(row["user_id"]),
            int(row["cycle"]),
        ),
    )
    if int(getattr(updated, "rowcount", 0) or 0) != 1:
        raise RuntimeError("Sit&Go point refund lost exactly-once claim")
    return fee


def _payout_slots_cents(entrants: int, pool_points: Decimal) -> dict[int, int]:
    cents = int((pool_points * 100).to_integral_value())
    if entrants <= 0:
        return {}
    if entrants <= 5:
        return {1: cents}
    if entrants == 6:
        first = cents * SIX_PLAYER_FIRST_PERCENT // 100
        return {1: first, 2: cents - first}
    raise RuntimeError(f"unsupported Sit&Go field size for payout: {entrants}")


def calculate_payouts(results: list[dict], entrants: int, pool_points: Decimal) -> dict[int, Decimal]:
    """Split prize slots across TDA-ranked ties without losing a point cent."""
    slots = _payout_slots_cents(int(entrants), _d(pool_points))
    grouped: dict[int, list[dict]] = defaultdict(list)
    for result in results:
        grouped[int(result["place"])].append(result)

    awards_cents: dict[int, int] = {}
    for place in sorted(grouped):
        group = sorted(grouped[place], key=lambda item: int(item["user_id"]))
        width = len(group)
        prize = sum(int(slots.get(position, 0)) for position in range(place, place + width))
        if prize <= 0:
            continue
        share, remainder = divmod(prize, width)
        for index, result in enumerate(group):
            uid = int(result["user_id"])
            awards_cents[uid] = share + (1 if index < remainder else 0)

    expected = sum(slots.values())
    if sum(awards_cents.values()) != expected:
        raise RuntimeError(
            f"Sit&Go payout conservation failed: awarded={sum(awards_cents.values())} expected={expected}"
        )
    return {uid: (Decimal(cents) / 100).quantize(CENT) for uid, cents in awards_cents.items()}


def _refund_cancelled_entries(service) -> None:
    db = service.db
    with db.connect() as con:
        _begin_write(db, con)
        rows = con.execute(
            """SELECT pe.*,e.created_by,e.name
               FROM sitngo_point_entries pe
               JOIN sitngo_events e ON e.id=pe.event_id
               WHERE pe.refund_tx_id IS NULL AND e.status='cancelled'
               ORDER BY pe.event_id,pe.user_id,pe.cycle"""
        ).fetchall()
        for raw in rows:
            row = dict(raw)
            now = db.utcnow()
            _refund_entry(
                con,
                db,
                row,
                actor_id=_event_actor(con, row),
                reason=f"Sit&Go中止返金: {row.get('name') or row['event_id']}",
                effective_at=now,
            )


def settle_finished_event(runtime, event_id: str) -> dict | None:
    db = runtime.db
    server = runtime.server
    with db.connect() as con:
        _begin_write(db, con)
        suffix = " FOR UPDATE" if getattr(db, "IS_POSTGRES", False) else ""
        event_row = con.execute(
            "SELECT * FROM sitngo_events WHERE id=?" + suffix,
            (event_id,),
        ).fetchone()
        if not event_row:
            return None
        event = dict(event_row)
        if str(event.get("status")) != "finished":
            return None
        existing = con.execute(
            "SELECT * FROM sitngo_point_settlements WHERE event_id=?",
            (event_id,),
        ).fetchone()
        if existing:
            return dict(existing)

        game_row = con.execute(
            "SELECT state_json FROM sitngo_games WHERE event_id=?",
            (event_id,),
        ).fetchone()
        if not game_row:
            raise RuntimeError("finished Sit&Go is missing game state")
        state = json.loads(game_row["state_json"])
        tournament = state.get("tournament") or {}
        results = list(tournament.get("results") or [])
        entrants = int(tournament.get("entrants") or len(results))
        if len(results) != entrants:
            raise RuntimeError(
                f"Sit&Go results incomplete for point settlement: results={len(results)} entrants={entrants}"
            )

        fee = int(event.get("entry_fee_points") or 0)
        if fee < 0:
            raise RuntimeError("Sit&Go entry fee cannot be negative")
        rows = con.execute(
            """SELECT * FROM sitngo_point_entries
               WHERE event_id=? AND refund_tx_id IS NULL
               ORDER BY user_id,cycle""",
            (event_id,),
        ).fetchall()
        active_entries = [dict(row) for row in rows]
        if fee > 0:
            if len(active_entries) != entrants:
                raise RuntimeError(
                    f"Sit&Go paid-entry count mismatch: paid={len(active_entries)} entrants={entrants}"
                )
            if any(int(row["fee_points"]) != fee for row in active_entries):
                raise RuntimeError("Sit&Go entry fee changed after registration")
        elif active_entries:
            raise RuntimeError("free Sit&Go unexpectedly has active point debits")

        pool = _d(sum(int(row["fee_points"]) for row in active_entries))
        expected_pool = _d(fee * entrants)
        if pool != expected_pool:
            raise RuntimeError(f"Sit&Go prize pool mismatch: pool={pool} expected={expected_pool}")

        payouts = calculate_payouts(results, entrants, pool) if pool > 0 else {}
        result_by_user = {int(item["user_id"]): item for item in results}
        actor = _event_actor(con, event)
        now = db.utcnow()
        for uid, amount in sorted(payouts.items()):
            if amount <= 0:
                continue
            result = result_by_user[uid]
            payout_id = "sng-prize-" + uuid.uuid4().hex
            _insert_ledger(
                con,
                db,
                txid=payout_id,
                user_id=uid,
                amount=amount,
                kind=PRIZE_KIND,
                reason=f"Sit&Go賞金 {int(result['place'])}位: {event.get('name') or event_id}",
                actor_id=actor,
                effective_at=now,
            )
            con.execute(
                """INSERT INTO sitngo_point_payouts(
                       event_id,user_id,place,amount,payout_tx_id,created_at
                   ) VALUES (?,?,?,?,?,?)""",
                (
                    event_id,
                    uid,
                    int(result["place"]),
                    _db_amount(db, amount),
                    payout_id,
                    now,
                ),
            )

        policy = {
            "version": 1,
            "entrants": entrants,
            "five_or_fewer": {"1": 100},
            "six": {"1": SIX_PLAYER_FIRST_PERCENT, "2": "remainder"},
            "tie_rule": "aggregate_occupied_prize_slots_then_split",
        }
        con.execute(
            """INSERT INTO sitngo_point_settlements(
                   event_id,entrants,pool_points,policy_json,settled_at
               ) VALUES (?,?,?,?,?)""",
            (event_id, entrants, _db_amount(db, pool), json.dumps(policy, ensure_ascii=False), now),
        )
        con.execute(
            """INSERT INTO admin_audit_log(
                   actor_id,action,target_user_id,detail_json,created_at
               ) VALUES (?,?,?,?,?)""",
            (
                actor,
                "sitngo.points_settle",
                None,
                json.dumps(
                    {
                        "event_id": event_id,
                        "entry_fee_points": fee,
                        "pool_points": float(pool),
                        "payouts": {str(uid): float(amount) for uid, amount in payouts.items()},
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                now,
            ),
        )
        return {
            "event_id": event_id,
            "entrants": entrants,
            "pool_points": float(pool),
            "settled_at": now,
        }


def _settle_pending_finished(service) -> None:
    runtime = getattr(service, "runtime", None)
    if runtime is None:
        return
    with service.db.connect() as con:
        rows = con.execute(
            """SELECT e.id FROM sitngo_events e
               LEFT JOIN sitngo_point_settlements s ON s.event_id=e.id
               WHERE e.status='finished' AND s.event_id IS NULL
               ORDER BY e.updated_at,e.id LIMIT 20"""
        ).fetchall()
    for row in rows:
        settle_finished_event(runtime, str(row["id"]))


def _point_summary(service, event_id: str) -> dict:
    with service.db.connect() as con:
        event = con.execute(
            "SELECT entry_fee_points FROM sitngo_events WHERE id=?",
            (event_id,),
        ).fetchone()
        active = con.execute(
            """SELECT COALESCE(SUM(fee_points),0) total,COUNT(*) n
               FROM sitngo_point_entries
               WHERE event_id=? AND refund_tx_id IS NULL""",
            (event_id,),
        ).fetchone()
        refunded = con.execute(
            """SELECT COALESCE(SUM(fee_points),0) total,COUNT(*) n
               FROM sitngo_point_entries
               WHERE event_id=? AND refund_tx_id IS NOT NULL""",
            (event_id,),
        ).fetchone()
        settlement = con.execute(
            "SELECT entrants,pool_points,settled_at FROM sitngo_point_settlements WHERE event_id=?",
            (event_id,),
        ).fetchone()
        payouts = con.execute(
            """SELECT p.user_id,p.place,p.amount,u.name
               FROM sitngo_point_payouts p JOIN users u ON u.id=p.user_id
               WHERE p.event_id=? ORDER BY p.place,p.user_id""",
            (event_id,),
        ).fetchall()
    return {
        "entry_fee_points": int(event["entry_fee_points"] or 0) if event else 0,
        "collected_points": float(active["total"] or 0),
        "paid_entries": int(active["n"] or 0),
        "refunded_points": float(refunded["total"] or 0),
        "refunded_entries": int(refunded["n"] or 0),
        "settled": settlement is not None,
        "pool_points": float(settlement["pool_points"] or 0) if settlement else float(active["total"] or 0),
        "settled_at": settlement["settled_at"] if settlement else None,
        "payouts": [dict(row) for row in payouts],
    }


def install(sitngo_module, runtime_module) -> None:
    service_cls = sitngo_module.SitNGoService
    runtime_cls = runtime_module.TournamentRuntime
    if getattr(service_cls, "_jj_points_installed", False):
        return

    original_ensure_schema = service_cls._ensure_schema
    original_payload = service_cls._event_payload
    original_admin_events = service_cls.admin_events
    original_reconcile = service_cls.reconcile
    original_cancel_event = service_cls.cancel_event
    original_save = runtime_cls.save
    original_public = runtime_cls.public

    def ensure_schema(self):
        original_ensure_schema(self)
        uid = "BIGINT" if getattr(self.db, "IS_POSTGRES", False) else "INTEGER"
        amount_type = "NUMERIC(12,2)" if getattr(self.db, "IS_POSTGRES", False) else "REAL"
        with self.db.connect() as con:
            cols = _columns(self.db, con, "sitngo_events")
            if "entry_fee_points" not in cols:
                con.execute("ALTER TABLE sitngo_events ADD COLUMN entry_fee_points INTEGER NOT NULL DEFAULT 0")
            con.execute(
                f"""CREATE TABLE IF NOT EXISTS sitngo_point_entries(
                    event_id TEXT NOT NULL REFERENCES sitngo_events(id) ON DELETE CASCADE,
                    user_id {uid} NOT NULL REFERENCES users(id),
                    cycle INTEGER NOT NULL,
                    fee_points INTEGER NOT NULL,
                    entry_tx_id TEXT NOT NULL UNIQUE REFERENCES point_ledger(id),
                    refund_tx_id TEXT UNIQUE REFERENCES point_ledger(id),
                    created_at TEXT NOT NULL,
                    refunded_at TEXT,
                    PRIMARY KEY(event_id,user_id,cycle)
                )"""
            )
            con.execute(
                f"""CREATE TABLE IF NOT EXISTS sitngo_point_settlements(
                    event_id TEXT PRIMARY KEY REFERENCES sitngo_events(id) ON DELETE CASCADE,
                    entrants INTEGER NOT NULL,
                    pool_points {amount_type} NOT NULL,
                    policy_json TEXT NOT NULL,
                    settled_at TEXT NOT NULL
                )"""
            )
            con.execute(
                f"""CREATE TABLE IF NOT EXISTS sitngo_point_payouts(
                    event_id TEXT NOT NULL REFERENCES sitngo_events(id) ON DELETE CASCADE,
                    user_id {uid} NOT NULL REFERENCES users(id),
                    place INTEGER NOT NULL,
                    amount {amount_type} NOT NULL,
                    payout_tx_id TEXT NOT NULL UNIQUE REFERENCES point_ledger(id),
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(event_id,user_id)
                )"""
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_sitngo_point_entries_active ON sitngo_point_entries(event_id,refund_tx_id)"
            )

    def event_payload(self, row, user_id=None, *, admin=False):
        payload = original_payload(self, row, user_id, admin=admin)
        fee = int(dict(row).get("entry_fee_points") or 0)
        payload["entry_fee_points"] = fee
        payload["entry_fee"] = fee
        payload["payout_policy"] = {
            "five_or_fewer": "winner_take_all",
            "six_first_percent": SIX_PLAYER_FIRST_PERCENT,
            "six_second": "remainder",
            "tie_rule": "split_occupied_prize_slots",
        }
        if payload.get("status") in {"running", "finished"}:
            entrants = int((payload.get("tournament") or {}).get("entrants") or payload.get("participant_count") or 0)
            payload["prize_pool_points"] = fee * entrants
        else:
            payload["prize_pool_points"] = fee * int(payload.get("participant_count") or 0)

        if user_id is not None and not admin:
            try:
                with self.db.connect() as con:
                    balance = official_balance(con, self.db, self.runtime.server, int(user_id))
                payload["point_balance"] = float(balance)
                if payload.get("can_register") and balance < _d(fee):
                    payload["can_register"] = False
                    payload["registration_block_reason"] = "insufficient_points"
            except HTTPException as exc:
                payload["can_register"] = False
                payload["registration_block_reason"] = "point_identity"
                payload["point_balance_error"] = str(exc.detail)
        if admin or payload.get("status") in {"running", "finished"}:
            payload["point_summary"] = _point_summary(self, str(row["id"]))
        return payload

    def admin_events(self, actor_id: int):
        result = original_admin_events(self, actor_id)
        result.setdefault("defaults", {})["entry_fee_points"] = 0
        result["defaults"]["payout_policy"] = {
            "five_or_fewer": "winner_take_all",
            "six_first_percent": SIX_PLAYER_FIRST_PERCENT,
            "six_second": "remainder",
            "tie_rule": "split_occupied_prize_slots",
        }
        return result

    def register(self, event_id: str, user_id: int):
        if hasattr(self, "runtime") and self.runtime.ring_seated(user_id):
            raise HTTPException(409, "リングの席を離れてから大会に参加登録してください")
        now = sitngo_module._utcnow()
        with self._lock, self.db.connect() as con:
            _begin_write(self.db, con)
            balance = official_balance(con, self.db, self.runtime.server, int(user_id), lock=True)
            other = con.execute(
                """SELECT r.event_id FROM sitngo_registrations r
                   JOIN sitngo_events e ON e.id=r.event_id
                   WHERE r.user_id=? AND r.event_id<>?
                     AND r.status IN ('registered','active')
                     AND e.status IN ('scheduled','registration_open','starting','running')
                   LIMIT 1""",
                (int(user_id), event_id),
            ).fetchone()
            if other:
                raise HTTPException(409, "別のSit&Goへの参加登録または参加中です")

            event_row = con.execute("SELECT * FROM sitngo_events WHERE id=?", (event_id,)).fetchone()
            if not event_row:
                raise HTTPException(404, "Sit&Goが見つかりません")
            event = dict(event_row)
            starts = sitngo_module._parse_aware(str(event["starts_at"]))
            opens = sitngo_module._parse_aware(str(event["registration_opens_at"]))
            if not (opens <= now < starts) or event["status"] not in {"scheduled", "registration_open"}:
                raise HTTPException(400, "現在は参加受付時間ではありません")

            existing = con.execute(
                "SELECT status FROM sitngo_registrations WHERE event_id=? AND user_id=?",
                (event_id, int(user_id)),
            ).fetchone()
            if existing and existing["status"] != "cancelled":
                raise HTTPException(409, "すでに参加登録済みです")
            count = con.execute(
                "SELECT COUNT(*) n FROM sitngo_registrations WHERE event_id=? AND status='registered'",
                (event_id,),
            ).fetchone()
            if int(count["n"] or 0) >= int(event.get("max_players") or sitngo_module.MAX_PLAYERS):
                raise HTTPException(409, "満席です")

            fee = int(event.get("entry_fee_points") or 0)
            if fee < 0 or fee > MAX_ENTRY_FEE:
                raise RuntimeError("Sit&Go entry fee invariant failed")
            if balance < _d(fee):
                raise HTTPException(409, f"ポイントが不足しています（必要 {fee}pt / 現在 {float(balance):g}pt）")

            stamp = sitngo_module._iso(now)
            if existing:
                con.execute(
                    """UPDATE sitngo_registrations
                       SET status='registered',registered_at=?,cancelled_at=NULL,seat=NULL
                       WHERE event_id=? AND user_id=?""",
                    (stamp, event_id, int(user_id)),
                )
            else:
                con.execute(
                    """INSERT INTO sitngo_registrations(
                           event_id,user_id,status,registered_at,cancelled_at,seat
                       ) VALUES (?,?,'registered',?,NULL,NULL)""",
                    (event_id, int(user_id), stamp),
                )

            if fee > 0:
                cycle_row = con.execute(
                    "SELECT COALESCE(MAX(cycle),0) n FROM sitngo_point_entries WHERE event_id=? AND user_id=?",
                    (event_id, int(user_id)),
                ).fetchone()
                cycle = int(cycle_row["n"] or 0) + 1
                txid = "sng-entry-" + uuid.uuid4().hex
                _insert_ledger(
                    con,
                    self.db,
                    txid=txid,
                    user_id=int(user_id),
                    amount=-_d(fee),
                    kind=ENTRY_KIND,
                    reason=f"Sit&Go参加: {event.get('name') or event_id}",
                    actor_id=int(user_id),
                    effective_at=stamp,
                )
                con.execute(
                    """INSERT INTO sitngo_point_entries(
                           event_id,user_id,cycle,fee_points,entry_tx_id,refund_tx_id,created_at,refunded_at
                       ) VALUES (?,?,?,?,?,NULL,?,NULL)""",
                    (event_id, int(user_id), cycle, fee, txid, stamp),
                )
            if event["status"] == "scheduled":
                con.execute(
                    "UPDATE sitngo_events SET status='registration_open',updated_at=? WHERE id=?",
                    (stamp, event_id),
                )
        return self._event_payload(self._row(event_id), int(user_id))

    def cancel_registration(self, event_id: str, user_id: int):
        now = sitngo_module._utcnow()
        with self._lock, self.db.connect() as con:
            _begin_write(self.db, con)
            _ranking_identity(con, self.db, int(user_id), lock=True)
            event_row = con.execute("SELECT * FROM sitngo_events WHERE id=?", (event_id,)).fetchone()
            if not event_row:
                raise HTTPException(404, "Sit&Goが見つかりません")
            event = dict(event_row)
            starts = sitngo_module._parse_aware(str(event["starts_at"]))
            if now >= starts or event["status"] in {"starting", "running", "finished", "cancelled"}:
                raise HTTPException(400, "開始後は参加を取り消せません")
            reg = con.execute(
                "SELECT status FROM sitngo_registrations WHERE event_id=? AND user_id=?",
                (event_id, int(user_id)),
            ).fetchone()
            if not reg or reg["status"] != "registered":
                raise HTTPException(400, "参加登録されていません")
            stamp = sitngo_module._iso(now)
            active = _active_entry(con, event_id, int(user_id))
            if int(event.get("entry_fee_points") or 0) > 0 and not active:
                raise RuntimeError("paid Sit&Go registration is missing its entry debit")
            if active:
                _refund_entry(
                    con,
                    self.db,
                    active,
                    actor_id=int(user_id),
                    reason=f"Sit&Go参加取消返金: {event.get('name') or event_id}",
                    effective_at=stamp,
                )
            con.execute(
                """UPDATE sitngo_registrations
                   SET status='cancelled',cancelled_at=?,seat=NULL
                   WHERE event_id=? AND user_id=?""",
                (stamp, event_id, int(user_id)),
            )
        return self._event_payload(self._row(event_id), int(user_id))

    def reconcile(self, now=None):
        changed = original_reconcile(self, now)
        _refund_cancelled_entries(self)
        _settle_pending_finished(self)
        return changed

    def cancel_event(self, event_id: str, reason: str, actor_id: int):
        result = original_cancel_event(self, event_id, reason, actor_id)
        _refund_cancelled_entries(self)
        return self._event_payload(self._row(event_id), actor_id, admin=True)

    def save(self, state, *args, **kwargs):
        value = original_save(self, state, *args, **kwargs)
        if (state.get("tournament") or {}).get("status") == "finished":
            settle_finished_event(self, str(state["id"]))
        return value

    def public(self, state, viewer=None):
        value = original_public(self, state, viewer)
        tournament = value.get("tournament")
        if not isinstance(tournament, dict):
            return value
        event_id = str(tournament.get("event_id") or state.get("id") or "")
        fee = int(tournament.get("entry_fee") or 0)
        tournament["entry_fee"] = fee
        tournament["prize_points"] = fee * int(tournament.get("entrants") or 0)
        if tournament.get("status") == "finished" and event_id:
            with self.db.connect() as con:
                payouts = con.execute(
                    "SELECT user_id,amount FROM sitngo_point_payouts WHERE event_id=?",
                    (event_id,),
                ).fetchall()
                settled = con.execute(
                    "SELECT 1 FROM sitngo_point_settlements WHERE event_id=?",
                    (event_id,),
                ).fetchone()
            amounts = {int(row["user_id"]): float(row["amount"] or 0) for row in payouts}
            for result in tournament.get("results") or []:
                result["prize_points"] = amounts.get(int(result["user_id"]), 0.0)
            tournament["payout_settled"] = settled is not None
        value["tournament"] = tournament
        return value

    service_cls._ensure_schema = ensure_schema
    service_cls._event_payload = event_payload
    service_cls.admin_events = admin_events
    service_cls.register = register
    service_cls.cancel_registration = cancel_registration
    service_cls.reconcile = reconcile
    service_cls.cancel_event = cancel_event
    service_cls._jj_points_installed = True

    runtime_cls.save = save
    runtime_cls.public = public
    runtime_cls._jj_points_installed = True


__all__ = [
    "ENTRY_KIND",
    "REFUND_KIND",
    "PRIZE_KIND",
    "MAX_ENTRY_FEE",
    "SIX_PLAYER_FIRST_PERCENT",
    "calculate_payouts",
    "official_balance",
    "settle_finished_event",
    "install",
]
