from __future__ import annotations

"""Safety boundary for official club-result point entries.

The historical entry API stores a club result as a single row in `entries`.
This module adds strict calendar/range validation plus optional request
idempotency for every official submission without changing the immutable materialized v1.24.4 core.
"""

import json
import re
import uuid
from datetime import datetime

from fastapi import HTTPException


_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{16,80}$")
_DEFAULT_ABS_POINTS_LIMIT = 100_000.0


def ensure_schema(db) -> None:
    uid = "BIGINT" if getattr(db, "IS_POSTGRES", False) else "INTEGER"
    with db.connect() as con:
        con.execute(
            f"""CREATE TABLE IF NOT EXISTS club_entry_requests(
                actor_id {uid} NOT NULL REFERENCES users(id),
                request_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                response_json TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY(actor_id,request_id)
            )"""
        )


def _limit(db) -> float:
    try:
        with db.connect() as con:
            row = con.execute(
                "SELECT value FROM app_settings WHERE key='manual_adjustment_limit'"
            ).fetchone()
        value = float(row["value"]) if row else _DEFAULT_ABS_POINTS_LIMIT
        return max(1.0, value)
    except Exception:
        return _DEFAULT_ABS_POINTS_LIMIT


def _core_payload(server, payload, *, forced_name: str | None = None):
    values = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    values.pop("request_id", None)
    if forced_name is not None:
        values["name"] = forced_name
    values["name"] = str(values.get("name") or "").strip()
    return server.PointEntry(**values)


def _validate(db, server, payload) -> None:
    name = str(payload.name or "").strip()
    if not name:
        raise HTTPException(400, "プレイヤー名を入力してください")
    if len(name) > 60:
        raise HTTPException(400, "プレイヤー名が長すぎます")

    raw_date = str(payload.date or "").strip()
    try:
        parsed = datetime.fromisoformat(raw_date)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "実在する日時を入力してください") from exc
    entry_day = parsed.date().isoformat()
    start = str(getattr(server, "FALL_SEASON_START", "2026-09-01"))
    end = str(getattr(server, "FALL_SEASON_END", "2027-04-01"))
    if not start <= entry_day < end:
        raise HTTPException(400, "後期期間（2026/9/1〜2027/3/31）の日付を入力してください")

    game_type = str(payload.game_type or "").strip().lower()
    ring_initials = {450, 900, 2000}
    tournament_initials = {300, 400, 500, 600, 800, 1000}
    allowed = ring_initials if game_type == "ring" else tournament_initials if game_type == "tournament" else set()
    if payload.initial not in allowed:
        raise HTTPException(400, "初期点はフォームの選択肢から選んでください")

    counts = {
        1: int(payload.chip_1),
        5: int(payload.chip_5),
        10: int(payload.chip_10),
        25: int(payload.chip_25),
        100: int(payload.chip_100),
        500: int(payload.chip_500),
    }
    remaining = sum(value * count for value, count in counts.items())
    points = remaining - (int(payload.reentries) + 1) * int(payload.initial)
    cap = _limit(db)
    if remaining > cap or abs(points) > cap:
        raise HTTPException(400, f"1件の結果は残りチップ・収支ともに{cap:g}pt以内にしてください")


def _identity(payload) -> str:
    values = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    values.pop("request_id", None)
    return json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _record_entry(con, db, core, user):
    """Record the validated club result on the caller's DB transaction.

    Mirror the materialized v1.24.4 `server.add_entry` row contract, but do not
    open a second connection: the request receipt and point entry MUST commit
    together or roll back together.
    """
    game_type = core.game_type.strip().lower()
    ring_initials = {
        450: "450 / blind 1-3-3",
        900: "900 / blind 2-5-5",
        2000: "2000 / blind 5-10-10",
    }
    tournament_initials = {
        300: "300 / tournament", 400: "400 / tournament",
        500: "500 / tournament", 600: "600 / tournament",
        800: "800 / tournament", 1000: "1000 / tournament",
    }
    initial_map = ring_initials if game_type == "ring" else tournament_initials
    counts = {
        1: core.chip_1, 5: core.chip_5, 10: core.chip_10,
        25: core.chip_25, 100: core.chip_100, 500: core.chip_500,
    }
    remaining = sum(value * count for value, count in counts.items())
    points = remaining - (core.reentries + 1) * core.initial
    entry_id = "live-" + uuid.uuid4().hex
    con.execute(
        """INSERT INTO entries(
           id,date,name,remaining,reentries,initial,points,game,game_type,
           source,created_by,created_at,chip_1,chip_5,chip_10,chip_25,chip_100,chip_500
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            entry_id, core.date, core.name.strip(), remaining,
            core.reentries, core.initial, points, initial_map[core.initial],
            game_type, "JJ Arena Live", user["id"], db.utcnow(),
            core.chip_1, core.chip_5, core.chip_10,
            core.chip_25, core.chip_100, core.chip_500,
        ),
    )
    return {
        "id": entry_id, "remaining": remaining, "points": points,
        "chips": {str(k): v for k, v in counts.items()},
    }


def apply_entry(db, server, payload, user, *, forced_name: str | None = None):
    core = _core_payload(server, payload, forced_name=forced_name)
    _validate(db, server, core)

    request_id = str(getattr(payload, "request_id", "") or "").strip()
    if not request_id:
        # Both administrators and members must have an idempotency receipt.
        # Stale browsers and old API scripts cannot bypass atomic settlement:
        # an unkeyed retry could otherwise create another official point row.
        raise HTTPException(
            428,
            "ポイント入力画面を更新してから再送信してください（操作IDがありません）",
        )
    if not _REQUEST_ID.fullmatch(request_id):
        raise HTTPException(400, "操作IDの形式が不正です")

    actor_id = int(user["id"])
    identity = _identity(core)
    ensure_schema(db)
    with db.connect() as con:
        claimed = con.execute(
            """INSERT INTO club_entry_requests(actor_id,request_id,payload_json,created_at)
               VALUES (?,?,?,?) ON CONFLICT(actor_id,request_id) DO NOTHING""",
            (actor_id, request_id, identity, db.utcnow()),
        ).rowcount
        if not claimed:
            row = con.execute(
                """SELECT payload_json,response_json FROM club_entry_requests
                   WHERE actor_id=? AND request_id=?""",
                (actor_id, request_id),
            ).fetchone()
            if row is None:
                raise HTTPException(409, "操作の記録を確認できません。履歴を確認してください")
            if row["payload_json"] != identity:
                raise HTTPException(409, "同じ操作IDで異なる結果は送信できません")
            if row["response_json"]:
                return json.loads(row["response_json"])
            # Old, already-partial receipts cannot be safely auto-replayed:
            # their entry may have committed before the response was lost.
            raise HTTPException(409, "同じ結果を処理中です。履歴を確認してから再操作してください")

        # A single transaction owns claim, result, and receipt. A crash or SQL
        # failure cannot strand a claim or write an unacknowledged club entry.
        result = _record_entry(con, db, core, user)
        con.execute(
            """UPDATE club_entry_requests SET response_json=?
               WHERE actor_id=? AND request_id=?""",
            (
                json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                actor_id, request_id,
            ),
        )
    return result


__all__ = ["apply_entry", "ensure_schema"]
