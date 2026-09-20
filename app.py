"""Production entrypoint for JJ Arena Live after the v2 core materialization cutover.

Render continues to start ``app:app``. This shim delegates to the committed,
verified materialized v1.24.4 implementation and serves browser assets compiled
during the build step. Production therefore rebuilds neither the historical
patch chain nor the UX asset-transform chain at process startup.

The former reconstructed startup path remains in ``app_legacy.py`` as the
parity oracle and rollback reference.
"""
from __future__ import annotations

import inspect
from functools import lru_cache

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import Response

from asset_encoding import accepts_gzip, encoded_asset, matches_etag
import app_materialized as _materialized
from app_materialized import app, db, runtime_poker_engine, runtime_server
from player_ux_phase2 import leave_after_hand_transition
import sitngo
import sitngo_admin_config
import sitngo_asset_cache
import sitngo_chip_rules
import sitngo_runtime
import sitngo_tournament_rules
import sitngo_process_guard
import sitngo_resilience
import read_efficiency

# Configure the root-level Sit&Go extension before browser transforms bind the
# Sit&Go UI functions and before the service installs its FastAPI routes. The
# tournament rules must wrap the isolated engine first; denomination/chip rules
# then wrap that tournament hand starter without touching the ring engine.
sitngo_process_guard.require_single_worker()
sitngo_admin_config.install(sitngo)
sitngo_tournament_rules.install(sitngo_runtime)
sitngo_chip_rules.install(sitngo_runtime)
sitngo_asset_cache.install()
sitngo_resilience.install(sitngo_runtime)

from served_assets import (
    ASSET_VERSION,
    CLEAR_COPY_MARKER,
    HAND_HISTORY_VISIBILITY_MARKER,
    PHASE2_MARKER,
    PHASE3_MARKER,
    PHASE4_MARKER,
    PHASE5_MARKER,
    PHASE5_MOBILE_MARKER,
    PHASE6_MARKER,
    PLAYER_UX_MARKER,
    ensure_runtime_assets,
)


_BUILT_ASSETS = ensure_runtime_assets()


@lru_cache(maxsize=4)
def _built_asset(relative: str) -> str:
    return (_BUILT_ASSETS / relative).read_text(encoding="utf-8")


# Compatibility names retained for existing regression tests and diagnostics.
# Every browser mutation, including historical rake-copy cleanup, cache query
# selection and obsolete poker-control removal, is compiled into `.jj_build`.
# Runtime only reads validated canonical output.
def _patched_index() -> str:
    return _built_asset("index.html")


def _patched_app_js() -> str:
    return _built_asset("static/app.js")


def _patched_styles() -> str:
    return _built_asset("static/styles.css")


def _patched_service_worker() -> str:
    return _built_asset("static/sw.js")


@app.middleware("http")
async def _v2_asset_hotfix(request: Request, call_next):
    """Serve canonical build-time compiled UX assets.

    `materialized_v1244` remains immutable for parity/reproducibility. The
    historical UX transforms run only in `build_served_assets.py`; production
    reads validated output and performs only transport concerns (ETag/gzip).
    """
    if request.method in {"GET", "HEAD"}:
        path = request.url.path
        body: str | None = None
        media_type: str | None = None
        headers: dict[str, str] = {}
        if path in {"/", "/index.html"}:
            body = _patched_index()
            media_type = "text/html"
            headers["Cache-Control"] = "no-cache, max-age=0"
        elif path == "/static/app.js":
            body = _patched_app_js()
            media_type = "application/javascript"
            headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif path == "/static/styles.css":
            body = _patched_styles()
            media_type = "text/css"
            headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif path == "/static/sw.js":
            body = _patched_service_worker()
            media_type = "application/javascript"
            headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            headers["Service-Worker-Allowed"] = "/"
        if body is not None:
            if path in {"/static/app.js", "/static/styles.css"}:
                plain, compressed, etag = encoded_asset(body)
                headers["Vary"] = "Accept-Encoding"
                headers["ETag"] = etag
                if matches_etag(request.headers.get("if-none-match", ""), etag):
                    return Response(status_code=304, headers=headers)
                if accepts_gzip(request.headers.get("accept-encoding", "")) and len(compressed) < len(plain):
                    encoded = compressed
                    headers["Content-Encoding"] = "gzip"
                else:
                    encoded = plain
            else:
                encoded = body.encode("utf-8")
            content = b"" if request.method == "HEAD" else encoded
            headers["Content-Length"] = str(len(encoded))
            return Response(content=content, media_type=media_type, headers=headers)
    return await call_next(request)


class _LeaveAfterHandIn(BaseModel):
    enabled: bool = True


def _action_timeout_seconds() -> int:
    """Read the actual server deadline default instead of duplicating 45 in UI."""
    try:
        default = inspect.signature(runtime_server.arm_action_deadline).parameters["seconds"].default
        return max(1, int(default))
    except Exception:
        return 45


@app.post("/api/poker-config")
def _poker_config(user=Depends(runtime_server.current_user)):
    return {
        "action_timeout_seconds": _action_timeout_seconds(),
        "ranking_points_per_bb": 3,
        "rake_percent": 5,
        "rake_cap_bb": 3,
    }


@app.post("/api/tables/{table_id}/leave-after-hand")
async def _leave_after_hand(
    table_id: str,
    payload: _LeaveAfterHandIn,
    user=Depends(runtime_server.current_user),
):
    async with runtime_server.get_table_lock(table_id):
        state = runtime_server.load_table(table_id)
        status = leave_after_hand_transition(state, int(user["id"]), bool(payload.enabled))
        if status == "leave_now":
            try:
                runtime_poker_engine.remove_player(state, int(user["id"]))
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            runtime_server.table_presence.pop((table_id, int(user["id"])), None)
            status = "left"
        runtime_server.save_table(state)
        public = runtime_poker_engine.public_state(state, int(user["id"]))
    await runtime_server.hub.broadcast(table_id)
    return {"ok": True, "status": status, "state": public}


@app.get("/api/tables", include_in_schema=False)
def _single_public_table_list(user=Depends(runtime_server.current_user)):
    """Expose exactly one ring table to players, including stale cached clients.

    The immutable materialized core retains both historical fixed tables for
    rollback/data compatibility. The public contract is narrower and returns
    only the first canonical table.
    """
    tables = runtime_server.tables(user)
    return tables[:1]


def _prioritize_single_public_table_route() -> None:
    """Put the one-table route ahead of the canonical two-table route.

    FastAPI resolves duplicate method/path routes by registration order. The
    materialized core registered its historical GET /api/tables route long
    before this integration shim, so merely registering a replacement route is
    insufficient. Move this exact APIRoute ahead of every other matching GET
    route and assert the invariant at startup.
    """
    routes = list(app.router.routes)
    replacement = next(
        (route for route in routes if getattr(route, "endpoint", None) is _single_public_table_list),
        None,
    )
    if replacement is None:
        raise RuntimeError("single public table route is missing")

    routes.remove(replacement)
    matching_indexes = [
        index
        for index, route in enumerate(routes)
        if getattr(route, "path", None) == "/api/tables"
        and "GET" in (getattr(route, "methods", None) or set())
    ]
    if not matching_indexes:
        raise RuntimeError("canonical GET /api/tables route is missing")

    routes.insert(min(matching_indexes), replacement)
    app.router.routes[:] = routes

    first_match = next(
        route
        for route in app.router.routes
        if getattr(route, "path", None) == "/api/tables"
        and "GET" in (getattr(route, "methods", None) or set())
    )
    if getattr(first_match, "endpoint", None) is not _single_public_table_list:
        raise RuntimeError("single public table route precedence was not established")


# Sit&Go is a root-level integration layer. The immutable v1.24.4 ring core is
# intentionally left unchanged; scheduling/registration state lives in its own
# tables and its own lifecycle task.
_sitngo_service = sitngo.install(app, db, runtime_server)

# First repair all late extension routes around the SPA fallback, then establish
# the stricter duplicate-route ordering required for GET /api/tables.
_materialized._prioritize_extension_routes(app, _materialized._CORE_ROUTE_IDS)
_prioritize_single_public_table_route()
read_efficiency.install(
    app,
    runtime_server,
    db,
    public_table_limit=1,
)
_materialized._prioritize_extension_routes(app, _materialized._CORE_ROUTE_IDS)


__all__ = [
    "app",
    "db",
    "runtime_poker_engine",
    "runtime_server",
    "HAND_HISTORY_VISIBILITY_MARKER",
    "PLAYER_UX_MARKER",
    "CLEAR_COPY_MARKER",
    "PHASE2_MARKER",
    "PHASE3_MARKER",
    "PHASE4_MARKER",
    "PHASE5_MARKER",
    "PHASE5_MOBILE_MARKER",
    "PHASE6_MARKER",
    "ASSET_VERSION",
]


def __getattr__(name: str):
    """Forward legacy module-level attributes to the canonical implementation.

    The old production ``app.py`` exposed imported extension modules and
    ``DEST`` as incidental module attributes. Keeping read-only forwarding here
    avoids breaking diagnostics/tests that inspect those attributes while the
    stable ASGI surface remains the explicit exports above.
    """
    return getattr(_materialized, name)
