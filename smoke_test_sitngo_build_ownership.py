"""Regression for Sit&Go browser-build ownership and read indexes."""
from __future__ import annotations

from pathlib import Path

import sitngo_browser_config
from smoke_test_sitngo_phase1 import production_app

ROOT = Path(__file__).resolve().parent


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    admin_config = (ROOT / "sitngo_admin_config.py").read_text(encoding="utf-8")
    hand_levels = (ROOT / "sitngo_hand_levels.py").read_text(encoding="utf-8")
    asset_cache = (ROOT / "sitngo_asset_cache.py").read_text(encoding="utf-8")

    require("_patch_player_ui" not in admin_config, "admin config still mutates player UI at runtime")
    require("import sitngo_ui" not in admin_config, "admin config still imports player UI at runtime")
    require(".write_text(" not in hand_levels, "hand-level runtime still writes browser assets at startup")
    require("sitngo_ui" not in hand_levels, "hand-level runtime still mutates player browser assets")
    require("_patch_admin_assets" not in hand_levels, "hand-level runtime still mutates admin assets")
    require("sitngo_ui" not in asset_cache and "transform_index" not in asset_cache, "asset bootstrap still patches UI at runtime")

    admin_index = (ROOT / "admin_static" / "index.html").read_text(encoding="utf-8")
    require(
        f"admin_sitngo.js?{sitngo_browser_config.ADMIN_CACHE_QUERY}" in admin_index,
        "committed admin Sit&Go cache identity is missing",
    )

    built_index = production_app._patched_index()
    built_js = production_app._patched_app_js()
    require(sitngo_browser_config.CACHE_QUERY in built_index, "player Sit&Go cache query was not compiled")
    require(sitngo_browser_config.HAND_LEVEL_UI_MARKER in built_js, "12-hand player UI was not compiled")
    require(sitngo_browser_config.TURN_UI_MARKER in built_js, "turn-safety player UI was not compiled")

    db = production_app.db
    expected = {"idx_sitngo_hands_event_created", "idx_sitngo_messages_event_created"}
    with db.connect() as con:
        if getattr(db, "IS_POSTGRES", False):
            rows = con.execute(
                "SELECT indexname name FROM pg_indexes WHERE schemaname='public' "
                "AND indexname IN (?,?)",
                tuple(sorted(expected)),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name IN (?,?)",
                tuple(sorted(expected)),
            ).fetchall()
    require({str(row["name"]) for row in rows} == expected, "Sit&Go event/history read indexes are missing")

    print("JJ_SITNGO_BUILD_OWNERSHIP_OK")


if __name__ == "__main__":
    main()
