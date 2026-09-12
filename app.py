"""Production entrypoint for JJ Arena Live after the v2 core materialization cutover.

Render continues to start ``app:app``. This shim delegates to the committed,
verified materialized v1.24.4 implementation so production no longer rebuilds
the historical patch chain on every process start.

The former reconstructed startup path remains in ``app_legacy.py`` as the
parity oracle and rollback reference.
"""
from __future__ import annotations

import inspect
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import Response

import app_materialized as _materialized
from app_materialized import app, db, runtime_poker_engine, runtime_server
from hand_history_visibility import (
    HAND_HISTORY_VISIBILITY_MARKER,
    transform_app_js as transform_hand_history_app_js,
    transform_styles as transform_hand_history_styles,
)
from player_ux_asset_transform import PLAYER_UX_MARKER, transform_app_js
from player_ux_clear_copy import (
    CLEAR_COPY_MARKER,
    transform_app_js as transform_clear_copy_app_js,
    transform_styles as transform_clear_copy_styles,
)
from player_ux_phase2 import (
    PHASE2_MARKER,
    leave_after_hand_transition,
    transform_app_js as transform_phase2_app_js,
    transform_styles as transform_phase2_styles,
)
from player_ux_phase3 import (
    PHASE3_MARKER,
    transform_app_js as transform_phase3_app_js,
    transform_styles as transform_phase3_styles,
)
from player_ux_phase4 import (
    PHASE4_MARKER,
    transform_app_js as transform_phase4_app_js,
    transform_styles as transform_phase4_styles,
)
from player_ux_phase5 import (
    PHASE5_MARKER,
    transform_app_js as transform_phase5_app_js,
    transform_styles as transform_phase5_styles,
)
from player_ux_phase5_mobile import (
    PHASE5_MOBILE_MARKER,
    transform_styles as transform_phase5_mobile_styles,
)


_ROOT = Path(__file__).resolve().parent
_MATERIALIZED_STATIC = _ROOT / "materialized_v1244" / "static"
_TODAYS_JJ_MARKER = "v2 today's-jj contrast hardening 2026-09-12"
_TODAYS_JJ_CSS = r'''

/* v2 today's-jj contrast hardening 2026-09-12
   These rules intentionally target the cards themselves, not only their parent
   learning shell. The home layout has changed several times and the text must
   remain readable even if a card is moved to another container. */
.jj-study-card,
.jj-video-card{
  color:#f4f8f6!important;
  -webkit-text-fill-color:currentColor;
}
.jj-study-card:link,
.jj-study-card:visited,
.jj-video-card:link,
.jj-video-card:visited{
  color:#f4f8f6!important;
  -webkit-text-fill-color:#f4f8f6!important;
}
.jj-study-card h3,
.jj-video-card h3{
  color:#ffffff!important;
  -webkit-text-fill-color:#ffffff!important;
  opacity:1!important;
  text-shadow:0 1px 2px rgba(0,0,0,.32)!important;
}
.jj-study-card p,
.jj-video-card p{
  color:#d7e2dc!important;
  -webkit-text-fill-color:#d7e2dc!important;
  opacity:1!important;
}
.jj-study-meta,
.jj-study-meta>span:not(.jj-study-source){
  color:#c4d0ca!important;
  -webkit-text-fill-color:#c4d0ca!important;
  opacity:1!important;
}
.jj-study-source,
.jj-video-kind{
  color:#a8ebcb!important;
  -webkit-text-fill-color:#a8ebcb!important;
  opacity:1!important;
}
.jj-video-kind.is-motivation{
  color:#f6dc8d!important;
  -webkit-text-fill-color:#f6dc8d!important;
}
.jj-study-card footer,
.jj-video-card footer,
.jj-study-card footer>span,
.jj-video-card footer>span{
  color:#c4d0ca!important;
  -webkit-text-fill-color:#c4d0ca!important;
  opacity:1!important;
}
.jj-study-card footer b,
.jj-video-card footer b{
  color:#ffe08a!important;
  -webkit-text-fill-color:#ffe08a!important;
  opacity:1!important;
}
@media(max-width:760px){
  .jj-study-card h3,.jj-video-card h3{
    font-size:.92rem!important;
    line-height:1.52!important;
    font-weight:800!important;
  }
  .jj-study-meta{font-size:.68rem!important}
  .jj-study-card footer,.jj-video-card footer{font-size:.7rem!important}
}
'''


@lru_cache(maxsize=1)
def _patched_index() -> str:
    html = (_MATERIALIZED_STATIC / "index.html").read_text(encoding="utf-8")
    html = html.replace('/static/styles.css?v=56', '/static/styles.css?v=66')
    html = html.replace('/static/app.js?v=56', '/static/app.js?v=66')
    html = html.replace('← Lobby', '← ロビー')
    html = html.replace('>Table Chat<', '>チャット<').replace('>Hand Log<', '>ハンド履歴<')
    html = html.replace('Waiting for players', '着席者を待っています')
    html = html.replace(
        'JJ内の練習用プレイマネーテーブルです。A/Bの2卓のみ、6-max、0.5/1bb、着席時150bb固定。各ハンドは10% rake・5bb capで、結果は1bb=3ptとして後期ランキングへ自動反映されます。テーブル画面との接続・操作が15分ない場合、ハンド終了後に自動離席します。',
        'プレイマネー｜6-max｜0.5/1bb｜150bb固定｜rake 10%・5bb cap｜ランキング 1bb=3pt｜15分無操作でハンド終了後に自動離席',
    )
    return html


@lru_cache(maxsize=1)
def _patched_app_js() -> str:
    js = (_MATERIALIZED_STATIC / "app.js").read_text(encoding="utf-8")
    js = transform_hand_history_app_js(js)
    js = transform_phase5_app_js(transform_phase4_app_js(transform_phase3_app_js(transform_phase2_app_js(transform_app_js(js)))))
    js = transform_clear_copy_app_js(js)

    # The Phase 2 connection layer is the authoritative WebSocket handler after
    # all UX transforms. Patch that exact final implementation so state frames
    # keep connection-freshness semantics while chat-only frames avoid a full
    # table rerender. State frames may omit chat after the first compatible frame.
    ws_handler = "tableWS.onmessage=e=>{try{const m=JSON.parse(e.data);if(m.type==='state'){const previous=tableState;tableState=m.state;tableMessages=m.messages||[];renderPokerRoom();jjV2AcceptState('ws',previous);refreshMe().catch(()=>{})}}catch{}};"
    ws_handler_optimized = "tableWS.onmessage=e=>{try{const m=JSON.parse(e.data);if(m.type==='state'){const previous=tableState;tableState=m.state;if(Array.isArray(m.messages))tableMessages=m.messages;renderPokerRoom();jjV2AcceptState('ws',previous)}else if(m.type==='chat'){tableMessages=m.messages||[];renderTableChat()}}catch{}};"
    if js.count(ws_handler) != 1:
        raise RuntimeError("production websocket handler drift: expected one Phase 2 state handler")
    js = js.replace(ws_handler, ws_handler_optimized, 1)

    # Keep the historical exact replacement as a compatibility guard for any
    # remaining pre-Phase-2 renderer copy; it does not alter the authoritative
    # handler patched above.
    js = js.replace(
        "renderPokerRoom();refreshMe().catch(()=>{})",
        "renderPokerRoom()",
    )

    # showApp() immediately calls switchView(currentView), which already loads
    # the visible view. The historical extra refreshAll() duplicated home API
    # calls on initial session restore and PIN login, so remove only that exact
    # redundant follow-up while preserving the same visible refresh.
    js = js.replace("showApp();await refreshAll()", "showApp()")
    return js


@lru_cache(maxsize=1)
def _patched_styles() -> str:
    css = (_MATERIALIZED_STATIC / "styles.css").read_text(encoding="utf-8")
    if _TODAYS_JJ_MARKER not in css:
        css = css.rstrip() + _TODAYS_JJ_CSS + "\n"
    css = transform_hand_history_styles(css)
    css = transform_phase5_mobile_styles(transform_phase5_styles(transform_phase4_styles(transform_phase3_styles(transform_phase2_styles(css)))))
    return transform_clear_copy_styles(css)


@lru_cache(maxsize=1)
def _patched_service_worker() -> str:
    worker = (_MATERIALIZED_STATIC / "sw.js").read_text(encoding="utf-8")
    worker = worker.replace("const CACHE='jj-arena-live-v56';", "const CACHE='jj-arena-live-v66';")
    worker = worker.replace("'/static/styles.css?v=19'", "'/static/styles.css?v=66'")
    worker = worker.replace("'/static/app.js?v=19'", "'/static/app.js?v=66'")
    return worker


@app.middleware("http")
async def _v2_asset_hotfix(request: Request, call_next):
    """Serve post-materialization UX fixes without mutating the canonical tree.

    The v2 cutover intentionally keeps ``materialized_v1244`` immutable for
    parity/reproducibility. The served app source is transformed at the exact
    implementation sites, rather than defining another browser-side renderer
    layer. Versioned asset URLs and a new service-worker namespace prevent stale
    clients from mixing the old and new poker controls.
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


# These are POST routes because the materialized SPA catch-all GET route is
# registered before this integration shim. POST keeps the routes unambiguous.
@app.post("/api/poker-config")
def _poker_config(user=Depends(runtime_server.current_user)):
    return {
        "action_timeout_seconds": _action_timeout_seconds(),
        "ranking_points_per_bb": 3,
        "rake_percent": 10,
        "rake_cap_bb": 5,
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
]


def __getattr__(name: str):
    """Forward legacy module-level attributes to the canonical implementation.

    The old production ``app.py`` exposed imported extension modules and
    ``DEST`` as incidental module attributes. Keeping read-only forwarding here
    avoids breaking diagnostics/tests that inspect those attributes while the
    stable ASGI surface remains the explicit exports above.
    """
    return getattr(_materialized, name)
