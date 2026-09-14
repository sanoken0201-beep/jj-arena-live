from __future__ import annotations

from pathlib import Path

import app

from player_ux_phase6 import PHASE6_MARKER
from served_assets import ASSET_VERSION, build_index, build_service_worker


ROOT = Path(__file__).resolve().parent


def main() -> None:
    js = app._patched_app_js()
    assert PHASE6_MARKER in js

    start = js.index("const jjV6Telemetry=")
    end = js.index("renderActionBar=function(){", start)
    telemetry = js[start:end]
    for forbidden in ("me.id", "me?.id", "me.name", "me?.name", "user_id", "hand_id", "table_id", "cards", "chat", "userAgent", "amount"):
        assert forbidden not in telemetry, f"identity/game payload leaked into telemetry helper: {forbidden}"
    assert "event:String(event),detail:String(detail),device:jjV6Device()" in telemetry
    assert "duration_ms" in telemetry
    assert "fetch('/api/ux-telemetry'" in telemetry
    assert "keepalive:true" in telemetry

    assert "jjV6SyncDecision(l);" in js
    assert "e.isTrusted&&action" in js, "programmatic CHECK pre-action clicks must not skew manual latency"
    assert "jjV6FinishDecision(action.dataset.action)" in js
    assert "jjV6Timeout(timeoutAction)" in js
    assert "jjV6ConnectionClosed();" in js
    assert "jjV6ConnectionOpen();" in js
    assert "jjV6Emit('sizing','slider')" in js
    assert "jjV6Emit('preaction','check')" in js
    assert "check_fold" not in js
    assert "jjV6Emit('ui','settings')" in js
    assert "jjV6Emit('ui',side.dataset.jjMobileSide==='log'?'history':'chat')" in js

    # v67 performance behavior remains in the final compiled client before telemetry.
    assert "m.type==='chat'" in js and "renderTableChat()" in js
    assert "refreshMe().catch(()=>{})" not in js[js.index("tableWS.onmessage=e=>"):js.index("tableWS.onclose=", js.index("tableWS.onmessage=e=>"))]

    compiler = (ROOT / "served_assets.py").read_text(encoding="utf-8")
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "transform_phase6_app_js(js)" in compiler
    assert "encoded_asset(body)" in app_source, "v67 lossless asset transfer must be preserved"
    assert "transform_phase6_app_js" not in app_source, "production runtime must not run phase 6 transform"
    assert ASSET_VERSION == 70
    index = build_index()
    worker = build_service_worker()
    assert f"/static/app.js?v={ASSET_VERSION}" in index
    assert f"/static/styles.css?v={ASSET_VERSION}" in index
    assert f"jj-arena-live-v{ASSET_VERSION}" in worker

    materialized = (ROOT / "app_materialized.py").read_text(encoding="utf-8")
    assert "import ux_telemetry" in materialized
    assert "ux_telemetry.install(app, runtime_server, db)" in materialized
    assert "_CORE_ROUTE_IDS" in materialized
    assert "_prioritize_extension_routes" in materialized
    route_paths = [str(getattr(route, "path", "") or "") for route in app.app.router.routes]
    telemetry_index = route_paths.index("/api/ux-telemetry")
    spa_index = route_paths.index("/{path:path}")
    assert telemetry_index < spa_index, "telemetry endpoint is shadowed by SPA catch-all"
    assert "runtime_performance.install(db, runtime_server, runtime_poker_engine)" in materialized

    admin_patch = (ROOT / "admin_copy_patch.py").read_text(encoding="utf-8")
    assert 'ADMIN_ASSET_VERSION = "123"' in admin_patch
    assert "ux_telemetry.css" in admin_patch and "ux_telemetry.js" in admin_patch

    admin_js = (ROOT / "admin_static" / "ux_telemetry.js").read_text(encoding="utf-8")
    assert "/api/admin/console/ux-telemetry?days=" in admin_js
    assert "ユーザーID・名前・ハンドID・カード・ベット額・チャット・自由入力文は保存しません" in admin_js
    assert "手動アクション選択" in admin_js

    print("JJ_PLAYER_UX_PHASE6_OK")


if __name__ == "__main__":
    main()
