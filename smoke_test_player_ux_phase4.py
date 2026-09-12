from __future__ import annotations

from pathlib import Path

from player_ux_asset_transform import transform_app_js as phase1
from player_ux_phase2 import transform_app_js as phase2, transform_styles as phase2_styles
from player_ux_phase3 import transform_app_js as phase3, transform_styles as phase3_styles
from player_ux_phase4 import PHASE4_MARKER, transform_app_js as phase4, transform_styles as phase4_styles


ROOT = Path(__file__).resolve().parent


def main() -> None:
    raw_js = (ROOT / "materialized_v1244" / "static" / "app.js").read_text(encoding="utf-8")
    raw_css = (ROOT / "materialized_v1244" / "static" / "styles.css").read_text(encoding="utf-8")
    before = phase3(phase2(phase1(raw_js)))
    patched = phase4(before)
    css = phase4_styles(phase3_styles(phase2_styles(raw_css)))

    assert PHASE4_MARKER in patched
    assert phase4(patched) == patched
    assert PHASE4_MARKER in css
    assert phase4_styles(css) == css

    # Phase 3 emits the actual legal target. Phase 4A must not hide it and must
    # remove the settings control from the live betting row.
    hidden_rule = "#actionBar .jj-v124-sizing .jj-size-btn small{display:none!important}"
    shown_rule = "#actionBar .jj-v124-sizing .jj-size-btn small{display:block!important}"
    assert hidden_rule in raw_css
    assert shown_rule in css
    assert css.rfind(shown_rule) > css.find(hidden_rule)
    assert "サイズ・合計" in patched
    assert " · 同額" in patched
    assert 'class="jj-size-btn jj-size-settings"' not in patched

    # Settings are now table chrome, and cannot be opened during the player's
    # live decision because the header button is disabled while legal.can_act.
    assert 'id="jjSizingSettingsOpen"' in patched
    assert 'data-jj-sizing-settings' in patched
    assert "const settings=$('#jjSizingSettingsOpen',tools),busy=!!tableState?.legal?.can_act" in patched
    assert "settings.disabled=busy" in patched
    assert "自分のアクション中はサイズ設定を変更できません" in patched

    # Compact layouts retain the existing private chat/log DOM and expose it as
    # a reversible drawer instead of duplicating hand data.
    assert "function jjV4OpenSideDrawer" in patched
    assert "function jjV4CloseSideDrawer" in patched
    assert 'id="jjSideDrawerToggle"' in patched
    assert 'id="jjSideDrawerClose"' in patched
    assert 'id="jjSideDrawerBackdrop"' in patched
    assert "jj-poker-side-open" in patched
    assert "e.key==='Escape'" in patched
    assert "#pokerRoom .table-side{display:block!important;position:fixed!important" in css
    assert "body.jj-poker-side-open #pokerRoom .table-side" in css

    # Mobile readability priorities: numeric stack/action information is larger
    # than the previous compact values while the desktop-only focus toggle is
    # removed from the phone header.
    assert "#pokerRoom #jjFocusModeToggle{display:none!important}" in css
    assert "#pokerRoom .jj-seat-box .stack{font-size:.8rem!important" in css
    assert "#actionBar .jj-v124-decision-meta strong{font-size:.74rem!important" in css
    assert "#actionBar .jj-main-actions .jj-action-btn b{font-size:.9rem!important" in css

    entry = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "transform_phase4_app_js(transform_phase3_app_js(transform_phase2_app_js(transform_app_js(js))))" in entry
    assert "transform_phase4_styles(transform_phase3_styles(transform_phase2_styles(css)))" in entry
    assert "'/static/app.js?v=61'" in entry
    assert "'/static/styles.css?v=61'" in entry
    assert "jj-arena-live-v61" in entry
    assert '"PHASE4_MARKER"' in entry

    print("JJ_PLAYER_UX_PHASE4_SMOKE_OK")


if __name__ == "__main__":
    main()
