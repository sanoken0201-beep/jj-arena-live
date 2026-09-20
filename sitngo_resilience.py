"""Generation backups and corruption recovery for persisted Sit&Go state.

The tournament runtime persists its authoritative state in sitngo_games.
Normal process restarts already resume that row. This layer covers the rarer
case where the current JSON itself is malformed or structurally unusable.

Snapshots are written only after successful tournament saves/creation. Their
identity ignores heartbeat-only clock/revision fields so the event-driven
five-second heartbeat cannot churn backup retention. The stored snapshot still
contains the complete private state needed to resume play.

Backup failure is fail-open for gameplay. Recovery is fail-closed: a corrupt
current row is replaced only by a validated snapshot for the same event.
"""
from __future__ import annotations

import copy
import hashlib
import json
import uuid
from typing import Any

from fastapi import HTTPException

KEEP_PER_EVENT = 40


def _semantic_digest(state: dict[str, Any]) -> str:
    value = copy.deepcopy(state)
    value.pop("_revision", None)
    tournament = value.get("tournament")
    if isinstance(tournament, dict):
        tournament.pop("clock_at_epoch", None)
        tournament.pop("elapsed_seconds", None)
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _state_json(state: dict[str, Any]) -> str:
    return json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _validate_state(event_id: str, state: Any, revision: int | None = None) -> dict[str, Any]:
    if not isinstance(state, dict):
        raise ValueError("Sit&Go state must be an object")
    if str(state.get("id") or "") != str(event_id):
        raise ValueError("Sit&Go state event id mismatch")
    tournament = state.get("tournament")
    if not isinstance(tournament, dict) or str(tournament.get("event_id") or "") != str(event_id):
        raise ValueError("Sit&Go tournament event id mismatch")
    if not isinstance(state.get("seats"), list):
        raise ValueError("Sit&Go seats are missing")
    try:
        state_revision = int(state.get("_revision"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Sit&Go state revision is invalid") from exc
    if revision is not None and state_revision != int(revision):
        raise ValueError("Sit&Go state/database revision mismatch")
    return state


def ensure_schema(db) -> None:
    with db.connect() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS sitngo_state_backups(
                id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL REFERENCES sitngo_events(id) ON DELETE CASCADE,
                revision INTEGER NOT NULL,
                state_json TEXT NOT NULL,
                state_sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_sitngo_backup_event "
            "ON sitngo_state_backups(event_id,revision DESC,created_at DESC)"
        )
        con.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_sitngo_backup_hash "
            "ON sitngo_state_backups(event_id,state_sha256)"
        )


def backup_state(db, state: dict[str, Any]) -> bool:
    """Persist one meaningful snapshot without ever blocking gameplay."""
    try:
        event_id = str(state.get("id") or "")
        revision = int(state.get("_revision"))
        _validate_state(event_id, state, revision)
        raw = _state_json(state)
        digest = _semantic_digest(state)
        with db.connect() as con:
            con.execute(
                """INSERT INTO sitngo_state_backups(
                    id,event_id,revision,state_json,state_sha256,created_at
                ) VALUES (?,?,?,?,?,?)
                ON CONFLICT(event_id,state_sha256) DO NOTHING""",
                ("sngb-" + uuid.uuid4().hex, event_id, revision, raw, digest, db.utcnow()),
            )
            rows = con.execute(
                "SELECT id FROM sitngo_state_backups "
                "WHERE event_id=? ORDER BY revision DESC,created_at DESC,id DESC",
                (event_id,),
            ).fetchall()
            for row in rows[KEEP_PER_EVENT:]:
                con.execute("DELETE FROM sitngo_state_backups WHERE id=?", (row["id"],))
        return True
    except Exception as exc:
        try:
            import resilience

            resilience.record_error(
                db,
                "sitngo_state_backup",
                f"{type(exc).__name__}: {exc}",
            )
        except Exception:
            pass
        return False


def restore_latest(db, event_id: str) -> dict[str, Any]:
    """Restore the newest valid same-event snapshot or fail closed."""
    with db.connect() as con:
        current = con.execute(
            "SELECT revision FROM sitngo_games WHERE event_id=?",
            (event_id,),
        ).fetchone()
        if not current:
            raise HTTPException(404, "大会テーブルの準備中です")
        current_revision = int(current["revision"])
        rows = con.execute(
            "SELECT id,revision,state_json FROM sitngo_state_backups "
            "WHERE event_id=? ORDER BY revision DESC,created_at DESC,id DESC",
            (event_id,),
        ).fetchall()
        for row in rows:
            try:
                state = json.loads(row["state_json"])
                _validate_state(event_id, state, int(row["revision"]))
            except Exception:
                continue
            updated = con.execute(
                "UPDATE sitngo_games SET state_json=?,revision=?,updated_at=? "
                "WHERE event_id=? AND revision=?",
                (
                    row["state_json"],
                    int(row["revision"]),
                    db.utcnow(),
                    event_id,
                    current_revision,
                ),
            )
            if updated.rowcount != 1:
                raise HTTPException(409, "大会の状態が更新されました。再接続してください")
            try:
                import resilience

                resilience.record_error(
                    db,
                    "sitngo_state_auto_restore",
                    f"restored revision {int(row['revision'])}",
                    path=event_id,
                )
            except Exception:
                pass
            return state
    raise RuntimeError("Sit&Go current state is corrupt and no valid backup exists")


def install(runtime_module) -> None:
    runtime_cls = runtime_module.TournamentRuntime
    if getattr(runtime_cls, "_jj_state_resilience_installed", False):
        return

    original_init = runtime_cls.__init__
    original_create = runtime_cls.create
    original_save = runtime_cls.save
    original_load = runtime_cls.load

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        ensure_schema(self.db)

    def create(self, con, event, participants, now):
        value = original_create(self, con, event, participants, now)
        try:
            row = con.execute(
                "SELECT state_json,revision FROM sitngo_games WHERE event_id=?",
                (event["id"],),
            ).fetchone()
            if row:
                state = json.loads(row["state_json"])
                _validate_state(str(event["id"]), state, int(row["revision"]))
                backup_state(self.db, state)
        except Exception as exc:
            try:
                import resilience

                resilience.record_error(
                    self.db,
                    "sitngo_state_backup",
                    f"{type(exc).__name__}: {exc}",
                )
            except Exception:
                pass
        return value

    def save(self, state, *args, **kwargs):
        value = original_save(self, state, *args, **kwargs)
        backup_state(self.db, state)
        return value

    def load(self, event_id):
        try:
            state = original_load(self, event_id)
            with self.db.connect() as con:
                row = con.execute(
                    "SELECT revision FROM sitngo_games WHERE event_id=?",
                    (event_id,),
                ).fetchone()
            if not row:
                raise HTTPException(404, "大会テーブルの準備中です")
            return _validate_state(str(event_id), state, int(row["revision"]))
        except HTTPException:
            raise
        except Exception:
            return restore_latest(self.db, str(event_id))

    runtime_cls.__init__ = init
    runtime_cls.create = create
    runtime_cls.save = save
    runtime_cls.load = load
    runtime_cls._jj_state_resilience_installed = True


__all__ = [
    "KEEP_PER_EVENT",
    "backup_state",
    "ensure_schema",
    "install",
    "restore_latest",
]
