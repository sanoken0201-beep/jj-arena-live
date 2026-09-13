from __future__ import annotations

from pathlib import Path

from player_ux_asset_transform import transform_app_js as phase1
from player_ux_phase2 import transform_app_js as phase2
from player_ux_phase3 import transform_app_js as phase3
from player_ux_phase4 import transform_app_js as phase4
from player_ux_phase5 import transform_app_js as phase5
from player_ux_phase6 import PHASE6_MARKER, transform_app_js as phase6


ROOT = Path(__file__).resolve().parent


def main() -> None:
    source = (ROOT / "materialized_v1244" / "static" / "app.js").read_text(encoding="utf-8")
    js = phase6(phase5(phase4(phase3(phase2(phase1(source))))))
    assert PHASE6_MARKER in js
    assert phase6(js) == js

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
    assert "jjV6FinishDecision(action.dataset.action)" in js
    assert "jjV6Timeout(timeoutAction)" in js
    assert "jjV6ConnectionClosed();" in js
    assert "jjV6ConnectionOpen();" in js
    assert "jjV6Emit('sizing','slider')" in js
    assert "jjV6Emit('preaction',pre.dataset.jjPreaction)" in js
    assert "jjV6Emit('ui','settings')" in js
    assert "jjV6Emit('ui',side.dataset.jjMobileSide==='log'?'history':'chat')" in js

    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "transform_phase6_app_js(transform_phase5_app_js(" in app_source
    assert "/static/app.js?v=63" in app_source
    assert "/static/styles.css?v=63" in app_source
    assert "jj-arena-live-v63" in app_source

    materialized = (ROOT / "app_materialized.py").read_text(encoding="utf-8")
    assert "import ux_telemetry" in materialized
    assert "ux_telemetry.install(app, runtime_server, db)" in materialized
    assert '"/api/ux-telemetry"' in materialized

    admin_patch = (ROOT / "admin_copy_patch.py").read_text(encoding="utf-8")
    assert 'ADMIN_ASSET_VERSION = "122"' in admin_patch
    assert "ux_telemetry.css" in admin_patch and "ux_telemetry.js" in admin_patch

    admin_js = (ROOT / "admin_static" / "ux_telemetry.js").read_text(encoding="utf-8")
    assert "/api/admin/console/ux-telemetry?days=" in admin_js
    assert "ユーザーID・名前・ハンドID・カード・ベット額・チャット・自由入力文は保存しません" in admin_js

    print("JJ_PLAYER_UX_PHASE6_OK")


if __name__ == "__main__":
    main()
