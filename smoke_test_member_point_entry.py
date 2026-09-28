from __future__ import annotations

import app
from served_assets import build_app_js, build_index


def main() -> None:
    index = build_index()
    js = build_app_js()

    assert '<button class="nav" data-view="points">＋ <span>ポイント入力</span></button>' in index
    assert '<button class="nav admin-only" data-view="points">' not in index
    assert "if(v==='members'&&me?.role!=='admin')v='home';" in js
    assert "if((v==='points'||v==='members')&&me?.role!=='admin')v='home';" not in js
    assert "post(me?.role==='admin'?'/entries':'/member/entries',payload)" in js
    assert "point.classList.remove('hidden')" in js
    assert "pointName.readOnly=!isAdmin" in js
    assert "<span>POINTS</span>" in js
    assert 'id="quickPointForm"' in js
    assert "quickName.readOnly=me?.role!=='admin'" in js
    assert "if(!me){if(existing)existing.remove();return}" in js
    assert "if(me?.role==='admin')quickPointLoadNames()" in js
    assert "if(isMobileUX()){ensureQuickPointHome();$('#homePointShortcut')?.remove()}" in js
    assert "else{$('#mobileQuickPointCard')?.remove();ensureDesktopPointShortcut()}" in js

    member_routes = [
        route for route in app.app.router.routes
        if getattr(route, "path", None) == "/api/member/entries"
        and "POST" in (getattr(route, "methods", None) or set())
    ]
    assert len(member_routes) == 1

    captured = {}
    original = app.runtime_server.add_entry
    try:
        def fake_add_entry(payload, user):
            captured["name"] = payload.name
            captured["user_id"] = user["id"]
            return {"ok": True}

        app.runtime_server.add_entry = fake_add_entry
        payload = app.runtime_server.PointEntry(
            name="OTHER",
            date="2026-09-28T18:30",
            reentries=0,
            initial=450,
            game_type="ring",
            chip_1=450,
        )
        result = app._member_point_entry(
            payload,
            {"id": 7, "name": "メンバー", "ranking_name": "ランキング名"},
        )
        assert result == {"ok": True}
        assert captured == {"name": "ランキング名", "user_id": 7}
    finally:
        app.runtime_server.add_entry = original

    print("MEMBER_POINT_ENTRY_OK")


if __name__ == "__main__":
    main()
