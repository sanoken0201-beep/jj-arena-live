"""Admin-configurable Sit&Go tournament structures.

This root-level integration keeps ``materialized_v1244`` immutable while making
all tournament chip/blind settings event-owned. Existing events retain the
values already persisted in ``sitngo_events``; only newly created events use the
new 30,000-chip default unless an administrator chooses different values.
"""
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator
from decimal import Decimal
from sitngo_points import default_payouts, validate_payouts

DEFAULT_STARTING_STACK = 30_000
DEFAULT_TARGET_MINUTES = 90
COMPAT_LEVEL_MINUTES = 10
MAX_LEVELS = 30
MAX_PREPARED_MINUTES = 600

DEFAULT_BLIND_STRUCTURE = [
    {"level": 1, "small_blind": 200, "big_blind": 400, "bb_ante": 400, "minutes": 10},
    {"level": 2, "small_blind": 300, "big_blind": 600, "bb_ante": 600, "minutes": 10},
    {"level": 3, "small_blind": 500, "big_blind": 1_000, "bb_ante": 1_000, "minutes": 10},
    {"level": 4, "small_blind": 700, "big_blind": 1_400, "bb_ante": 1_400, "minutes": 10},
    {"level": 5, "small_blind": 1_000, "big_blind": 2_000, "bb_ante": 2_000, "minutes": 10},
    {"level": 6, "small_blind": 1_500, "big_blind": 3_000, "bb_ante": 3_000, "minutes": 10},
    {"level": 7, "small_blind": 2_000, "big_blind": 4_000, "bb_ante": 4_000, "minutes": 10},
    {"level": 8, "small_blind": 3_000, "big_blind": 6_000, "bb_ante": 6_000, "minutes": 10},
    {"level": 9, "small_blind": 5_000, "big_blind": 10_000, "bb_ante": 10_000, "minutes": 10},
    {"level": 10, "small_blind": 8_000, "big_blind": 16_000, "bb_ante": 16_000, "minutes": 10},
    {"level": 11, "small_blind": 10_000, "big_blind": 20_000, "bb_ante": 20_000, "minutes": 10},
    {"level": 12, "small_blind": 15_000, "big_blind": 30_000, "bb_ante": 30_000, "minutes": 10},
    {"level": 13, "small_blind": 20_000, "big_blind": 40_000, "bb_ante": 40_000, "minutes": 10},
    {"level": 14, "small_blind": 30_000, "big_blind": 60_000, "bb_ante": 60_000, "minutes": 10},
    {"level": 15, "small_blind": 40_000, "big_blind": 80_000, "bb_ante": 80_000, "minutes": 10},
]


class BlindLevelIn(BaseModel):
    level: int | None = None
    small_blind: int = Field(ge=100, le=100_000_000)
    big_blind: int = Field(ge=100, le=100_000_000)
    bb_ante: int = Field(ge=0, le=100_000_000)
    # Compatibility-only metadata. Blind progression is fixed at 12 completed hands.
    minutes: int = Field(default=COMPAT_LEVEL_MINUTES, ge=1, le=60)


class ConfiguredSitNGoCreateIn(BaseModel):
    entry_fee: Decimal = Field(default=Decimal(0), ge=0, le=1000000, decimal_places=2)
    payout_percentages: dict[str, list[Decimal]] = Field(default_factory=default_payouts)
    _validate_payouts = field_validator('payout_percentages')(validate_payouts)

    name: str = Field(default="JJ Sit&Go", min_length=1, max_length=80)
    starts_at: str = Field(min_length=10, max_length=50)
    starting_stack: int = Field(default=DEFAULT_STARTING_STACK, ge=1_000, le=10_000_000)
    structure: list[BlindLevelIn] | None = None


class ConfiguredSitNGoUpdateIn(BaseModel):
    entry_fee: Decimal | None = Field(default=None, ge=0, le=1000000, decimal_places=2)
    payout_percentages: dict[str, list[Decimal]] | None = None

    @field_validator('payout_percentages')
    @classmethod
    def check_payouts(cls, value):
        return validate_payouts(value) if value is not None else None

    name: str | None = Field(default=None, min_length=1, max_length=80)
    starts_at: str | None = Field(default=None, min_length=10, max_length=50)
    starting_stack: int | None = Field(default=None, ge=1_000, le=10_000_000)
    structure: list[BlindLevelIn] | None = None


def _level_dict(value: Any) -> dict[str, int]:
    if hasattr(value, "model_dump"):
        raw = value.model_dump()
    elif hasattr(value, "dict"):
        raw = value.dict()
    else:
        raw = dict(value)
    try:
        return {
            "small_blind": int(raw["small_blind"]),
            "big_blind": int(raw["big_blind"]),
            "bb_ante": int(raw.get("bb_ante", raw["big_blind"])),
            "minutes": int(raw.get("minutes", COMPAT_LEVEL_MINUTES)),
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(400, "ブラインドストラクチャーの形式が不正です") from exc


def _validate_stack(value: Any) -> int:
    try:
        stack = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "初期スタックは整数で入力してください") from exc
    if not 1_000 <= stack <= 10_000_000:
        raise HTTPException(400, "初期スタックは1,000〜10,000,000点で設定してください")
    if stack % 100:
        raise HTTPException(400, "初期スタックは100点単位で設定してください")
    return stack


def normalize_structure(
    raw_levels: Any,
    starting_stack: int,
    *,
    preserve_legacy_minutes: bool = False,
) -> list[dict[str, int]]:
    stack = _validate_stack(starting_stack)
    levels = list(raw_levels or [])
    if not levels:
        raise HTTPException(400, "ブラインドレベルを1つ以上設定してください")
    if len(levels) > MAX_LEVELS:
        raise HTTPException(400, f"ブラインドレベルは最大{MAX_LEVELS}個です")

    normalized: list[dict[str, int]] = []
    prior: dict[str, int] | None = None
    for index, item in enumerate(levels, start=1):
        level = _level_dict(item)
        sb, bb, ante = (
            level["small_blind"],
            level["big_blind"],
            level["bb_ante"],
        )
        stored_minutes = level["minutes"]
        minutes = stored_minutes if preserve_legacy_minutes else COMPAT_LEVEL_MINUTES
        if not (100 <= sb < bb <= 100_000_000):
            raise HTTPException(400, f"Lv.{index}: SBはBBより小さい正の値にしてください")
        if not 0 <= ante <= 100_000_000:
            raise HTTPException(400, f"Lv.{index}: BBAの値が不正です")
        if any(amount % 100 for amount in (sb, bb, ante)):
            raise HTTPException(400, f"Lv.{index}: SB・BB・BBAは100点単位で設定してください")
        if not 1 <= minutes <= 60:
            raise HTTPException(400, f"Lv.{index}: レベル時間は1〜60分で設定してください")
        if prior and (
            sb < prior["small_blind"]
            or bb < prior["big_blind"]
            or ante < prior["bb_ante"]
        ):
            raise HTTPException(400, f"Lv.{index}: ブラインド/アンティを前レベルより下げることはできません")
        normalized.append(
            {
                "level": index,
                "small_blind": sb,
                "big_blind": bb,
                "bb_ante": ante,
                "minutes": minutes,
            }
        )
        prior = normalized[-1]

    prepared = sum(level["minutes"] for level in normalized)
    if prepared > MAX_PREPARED_MINUTES:
        raise HTTPException(400, f"ストラクチャーの合計時間は最大{MAX_PREPARED_MINUTES}分です")
    if normalized[0]["big_blind"] >= stack:
        raise HTTPException(400, "Lv.1のBBは初期スタックより小さくしてください")
    return normalized


def _stored_structure(row: dict[str, Any]) -> list[dict[str, int]]:
    stack = int(row.get("starting_stack") or DEFAULT_STARTING_STACK)
    try:
        raw = json.loads(row.get("structure_json") or "[]")
        return normalize_structure(raw, stack, preserve_legacy_minutes=True)
    except (json.JSONDecodeError, HTTPException, TypeError, ValueError):
        # Legacy/corrupt rows should stay operable. This fallback is deliberately
        # not written back, so an administrator can inspect/correct the event.
        return normalize_structure(DEFAULT_BLIND_STRUCTURE, DEFAULT_STARTING_STACK, preserve_legacy_minutes=True)


def _structure_metrics(levels: list[dict[str, int]]) -> tuple[int, int, int]:
    prepared = sum(int(level["minutes"]) for level in levels)
    target = min(DEFAULT_TARGET_MINUTES, prepared)
    first_minutes = int(levels[0]["minutes"])
    return first_minutes, target, prepared


def install(sitngo_module) -> None:
    """Install the configurable event contract before ``sitngo.install()``."""
    if getattr(sitngo_module, "_JJ_ADMIN_STRUCTURE_PATCHED", False):
        return

    sitngo_module.STARTING_STACK = DEFAULT_STARTING_STACK
    sitngo_module.BLIND_STRUCTURE = deepcopy(DEFAULT_BLIND_STRUCTURE)
    sitngo_module.SitNGoCreateIn = ConfiguredSitNGoCreateIn
    sitngo_module.SitNGoUpdateIn = ConfiguredSitNGoUpdateIn

    service_cls = sitngo_module.SitNGoService
    original_payload = service_cls._event_payload
    original_next_event = service_cls.next_event

    def event_payload(self, row, user_id=None, *, admin=False):
        payload = original_payload(self, row, user_id, admin=admin)
        levels = _stored_structure(dict(row))
        _, target, prepared = _structure_metrics(levels)
        payload.update(
            structure=levels,
            target_minutes=int(row.get("target_minutes") or target),
            prepared_minutes=int(row.get("prepared_minutes") or prepared),
            config_editable=str(row.get("status")) in {"scheduled", "registration_open"},
        )
        return payload

    def next_event(self, user_id: int):
        result = original_next_event(self, user_id)
        event = result.get("event")
        result["structure"] = deepcopy(event["structure"] if event else sitngo_module.BLIND_STRUCTURE)
        return result

    def create_event(self, payload: ConfiguredSitNGoCreateIn, actor_id: int):
        starts = sitngo_module._parse_aware(payload.starts_at)
        if starts <= sitngo_module._utcnow() + sitngo_module.timedelta(minutes=1):
            raise HTTPException(400, "開催日時は現在より1分以上先に設定してください")
        stack = _validate_stack(payload.starting_stack)
        levels = normalize_structure(payload.structure or sitngo_module.BLIND_STRUCTURE, stack)
        level_minutes, target_minutes, prepared_minutes = _structure_metrics(levels)
        event_id = "sng-" + sitngo_module.uuid.uuid4().hex
        opens = sitngo_module._registration_open_for(starts)
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
                    sitngo_module._iso(starts),
                    sitngo_module._iso(opens),
                    "scheduled",
                    sitngo_module.MAX_PLAYERS,
                    sitngo_module.MIN_PLAYERS,
                    stack,
                    level_minutes,
                    target_minutes,
                    prepared_minutes,
                    json.dumps(levels, ensure_ascii=False, separators=(",", ":")),
                    actor_id,
                    stamp,
                    stamp,
                ),
            )
            self.points.configure(con, event_id, payload.entry_fee, payload.payout_percentages)
        self._audit(
            actor_id,
            "sitngo.create",
            entry_fee=str(payload.entry_fee),
            payout_percentages={n:[str(v) for v in r] for n,r in payload.payout_percentages.items()},
            event_id=event_id,
            starts_at=sitngo_module._iso(starts),
            name=payload.name.strip(),
            starting_stack=stack,
            structure=levels,
        )
        return self._event_payload(self._row(event_id), actor_id, admin=True)

    def update_event(self, event_id: str, payload: ConfiguredSitNGoUpdateIn, actor_id: int):
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
            if payload.entry_fee is not None or payload.payout_percentages is not None:
                fee = payload.entry_fee if payload.entry_fee is not None else Decimal(self.points.fee(con,event_id))/100
                rates = payload.payout_percentages if payload.payout_percentages is not None else self.points.payouts(con,event_id)
                old_rates=self.points.payouts(con,event_id)
                is_changed = self.points.fee(con,event_id) != int(fee*100) or any([Decimal(str(v)) for v in rates[n]] != [Decimal(str(v)) for v in old_rates[n]] for n in rates)
                if is_changed:
                    if con.execute('SELECT 1 FROM sitngo_registrations WHERE event_id=? LIMIT 1',(event_id,)).fetchone():
                        raise HTTPException(409,'参加登録後は参加費・配当率を変更できません。中止して新しい大会を作成してください')
                    self.points.configure(con,event_id,fee,rates)
                    changed.update(entry_fee=str(fee),payout_percentages={n:[str(v) for v in r] for n,r in rates.items()})
            if payload.name is not None:
                name = payload.name.strip()
                if not name:
                    raise HTTPException(400, "大会名を入力してください")
                sets.append("name=?")
                args.append(name)
                changed["name"] = name
            if payload.starts_at is not None:
                starts = sitngo_module._parse_aware(payload.starts_at)
                if starts <= sitngo_module._utcnow() + sitngo_module.timedelta(minutes=1):
                    raise HTTPException(400, "開催日時は現在より1分以上先に設定してください")
                opens = sitngo_module._registration_open_for(starts)
                status = "registration_open" if sitngo_module._utcnow() >= opens else "scheduled"
                sets.extend(["starts_at=?", "registration_opens_at=?", "status=?"])
                args.extend([sitngo_module._iso(starts), sitngo_module._iso(opens), status])
                changed["starts_at"] = sitngo_module._iso(starts)
            if payload.starting_stack is not None or payload.structure is not None:
                stack = _validate_stack(payload.starting_stack if payload.starting_stack is not None else event["starting_stack"])
                raw_levels = payload.structure if payload.structure is not None else json.loads(event["structure_json"])
                levels = normalize_structure(
                    raw_levels,
                    stack,
                    preserve_legacy_minutes=payload.structure is None,
                )
                level_minutes, target_minutes, prepared_minutes = _structure_metrics(levels)
                sets.extend(
                    [
                        "starting_stack=?",
                        "level_minutes=?",
                        "target_minutes=?",
                        "prepared_minutes=?",
                        "structure_json=?",
                    ]
                )
                args.extend(
                    [
                        stack,
                        level_minutes,
                        target_minutes,
                        prepared_minutes,
                        json.dumps(levels, ensure_ascii=False, separators=(",", ":")),
                    ]
                )
                changed.update(starting_stack=stack, structure=levels)
            if sets:
                sets.append("updated_at=?")
                args.append(self.db.utcnow())
                args.append(event_id)
                con.execute(f"UPDATE sitngo_events SET {','.join(sets)} WHERE id=?", args)
        if changed:
            self._audit(actor_id, "sitngo.update", event_id=event_id, changed=changed)
        return self._event_payload(self._row(event_id), actor_id, admin=True)

    service_cls._event_payload = event_payload
    service_cls.next_event = next_event
    service_cls.create_event = create_event
    service_cls.update_event = update_event

    import sitngo_runtime

    def runtime_create(self, con, event, participants, now):
        eid = event["id"]
        if con.execute("SELECT event_id FROM sitngo_games WHERE event_id=?", (eid,)).fetchone():
            return
        stack = _validate_stack(event["starting_stack"])
        levels = normalize_structure(json.loads(event["structure_json"]), stack, preserve_legacy_minutes=True)
        first = levels[0]
        engine = self.engine
        state = engine.blank_table_state(
            table_id=eid,
            name=event["name"],
            max_seats=6,
            small_blind=first["small_blind"],
            big_blind=first["big_blind"],
            min_buyin=stack,
            max_buyin=stack,
        )
        for uid, seat in participants:
            user = con.execute("SELECT name FROM users WHERE id=?", (uid,)).fetchone()
            engine.seat_player(state, user_id=uid, name=user["name"], seat=seat, stack=stack)
        state.update(
            session_active=True,
            rake_percent=0,
            rake_cap=0,
            _revision=0,
            tournament={
                "event_id": eid,
                "status": "running",
                "entry_fee": self.service.points.fee(con,eid)/100,
                "prize_points": self.service.points.fee(con,eid)*len(participants)/100,
                "payout_percentages": self.service.points.payouts(con,eid)[str(len(participants))],
                "started_at_epoch": now.timestamp(),
                "clock_at_epoch": now.timestamp(),
                "elapsed_seconds": 0,
                "level": 1,
                "bb_ante": first["bb_ante"],
                "structure": levels,
                "results": [],
                "entrants": len(participants),
                "total_chips": len(participants) * stack,
            },
        )
        engine.start_hand(state)
        self.server.arm_action_deadline(state)
        con.execute(
            "INSERT INTO sitngo_games(event_id,state_json,revision,updated_at) VALUES (?,?,0,?)",
            (eid, json.dumps(state, ensure_ascii=False), self.db.utcnow()),
        )
        self.signal()

    sitngo_runtime.TournamentRuntime.create = runtime_create
    sitngo_module._JJ_ADMIN_STRUCTURE_PATCHED = True


__all__ = [
    "BlindLevelIn",
    "ConfiguredSitNGoCreateIn",
    "ConfiguredSitNGoUpdateIn",
    "COMPAT_LEVEL_MINUTES",
    "DEFAULT_BLIND_STRUCTURE",
    "DEFAULT_STARTING_STACK",
    "install",
    "normalize_structure",
]
