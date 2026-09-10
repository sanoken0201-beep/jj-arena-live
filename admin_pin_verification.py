from __future__ import annotations

import re
import threading
import time
from collections import defaultdict

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field


VERIFY_WINDOW_SECONDS = 10 * 60
VERIFY_MAX_ATTEMPTS = 5
_attempt_lock = threading.Lock()
_attempts: dict[tuple[int, int], list[float]] = defaultdict(list)


class AdminPinVerify(BaseModel):
    pin: str = Field(min_length=6, max_length=6)


def _check_attempt_limit(actor_id: int, target_id: int) -> tuple[int, int]:
    """Limit candidate-PIN checks so the admin endpoint cannot become a PIN oracle."""
    key = (int(actor_id), int(target_id))
    now = time.monotonic()
    cutoff = now - VERIFY_WINDOW_SECONDS
    with _attempt_lock:
        recent = [stamp for stamp in _attempts.get(key, []) if stamp >= cutoff]
        _attempts[key] = recent
        if len(recent) >= VERIFY_MAX_ATTEMPTS:
            raise HTTPException(429, "PIN確認の試行が多すぎます。10分ほど時間をおいてください")
        return key


def _record_attempt(key: tuple[int, int], *, matched: bool) -> None:
    now = time.monotonic()
    with _attempt_lock:
        if matched:
            _attempts.pop(key, None)
        else:
            _attempts[key].append(now)


def install(app, admin_console) -> None:
    if getattr(app.state, "jj_admin_pin_verification_installed", False):
        return
    app.state.jj_admin_pin_verification_installed = True

    import db
    import server

    @app.post("/api/admin/console/users/{uid}/verify-pin")
    def verify_pin(uid: int, payload: AdminPinVerify, user=Depends(server.admin_user)):
        pin = (payload.pin or "").strip()
        if not re.fullmatch(r"\d{6}", pin):
            raise HTTPException(400, "PINは6桁の数字です")

        actor_id = int(user["id"])
        target_id = int(uid)
        key = _check_attempt_limit(actor_id, target_id)

        with db.connect() as con:
            cols = admin_console._cols(db, con, "users")
            selected = ["id", "password_hash"]
            if "deleted_at" in cols:
                selected.append("deleted_at")
            row = con.execute(
                f"SELECT {','.join(selected)} FROM users WHERE id=?",
                (target_id,),
            ).fetchone()

        if not row:
            raise HTTPException(404, "user not found")
        rowd = dict(row)
        if rowd.get("deleted_at"):
            raise HTTPException(404, "user not found")

        matched = bool(db.verify_password(pin, rowd.get("password_hash")))
        _record_attempt(key, matched=matched)

        # Never place the candidate PIN or password hash in the audit trail.
        admin_console._audit(
            db,
            actor_id,
            "user.pin_verify",
            target_id,
            result="match" if matched else "no_match",
        )
        return {"ok": True, "matches": matched}
