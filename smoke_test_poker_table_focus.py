from __future__ import annotations

import json

from build_served_assets import POKER_FOCUS_QUERY, main as build_assets
from materialized_v1244.poker_engine import blank_table_state, public_state, seat_player, start_hand
from poker_table_focus import POKER_TABLE_FOCUS_MARKER
from served_assets import BUILD_ROOT, MATERIALIZED_STATIC


def _privacy_contract() -> None:
    state = blank_table_state(
        table_id="focus-test",
        name="Focus Test",
        max_seats=6,
        small_blind=50,
        big_blind=100,
        min_buyin=100,
        max_buyin=20000,
    )
    seat_player(state, user_id=1, name="Hero", seat=0, stack=15000)
    seat_player(state, user_id=2, name="Villain", seat=3, stack=15000)
    start_hand(state)
    original_hero = next(player for player in state["seats"] if player["user_id"] == 1)
    view = public_state(state, 1)
    hero = next(player for player in view["seats"] if player["user_id"] == 1)
    villain = next(player for player in view["seats"] if player["user_id"] == 2)
    assert len(original_hero["cards"]) == 2
    assert hero["cards"] == original_hero["cards"], "server redacted the viewer's own cards"
    assert villain["cards"] == ["??", "??"], "opponent private cards leaked"


def main() -> None:
    canonical_app = (MATERIALIZED_STATIC / "app.js").read_text(encoding="utf-8")
    canonical_css = (MATERIALIZED_STATIC / "styles.css").read_text(encoding="utf-8")
    assert POKER_TABLE_FOCUS_MARKER not in canonical_app
    assert POKER_TABLE_FOCUS_MARKER not in canonical_css

    build_assets()
    app = (BUILD_ROOT / "static/app.js").read_text(encoding="utf-8")
    css = (BUILD_ROOT / "static/styles.css").read_text(encoding="utf-8")
    index = (BUILD_ROOT / "index.html").read_text(encoding="utf-8")
    manifest = json.loads((BUILD_ROOT / "manifest.json").read_text(encoding="utf-8"))

    assert POKER_TABLE_FOCUS_MARKER in app
    assert POKER_TABLE_FOCUS_MARKER in css
    assert manifest.get("post_transforms", {}).get("poker_table_focus") == POKER_TABLE_FOCUS_MARKER
    assert POKER_FOCUS_QUERY in index

    # Hero cards must have a dedicated, seat-independent visual surface.
    assert "jjHeroHandDock" in app
    assert "jjFocusRenderHeroHand" in app
    assert "cards.filter(c=>c&&c!=='??')" in app
    assert "カードを同期中…" in app
    assert ".jj-hero-hand-dock" in css
    assert "#pokerRoom .jj-seat.is-hero .jj-hole{display:none!important}" in css

    # The historical pre-action Check/Fold layer is deliberately removed from
    # the live decision surface; only server-legal action buttons remain.
    assert "jjV5ClearPreAction" in app
    assert "#actionBar .jj-v5-preactions" in css

    # CHECK and FOLD own one explicit desktop-safe dispatch path and action
    # buttons can never become implicit form submit buttons.
    selector = '#actionBar [data-action="check"],#actionBar [data-action="fold"]'
    assert selector in app
    assert "e.stopImmediatePropagation();" in app
    assert "await doAction(action)" in app
    assert 'type="button" class="jj-action-btn' in app
    assert "#pokerRoom #actionBar .jj-action-btn{pointer-events:auto!important" in css

    # Redundant live-table metadata should no longer consume the decision area.
    for token in (
        "#pokerRoom #jjPokerSettings",
        "#pokerRoom #jjFocusModeToggle",
        "#pokerRoom #jjSoundToggle",
        "#actionBar .jj-v124-decision-meta",
        "#actionBar #jjV123ActionStatus",
    ):
        assert token in css

    _privacy_contract()
    print("JJ_POKER_TABLE_FOCUS_OK")


if __name__ == "__main__":
    main()
