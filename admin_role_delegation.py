"""Audited, PIN-confirmed administrator handover for the canonical admin console."""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Literal

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field

# Do not place PINs in log messages, audit details or response bodies.
WINDOW_SECONDS = 600
MAX_FAILURES = 5
_attempt_lock = threading.Lock()
_failed_attempts: dict[int, list[float]] = defaultdict(list)
_PG_LOCK_KEY = 2026101001


class RoleChangeIn(BaseModel):
    role: Literal["admin", "member"]
    current_pin: str = Field(pattern=r"^[0-9]{6}$", min_length=6, max_length=6)


def _check_pin_limit(actor_id: int) -> None:
    with _attempt_lock:
        cutoff = time.monotonic() - WINDOW_SECONDS
        history = [stamp for stamp in _failed_attempts[actor_id] if stamp >= cutoff]
        _failed_attempts[actor_id] = history
        if len(history) >= MAX_FAILURES:
            raise HTTPException(429, "PIN確認の失敗が多すぎます。10分後に再試行してください")


def _record_failed_pin(actor_id: int) -> None:
    with _attempt_lock:
        _failed_attempts[actor_id].append(time.monotonic())


def _clear_failed_pin(actor_id: int) -> None:
    with _attempt_lock:
        _failed_attempts.pop(actor_id, None)


def install(app, server, db, admin_console) -> None:
    if getattr(app.state, "jj_admin_role_delegation_installed", False):
        return
    app.state.jj_admin_role_delegation_installed = True

    @app.post("/api/admin/console/users/{uid}/role")
    def change_role(
        uid: int,
        payload: RoleChangeIn,
        request: Request,
        actor=Depends(server.admin_user),
    ):
        actor_id = int(actor["id"])
        _check_pin_limit(actor_id)

        # All role changes use one serialized, committed transaction. This
        # makes the last-admin check safe even for concurrent administrator
        # requests and ensures audit/session revocation cannot be lost.
        with db.connect() as con:
            if getattr(db, "IS_POSTGRES", False):
                con.execute("SELECT pg_advisory_xact_lock(?)", (_PG_LOCK_KEY,))
            else:
                con.execute("BEGIN IMMEDIATE")

            operator = con.execute(
                "SELECT role,password_hash,disabled,deleted_at FROM users WHERE id=?",
                (actor_id,),
            ).fetchone()
            if (not operator or operator["role"] != "admin"
                    or int(operator["disabled"] or 0) or operator["deleted_at"]):
                raise HTTPException(403, "管理者権限がありません")

            if not db.verify_password(payload.current_pin, operator["password_hash"]):
                _record_failed_pin(actor_id)
                raise HTTPException(403, "管理者PINが正しくありません")
            _clear_failed_pin(actor_id)

            target = con.execute(
                "SELECT id,name,role,disabled,deleted_at,approved,club_verified "
                "FROM users WHERE id=?",
                (uid,),
            ).fetchone()
            if target is None:
                raise HTTPException(404, "対象アカウントがありません")
            if (int(target["disabled"] or 0) or target["deleted_at"]
                    or not int(target["approved"] or 0)):
                raise HTTPException(409, "停止・削除・未承認のアカウントは権限変更できません")

            existing = str(target["role"])
            if existing == payload.role:
                return {"ok": True, "changed": False, "user_id": uid, "role": existing}

            if uid == actor_id:
                raise HTTPException(409, "自分自身の管理者権限は解除できません")
            if payload.role == "admin" and not int(target["club_verified"] or 0):
                raise HTTPException(409, "先にJJメンバーの本人確認を完了してください")

            if existing == "admin" and payload.role == "member":
                active = con.execute(
                    "SELECT COUNT(*) AS n FROM users WHERE role='admin' "
                    "AND COALESCE(disabled,0)=0 AND deleted_at IS NULL"
                ).fetchone()
                if int(active["n"]) <= 1:
                    raise HTTPException(409, "最後の管理者は解除できません")

            con.execute(
                "UPDATE users SET role=? WHERE id=? AND role=?",
                (payload.role, uid, existing),
            )
            # Invalidate every session belonging to the changed account,
            # including a member session that predated elevation.
            con.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
            admin_console._audit(
                db,
                actor_id,
                "user.role_change",
                uid,
                con=con,
                before_role=existing,
                after_role=payload.role,
                changed={"role": f"{existing} → {payload.role}"},
            )
        return {"ok": True, "changed": True, "user_id": uid, "role": payload.role}
