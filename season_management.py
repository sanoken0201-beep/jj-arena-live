"""Additive season metadata and future drafts; no ranking reset in phase 2.

Legacy fall/summer accounting windows remain immutable until the audited phase-3
cutover migrates *all* result writers, readers and point validators together.
"""
from __future__ import annotations

import re
import uuid
from datetime import date

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

SEASON_STATES = ("active", "archived", "draft")
_NAME_LIMIT = 80


class SeasonCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=_NAME_LIMIT)
    start_date: str
    end_exclusive: str


class SeasonPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=_NAME_LIMIT)
    start_date: str | None = None
    end_exclusive: str | None = None


def _clean_name(value: str) -> str:
    name = " ".join(value.strip().split())
    if not name or len(name) > _NAME_LIMIT or any(ord(char) < 32 for char in name):
        raise HTTPException(400, "シーズン名が不正です")
    return name


def _date_string(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise HTTPException(400, "日付はYYYY-MM-DD形式で入力してください")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise HTTPException(400, "実在する日付を入力してください") from None
    if parsed.year < 2026:
        raise HTTPException(400, "新しいシーズンは2026年以降の日付にしてください")
    return parsed.isoformat()


def _validate_range(start: str, end: str) -> tuple[str, str]:
    start = _date_string(start)
    end = _date_string(end)
    if start >= end:
        raise HTTPException(400, "シーズン終了日は開始日より後にしてください")
    if (date.fromisoformat(end) - date.fromisoformat(start)).days > 1096:
        raise HTTPException(400, "シーズン期間は3年以内にしてください")
    return start, end


def _no_overlap(con, start: str, end: str, *, exclude_id: str | None = None) -> None:
    sql = "SELECT season_id FROM jj_seasons WHERE start_date<? AND end_exclusive>?"
    args = [end, start]
    if exclude_id is not None:
        sql += " AND season_id<>?"
        args.append(exclude_id)
    overlapping = con.execute(sql + " LIMIT 1", args).fetchone()
    if overlapping:
        raise HTTPException(409, "既存シーズンの期間と重複しています")


def _row(row) -> dict:
    return dict(row)


def _init(db, server) -> None:
    now = db.utcnow()
    fall_start = str(getattr(server, "FALL_SEASON_START", "2026-09-01"))
    fall_end = str(getattr(server, "FALL_SEASON_END", "2027-04-01"))
    with db.connect() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS jj_seasons(
                season_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                start_date TEXT NOT NULL,
                end_exclusive TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('active','archived','draft')),
                locked_bounds INTEGER NOT NULL DEFAULT 0 CHECK(locked_bounds IN (0,1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                updated_by BIGINT REFERENCES users(id),
                CHECK(start_date < end_exclusive)
            )"""
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_jj_seasons_dates ON jj_seasons(start_date,end_exclusive)")
        for values in (
            ("summer", "JJ 2026 Summer Season", "0000-01-01", fall_start, "archived", 1),
            ("fall", "JJ 2026 Winter Season", fall_start, fall_end, "active", 1),
        ):
            con.execute(
                """INSERT INTO jj_seasons
                (season_id,name,start_date,end_exclusive,status,locked_bounds,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(season_id) DO NOTHING""",
                (*values, now, now),
            )
        existing = con.execute(
            "SELECT season_id,start_date,end_exclusive,status,locked_bounds FROM jj_seasons "
            "WHERE season_id IN ('summer','fall')"
        ).fetchall()
        expected = {
            "summer": ("0000-01-01", fall_start),
            "fall": (fall_start, fall_end),
        }
        if len(existing) != 2:
            raise RuntimeError("Legacy season metadata was not initialized")
        for row in existing:
            if ((row["start_date"],row["end_exclusive"]) != expected[row["season_id"]]
                    or int(row["locked_bounds"]) != 1
                    or (row["season_id"] == "summer" and row["status"] != "archived")
                    or (row["season_id"] == "fall" and row["status"] not in ("active","archived"))):
                raise RuntimeError("Legacy season metadata drifted from the live accounting contract")
        active = con.execute("SELECT COUNT(*) n FROM jj_seasons WHERE status='active'").fetchone()
        if int(active["n"]) != 1:
            raise RuntimeError("Season catalog must have exactly one active season")



def active_season(db, *, con=None) -> dict:
    if con is None:
        with db.connect() as connection:
            return active_season(db, con=connection)
    row = con.execute(
        "SELECT * FROM jj_seasons WHERE status='active' LIMIT 1"
    ).fetchone()
    if not row:
        raise RuntimeError("No active JJ season is configured")
    return dict(row)


def bounds(db, season: str = "fall") -> tuple[str, str]:
    """Resolve periods without exposing draft data.

    Legacy callers pass season='fall' for the CURRENT rankings. The fixed
    historical 2026 Winter Season becomes available as 'archive:fall' once
    archived; earlier summer retains its legacy ID.
    """
    key = (season or "fall").strip().lower()
    with db.connect() as con:
        if key in ("active", "fall"):
            row = active_season(db, con=con)
        else:
            season_id = key[len("archive:"):] if key.startswith("archive:") else key
            row = con.execute(
                "SELECT * FROM jj_seasons WHERE season_id=?", (season_id,)
            ).fetchone()
        if not row:
            raise HTTPException(400, "不明なシーズンです")
        if row["status"] == "draft":
            raise HTTPException(400, "準備中のシーズンはランキングに表示できません")
        if key.startswith("archive:") and row["status"] != "archived":
            raise HTTPException(400, "このシーズンはまだ過去シーズンではありません")
        return str(row["start_date"]), str(row["end_exclusive"])


def install(app, server, db, admin_console) -> None:
    if getattr(app.state, "jj_season_management_installed", False):
        return
    _init(db, server)
    app.state.jj_season_management_installed = True

    @app.get("/api/seasons")
    def seasons(user=Depends(server.current_user)):
        """Player-visible labels; drafts are never exposed until phase 3 activation."""
        with db.connect() as con:
            rows = con.execute(
                "SELECT season_id,name,start_date,end_exclusive,status FROM jj_seasons "
                "WHERE status IN ('active','archived') ORDER BY start_date DESC"
            ).fetchall()
        return [_row(row) for row in rows]

    @app.get("/api/admin/console/seasons")
    def admin_seasons(user=Depends(server.admin_user)):
        with db.connect() as con:
            rows = con.execute(
                "SELECT * FROM jj_seasons ORDER BY start_date DESC,season_id"
            ).fetchall()
        return [_row(row) for row in rows]

    @app.post("/api/admin/console/seasons", status_code=201)
    def create_season(payload: SeasonCreate, user=Depends(server.admin_user)):
        name = _clean_name(payload.name)
        start, end = _validate_range(payload.start_date, payload.end_exclusive)
        season_id = "season-" + uuid.uuid4().hex
        with db.connect() as con:
            _no_overlap(con, start, end)
            con.execute(
                """INSERT INTO jj_seasons
                (season_id,name,start_date,end_exclusive,status,locked_bounds,created_at,updated_at,updated_by)
                VALUES (?,?,?,?,'draft',0,?,?,?)""",
                (season_id, name, start, end, db.utcnow(), db.utcnow(), int(user["id"])),
            )
            admin_console._audit(
                db, int(user["id"]), "season.create", con=con,
                season_id=season_id, name=name, start_date=start,
                end_exclusive=end, status="draft",
            )
            saved = con.execute("SELECT * FROM jj_seasons WHERE season_id=?", (season_id,)).fetchone()
        return _row(saved)

    @app.patch("/api/admin/console/seasons/{season_id}")
    def update_season(season_id: str, payload: SeasonPatch, user=Depends(server.admin_user)):
        with db.connect() as con:
            original = con.execute(
                "SELECT * FROM jj_seasons WHERE season_id=?", (season_id,)
            ).fetchone()
            if not original:
                raise HTTPException(404, "シーズンがありません")
            before = _row(original)
            name = _clean_name(payload.name) if payload.name is not None else before["name"]
            start = payload.start_date if payload.start_date is not None else before["start_date"]
            end = payload.end_exclusive if payload.end_exclusive is not None else before["end_exclusive"]
            if int(before["locked_bounds"]):
                if start != before["start_date"] or end != before["end_exclusive"]:
                    raise HTTPException(
                        409,
                        "現在・過去の確定済みシーズン期間は変更できません。次期切替で期間を設定してください",
                    )
            else:
                start, end = _validate_range(start, end)
                _no_overlap(con, start, end, exclude_id=season_id)

            changed = {
                key: [before[key], value]
                for key, value in (
                    ("name", name), ("start_date", start), ("end_exclusive", end)
                )
                if before[key] != value
            }
            if changed:
                con.execute(
                    "UPDATE jj_seasons SET name=?,start_date=?,end_exclusive=?,updated_at=?,updated_by=? "
                    "WHERE season_id=?",
                    (name, start, end, db.utcnow(), int(user["id"]), season_id),
                )
                admin_console._audit(
                    db, int(user["id"]), "season.update", con=con,
                    season_id=season_id, changed=changed,
                )
            saved = con.execute("SELECT * FROM jj_seasons WHERE season_id=?", (season_id,)).fetchone()
        return _row(saved)
