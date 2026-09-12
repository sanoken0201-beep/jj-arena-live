from __future__ import annotations

from pathlib import Path

from player_ux_asset_transform import transform_app_js as phase1_js
from player_ux_phase2 import transform_app_js as phase2_js, transform_styles as phase2_css
from player_ux_phase3 import transform_app_js as phase3_js, transform_styles as phase3_css
from player_ux_phase4 import transform_app_js as phase4_js, transform_styles as phase4_css
from player_ux_phase5 import PHASE5_MARKER, transform_app_js as phase5_js, transform_styles as phase5_css


ROOT = Path(__file__).resolve().parent


def main() -> None:
    raw_js = (ROOT / "materialized_v1244" / "static" / "app.js").read_text(encoding="utf-8")
    raw_css = (ROOT / "materialized_v1244" / "static" / "styles.css").read_text(encoding="utf-8")
    js4 = phase4_js(phase3_js(phase2_js(phase1_js(raw_js))))
    js5 = phase5_js(js4)
    css5 = phase5_css(phase4_css(phase3_css(phase2_css(raw_css))))

    assert PHASE5_MARKER in js5 and PHASE5_MARKER in css5
    assert phase5_js(js5) == js5
    assert phase5_css(css5) == css5

    # Pre-actions are deliberately zero-chip only. No call-any or automatic raise exists.
    assert "data-jj-preaction=\"check\"" in js5
    assert "data-jj-preaction=\"check_fold\"" in js5
    assert "コール・ベット・レイズは自動実行しません" in js5
    pre_start = js5.index("function jjV5MaybeRunPreAction")
    pre_end = js5.index("function jjV5HotkeysEnabled")
    pre_code = js5[pre_start:pre_end]
    assert 'data-action=\"check\"' in pre_code
    assert 'data-action=\"fold\"' in pre_code
    assert 'data-action=\"call\"' not in pre_code
    assert 'data-action=\"raise\"' not in pre_code
    assert "document.visibilityState!=='visible'" in pre_code
    assert "!jjV2Connection.fresh" in pre_code
    assert "live.click()" in pre_code, "pre-action must reuse the existing authoritative click/action path"
    assert "reserved.key!==jjV5HandKey()" in pre_code

    # Keyboard support is opt-in, avoids native browser Ctrl+F/R/K, and never commits an action by itself.
    assert "localStorage.getItem(jjV3UserKey('hotkeys'))==='1'" in js5
    assert "!e.ctrlKey||!e.shiftKey||e.altKey||e.metaKey||e.repeat" in js5
    assert "jjV5TypingTarget(e.target)||$('#modal')?.open" in js5
    hot_start = js5.index("function jjV5HandleHotkey")
    hot_end = js5.index("function jjV5ResultKey")
    hot_code = js5[hot_start:hot_end]
    assert "e.code==='Digit1'" in hot_code and 'data-action=\"fold\"' in hot_code
    assert "e.code==='Digit2'" in hot_code and 'data-action=\"check\"' in hot_code
    assert "e.code==='Digit3'" in hot_code and "mode='focus-input'" in hot_code
    assert "Digit[4-7]" in hot_code
    assert "mode==='focus-action'" in hot_code and "target.focus" in hot_code
    assert "mode==='size'" in hot_code and "target.click()" in hot_code
    assert "KeyF" not in hot_code and "KeyR" not in hot_code and "KeyK" not in hot_code
    assert 'data-action=\"call\"' not in hot_code
    assert 'data-action=\"raise\"' not in hot_code
    assert "doAction(" not in hot_code
    focus_action = hot_code[hot_code.index("if(mode==='focus-action')"):hot_code.index("if(mode==='focus-input')")]
    assert ".click()" not in focus_action, "Fold/Check keyboard shortcut must only focus, not execute"
    assert "キーボード補助を有効にする" in js5
    assert "Ctrl+F / Ctrl+R / Ctrl+Kは使用しません" in js5
    assert "フォールド・チェックはショートカットだけでは確定しません" in js5

    # Result details shrink after seven seconds or immediately when the next decision arrives.
    assert "setTimeout(()=>{if(jjV5ResultKey()===key&&!jjV5SettlementExpanded)jjV5SetSettlementCompact(true)},7000)" in js5
    assert "if(tableState?.legal?.can_act&&!jjV5SettlementExpanded)jjV5SetSettlementCompact(true)" in js5
    assert "data-jj-result-toggle" in js5
    assert "#resultBanner.jj-v5-result-compact" in css5
    assert ".jj-settlement-actions" in css5 and ".jj-settlement-note" in css5

    # The production asset chain is phase1 -> phase2 -> phase3 -> phase4 -> phase5 with a fresh cache namespace.
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "transform_phase5_app_js(transform_phase4_app_js(transform_phase3_app_js(transform_phase2_app_js(transform_app_js(js)))))" in app_source
    assert "transform_phase5_styles(transform_phase4_styles(transform_phase3_styles(transform_phase2_styles(css))))" in app_source
    assert "/static/styles.css?v=64" in app_source
    assert "/static/app.js?v=64" in app_source
    assert "jj-arena-live-v64" in app_source
    assert '"PHASE5_MARKER"' in app_source

    print("JJ_PLAYER_UX_PHASE5_OK")


if __name__ == "__main__":
    main()
