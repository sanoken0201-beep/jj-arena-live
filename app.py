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
_RAKE_JS_QUERY = "r=5-3"


@lru_cache(maxsize=4)
def _built_asset(relative: str) -> str:
    return (_BUILT_ASSETS / relative).read_text(encoding="utf-8")


# Compatibility names retained for existing regression tests and diagnostics.
# They read precompiled files; only the configured rake numbers are substituted.
def _patched_index() -> str:
    value = _built_asset("index.html")
    value = value.replace(
        f"/static/app.js?v={ASSET_VERSION}",
        f"/static/app.js?v={ASSET_VERSION}&{_RAKE_JS_QUERY}",
    )
    return value.replace("rake 10%・5bb cap", "rake 5%・3bb cap")


def _patched_app_js() -> str:
    value = _built_asset("static/app.js")
    value = value.replace(
        "RAKE 10% · ${fmt(t.rake_cap_bb)}bb CAP",
        "RAKE 5% · ${fmt(t.rake_cap_bb)}bb CAP",
    )
    value = value.replace("rake 10% / 5bb cap", "rake 5% / 3bb cap")
    value = value.replace(
        "pot*0.10,Number(tableState.rake_cap||500)",
        "pot*0.05,Number(tableState.rake_cap||300)",
    )
    return value


def _patched_styles() -> str:
    return _built_asset("static/styles.css")


def _patched_service_worker() -> str:
    return _built_asset("static/sw.js")


@app.middleware("http")
async def _v2_asset_hotfix(request: Request, call_next):
    """Serve build-time compiled UX assets without mutating the canonical core.

    `materialized_v1244` remains immutable for parity/reproducibility. The
    historical UX transforms run in `build_served_assets.py`; production only
    reads their validated output. Versioned asset URLs and the service-worker
    namespace prevent stale clients from mixing incompatible poker controls.
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


# app.py may add integration routes after app_materialized finished installing its
# extensions. Re-apply the identity-based ordering once so every non-core route,
# including future GET endpoints, stays ahead of the canonical SPA catch-all.
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
