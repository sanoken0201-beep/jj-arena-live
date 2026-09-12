from __future__ import annotations

import re
from pathlib import Path

from player_ux_asset_transform import transform_app_js as phase1_js
from player_ux_phase2 import transform_app_js as phase2_js, transform_styles as phase2_css
from player_ux_phase3 import transform_app_js as phase3_js, transform_styles as phase3_css
from player_ux_phase4 import PHASE4_MARKER, transform_app_js as phase4_js, transform_styles as phase4_css


ROOT = Path(__file__).resolve().parent


def main() -> None:
    source_js = (ROOT / "materialized_v1244" / "static" / "app.js").read_text(encoding="utf-8")
    source_css = (ROOT / "materialized_v1244" / "static" / "styles.css").read_text(encoding="utf-8")

    js3 = phase3_js(phase2_js(phase1_js(source_js)))
    js4 = phase4_js(js3)
    css4 = phase4_css(phase3_css(phase2_css(source_css)))

    assert PHASE4_MARKER in js4
    assert PHASE4_MARKER in css4
    assert phase4_js(js4) == js4, "phase 4 JS transform must be idempotent"
    assert phase4_css(css4) == css4, "phase 4 CSS transform must be idempotent"

    old_hide = "#actionBar .jj-v124-sizing .jj-size-btn small{display:none!important}"
    phase4_show = "#actionBar .jj-v124-sizing .jj-size-btn small{display:block!important}"
    assert old_hide in css4
    assert phase4_show in css4
    assert css4.rfind(phase4_show) > css4.rfind(old_hide)

    assert '${quick}${allin}<button type="button" class="jj-size-btn jj-size-settings"' not in js4
    assert 'id="jjPokerSettings" data-jj-sizing-settings' in js4
    assert "if(tableState?.legal?.can_act)return toast('自分のアクション中は設定を変更できません')" in js4

    assert 'data-jj-mobile-side="log">履歴</button>' in js4
    assert 'data-jj-mobile-side="chat">チャット</button>' in js4
    assert 'id="jjV4SideClose"' in js4
    assert "document.body.classList.add('jj-v4-side-open')" in js4
    assert "body.jj-v4-side-open #pokerRoom .table-side" in css4
    assert "display:block!important;position:fixed!important" in css4

    assert "#pokerRoom .jj-seat-box .stack{font-size:.76rem!important" in css4
    assert "body.jj-mobile-table-open #actionBar .jj-v124-decision-meta strong{font-size:.72rem!important}" in css4

    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "transform_phase4_app_js(" in app_source
    assert "transform_phase4_styles(" in app_source
    js_version = re.search(r"/static/app\.js\?v=(\d+)", app_source)
    css_version = re.search(r"/static/styles\.css\?v=(\d+)", app_source)
    cache_version = re.search(r"jj-arena-live-v(\d+)", app_source)
    assert js_version and int(js_version.group(1)) >= 61
    assert css_version and int(css_version.group(1)) >= 61
    assert cache_version and int(cache_version.group(1)) >= 61

    print("JJ_PLAYER_UX_PHASE4_OK")


if __name__ == "__main__":
    main()
