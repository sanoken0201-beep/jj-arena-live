from __future__ import annotations

import re
from pathlib import Path

from player_ux_asset_transform import transform_app_js as phase1
from player_ux_phase2 import transform_app_js as phase2
from player_ux_phase3 import PHASE3_MARKER, transform_app_js as phase3, transform_styles


ROOT = Path(__file__).resolve().parent


def main() -> None:
    raw_js = (ROOT / "materialized_v1244" / "static" / "app.js").read_text(encoding="utf-8")
    raw_css = (ROOT / "materialized_v1244" / "static" / "styles.css").read_text(encoding="utf-8")
    before = phase2(phase1(raw_js))
    patched = phase3(before)
    css = transform_styles(raw_css)

    assert PHASE3_MARKER in patched
    assert phase3(patched) == patched

    assert "JJ_V3_SIZING_DEFAULTS={pre:[2.5,3,4],post:[33,50,75,100]}" in patched
    assert "localStorage.setItem(jjV3UserKey('sizing')" in patched
    assert "localStorage.removeItem(jjV3UserKey('sizing'))" in patched
    assert "初期値に戻す" in patched
    assert "この端末に保存します" in patched
    settings_start = patched.index("function jjV3OpenSizingSettings")
    settings_end = patched.index("async function jjV3BookmarkHand")
    settings_code = patched[settings_start:settings_end]
    assert "/action" not in settings_code
    assert "post(`/tables/" not in settings_code

    assert "jjV124PresetTarget(pre?'pre':'post'" in patched
    assert "サイズ・合計" in patched
    assert " · 同額" in patched
    assert "is-duplicate-target" in patched
    assert "data-jj-sizing-settings" in patched
    assert "#pokerRoom .jj-size-settings{display:inline-flex!important" in css

    assert "id=\"jjFocusModeToggle\"" in patched
    assert "集中表示" in patched and "通常表示" in patched
    assert "localStorage.setItem(jjV3UserKey('focus')" in patched
    assert "const back=e.target.closest('#backLobby')" in patched
    assert "document.body.classList.remove('jj-poker-focus','jj-poker-keyboard-open')" in patched
    assert "visualViewport" in patched
    assert "jj-poker-keyboard-open" in patched
    assert "--jj-vv-bottom" in patched
    assert "body.jj-poker-focus .sidebar{display:none!important}" in css
    assert "body.jj-poker-focus .topbar{display:none!important}" in css
    assert "body.jj-poker-keyboard-open.jj-mobile-table-open.jj-mobile-poker-can-act #actionBar" in css
    assert "#pokerRoom .result-banner{flex-direction:column" in css

    assert "直前のハンドを見る" in patched
    assert "あとで復習" in patched
    assert "async function jjV3BookmarkHand" in patched
    assert "bookmarked:true,note:String(review.note||''),tags:Array.isArray(review.tags)?review.tags:[]" in patched
    assert "/analysis/hands/${encodeURIComponent(handId)}/review" in patched

    entry = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "transform_phase3_app_js(" in entry
    assert "transform_phase3_styles(" in entry
    js_versions = [int(v) for v in re.findall(r"/static/app\.js\?v=(\d+)", entry)]
    css_versions = [int(v) for v in re.findall(r"/static/styles\.css\?v=(\d+)", entry)]
    cache_versions = [int(v) for v in re.findall(r"jj-arena-live-v(\d+)", entry)]
    assert js_versions and max(js_versions) >= 60
    assert css_versions and max(css_versions) >= 60
    assert cache_versions and max(cache_versions) >= 60

    print("JJ_PLAYER_UX_PHASE3_SMOKE_OK")


if __name__ == "__main__":
    main()
