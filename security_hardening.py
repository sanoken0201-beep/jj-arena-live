from __future__ import annotations

import os
import threading
import time
from collections import defaultdict

from fastapi import Depends, HTTPException, Request, Response


CHANGE_PIN_WINDOW_SECONDS = 10 * 60
CHANGE_PIN_MAX_FAILURES = 5
_change_pin_lock = threading.Lock()
_change_pin_failures: dict[tuple[int, str], list[float]] = defaultdict(list)


def _client_host(request: Request) -> str:
    return str(request.client.host if request.client else "unknown")


def _change_pin_key(request: Request, user_id: int) -> tuple[int, str]:
    return int(user_id), _client_host(request)


def _check_change_pin_limit(key: tuple[int, str]) -> None:
    now = time.monotonic()
    cutoff = now - CHANGE_PIN_WINDOW_SECONDS
    with _change_pin_lock:
        recent = [stamp for stamp in _change_pin_failures.get(key, []) if stamp >= cutoff]
        _change_pin_failures[key] = recent
        if len(recent) >= CHANGE_PIN_MAX_FAILURES:
            raise HTTPException(429, "PIN変更の確認試行が多すぎます。10分ほど時間をおいてください")


def _record_change_pin_failure(key: tuple[int, str]) -> None:
    with _change_pin_lock:
        _change_pin_failures[key].append(time.monotonic())


def _clear_change_pin_failures(key: tuple[int, str]) -> None:
    with _change_pin_lock:
        _change_pin_failures.pop(key, None)


def _remove_http_route(app, path: str, method: str) -> None:
    method = method.upper()
    app.router.routes[:] = [
        route
        for route in app.router.routes
        if not (
            getattr(route, "path", None) == path
            and method in (getattr(route, "methods", None) or set())
        )
    ]


def install(app, server, db) -> None:
    """Apply auth/security hardening without changing the materialized core files.

    This extension is shared by both materialized and legacy entrypoints so the
    rollback path keeps the same security boundary.
    """
    if getattr(app.state, "jj_security_hardening_installed", False):
        return
    app.state.jj_security_hardening_installed = True

    # Production sessions must use the __Host- cookie. The old unprefixed cookie
    # remains available only in local/non-Render compatibility environments.
    def hardened_request_token(request, authorization: str | None = None) -> str | None:
        auth = server.bearer(authorization)
        if auth:
            return auth
        primary = request.cookies.get(server.SESSION_COOKIE)
        if primary:
            return primary
        if not os.getenv("RENDER") and server.LEGACY_SESSION_COOKIE != server.SESSION_COOKIE:
            return request.cookies.get(server.LEGACY_SESSION_COOKIE)
        return None

    server.request_token = hardened_request_token

    # Fetch Metadata is an additional CSRF boundary. It protects unsafe cookie
    # requests even when a browser omits Origin for an unusual navigation path.
    @app.middleware("http")
    async def jj_fetch_metadata_guard(request: Request, call_next):
        if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            if str(request.headers.get("sec-fetch-site") or "").lower() == "cross-site":
                return Response(status_code=403, content="cross-site request blocked")
        return await call_next(request)

    # Replace the original PIN-change endpoint. A valid authenticated session is
    # not sufficient reason to permit unlimited guesses of the current 6-digit PIN.
    _remove_http_route(app, "/api/auth/change-pin", "POST")
    change_pin_model = server.ChangePinIn

    async def hardened_change_pin(
        payload,
        request: Request,
        user=Depends(server.current_user),
    ):
        current_pin = server.validate_pin(payload.current_pin)
        new_pin = server.validate_pin(payload.new_pin)
        if current_pin == new_pin:
            raise HTTPException(400, "現在と異なる暗証番号を設定してください")

        key = _change_pin_key(request, int(user["id"]))
        _check_change_pin_limit(key)
        with db.connect() as con:
            row = con.execute(
                "SELECT password_hash FROM users WHERE id=?",
                (user["id"],),
            ).fetchone()
            if not row or not db.verify_password(current_pin, row["password_hash"]):
                _record_change_pin_failure(key)
                raise HTTPException(400, "現在の暗証番号が違います")
            con.execute(
                "UPDATE users SET password_hash=? WHERE id=?",
                (db.hash_password(new_pin), user["id"]),
            )

        _clear_change_pin_failures(key)
        db.delete_user_sessions(user["id"], keep_token=server.request_token(request))
        return {"ok": True}

    # Assign the concrete model after definition so FastAPI does not have to
    # resolve a dynamically supplied module through postponed annotations.
    hardened_change_pin.__annotations__["payload"] = change_pin_model
    app.post("/api/auth/change-pin")(hardened_change_pin)
