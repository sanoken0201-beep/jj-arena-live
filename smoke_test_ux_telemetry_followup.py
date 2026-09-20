from __future__ import annotations

from pathlib import Path

from browser_asset_pipeline import PIPELINE_VERSION, POST_BUILD_STAGES
from build_served_assets import main as build_assets
from served_assets import BUILD_ROOT, validate_built_assets
from ux_telemetry import EVENT_DETAILS
from ux_telemetry_followup import CACHE_QUERY, MARKER, transform_app_js

ROOT = Path(__file__).resolve().parent


def main() -> None:
    build_assets()
    manifest = validate_built_assets(BUILD_ROOT)
    stages = [name for name, _ in POST_BUILD_STAGES]

    assert PIPELINE_VERSION == 4
    assert manifest.get("pipeline_version") == 4
    assert stages[-2:] == ["runtime_browser_consolidation", "ux_telemetry_followup"]
    assert manifest.get("pipeline_stages") == stages

    js = (BUILD_ROOT / "static/app.js").read_text(encoding="utf-8")
    index = (BUILD_ROOT / "index.html").read_text(encoding="utf-8")

    assert MARKER in js
    assert CACHE_QUERY in index
    assert "jjV6Telemetry.awaitingFresh=true" in js
    assert "jjV73FreshState();" in js
    assert "jjV73ActionRejected();toast(err.message)" in js
    assert "jjV73ReadySuccess();toast('開始準備を完了しました')" in js
    assert "jjV73Review('table_open')" in js
    assert "jjV73Review('bookmark')" in js

    start = js.index("// v73 ux telemetry followup")
    end = js.index("// Desktop bet markers use explicit poker-table lanes", start)
    helper = js[start:end]
    for forbidden in (
        "me.id", "me?.id", "me.name", "me?.name", "user_id", "hand_id",
        "table_id", "cards", "chip", "amount", "chat", "session", "userAgent",
    ):
        assert forbidden not in helper, f"sensitive value leaked into UX helper: {forbidden}"
    assert "fetch(" not in helper, "followup must reuse the existing telemetry batch sender"

    module_source = (ROOT / "ux_telemetry_followup.py").read_text(encoding="utf-8")
    assert "setInterval" not in module_source
    assert EVENT_DETAILS["reconnect"] == {"ws_open", "fresh_state"}
    assert EVENT_DETAILS["ready"] == {"submit"}
    assert EVENT_DETAILS["action_result"] == {"rejected"}
    assert EVENT_DETAILS["review"] == {"table_open", "bookmark"}

    admin_js = (ROOT / "admin_static" / "ux_telemetry.js").read_text(encoding="utf-8")
    assert "uxReadyP50" in admin_js
    assert "uxReviewOpens" in admin_js
    assert "uxActionRejects" in admin_js
    assert "reconnect_successes" in admin_js

    # The post-build transform is deliberately idempotent.
    assert transform_app_js(js) == js

    print("JJ_UX_TELEMETRY_FOLLOWUP_OK")


if __name__ == "__main__":
    main()
