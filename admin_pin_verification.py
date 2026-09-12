from __future__ import annotations

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field


class AdminPinVerify(BaseModel):
    """Compatibility request model for the retired PIN-verification endpoint."""

    pin: str = Field(min_length=6, max_length=6)


def install(app, admin_console) -> None:
    """Keep the old URL non-functional so stale admin clients fail safely.

    Administrators may reset a member PIN and revoke sessions, but must never be
    able to test guesses against another member's authentication secret.
    """
    if getattr(app.state, "jj_admin_pin_verification_installed", False):
        return
    app.state.jj_admin_pin_verification_installed = True

    import server

    @app.post("/api/admin/console/users/{uid}/verify-pin")
    def verify_pin(uid: int, payload: AdminPinVerify, user=Depends(server.admin_user)):
        del uid, payload, user
        raise HTTPException(
            410,
            "PIN照合機能はセキュリティ保護のため廃止されました。必要な場合はPINリセットを利用してください",
        )
