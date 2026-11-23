"""Explicit login and account-creation endpoints for the JJ Arena sign-in page.

The canonical /api/auth/pin endpoint is retained for old clients; its wrapped
name collision / ban / PIN protections are reused for registrations. The new
UI uses /api/auth/pin-login so entering an unknown name never creates a user.
"""
from fastapi import HTTPException
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import Response


class RegistrationIn(BaseModel):
    name: str = Field(min_length=1, max_length=30)
    pin: str = Field(min_length=6, max_length=6)
    confirm_pin: str = Field(min_length=6, max_length=6)


def install(app, server, db) -> None:
    if getattr(app.state, "jj_explicit_registration_installed", False):
        return

    pin_route = next((
        route for route in app.router.routes
        if getattr(route, "path", None) == "/api/auth/pin"
        and "POST" in (getattr(route, "methods", None) or set())
    ), None)
    if not pin_route or not getattr(pin_route, "dependant", None):
        raise RuntimeError("explicit registration requires canonical PIN route")

    def guarded_pin(payload, response, request):
        # Always retrieve the *current* wrapped handler: name collisions,
        # permanent bans, and security checks remain authoritative.
        return pin_route.dependant.call(
            payload=payload, response=response, request=request
        )

    @app.post("/api/auth/pin-login")
    def login_only(
        payload: server.PinAccess, response: Response, request: Request
    ):
        name = server.normalize_login_name(payload.name)
        server.validate_pin(payload.pin)
        login_id = server.internal_login_id(name)
        with db.connect() as con:
            exists = con.execute(
                "SELECT id FROM users WHERE email=? AND deleted_at IS NULL",
                (login_id,),
            ).fetchone()
        if not exists:
            # Unknown names count against the same per-identity rate limit.
            key = server._check_login_rate(request, login_id)
            server._record_login_failure(key)
            raise HTTPException(401, "名前または暗証番号が違います")
        result = guarded_pin(payload, response, request)
        if result.get("created"):
            # Fail closed if a concurrent deletion occurred after the lookup.
            raise HTTPException(409, "アカウントの状態が変わりました。もう一度お試しください")
        return {**result, "created": False}

    @app.post("/api/auth/register")
    def register_account(
        payload: RegistrationIn, response: Response, request: Request
    ):
        name = server.normalize_login_name(payload.name)
        pin = server.validate_pin(payload.pin)
        confirm_pin = server.validate_pin(payload.confirm_pin)
        if pin != confirm_pin:
            raise HTTPException(400, "確認用PINが一致しません")

        login_id = server.internal_login_id(name)
        with db.connect() as con:
            present = con.execute(
                "SELECT id FROM users WHERE email=?",
                (login_id,),
            ).fetchone()
        if present:
            raise HTTPException(409, "この名前は既に登録されています。ログインしてください")

        # Delegate account creation to the existing, serialized, rate-limited,
        # permanent-ban guarded handler. Do not bypass any protection.
        result = guarded_pin(
            server.PinAccess(name=payload.name, pin=pin), response, request
        )
        if not result.get("created"):
            # A parallel registration may have won the race.
            raise HTTPException(409, "この名前は既に登録されています。ログインしてください")
        return result

    app.state.jj_explicit_registration_installed = True


__all__ = ["RegistrationIn", "install"]
