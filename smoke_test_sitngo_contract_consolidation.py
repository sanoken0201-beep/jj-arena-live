"""Sit&Go compatibility metadata and browser-build ownership regression."""
from __future__ import annotations

import tempfile
from pathlib import Path

import sitngo_admin_config as admin_config
import sitngo_browser_config
import sitngo_hand_levels
import served_assets

ROOT = Path(__file__).resolve().parent


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    raw = [
        {"level": 1, "small_blind": 200, "big_blind": 400, "bb_ante": 400, "minutes": 1},
        {"level": 2, "small_blind": 300, "big_blind": 600, "bb_ante": 600, "minutes": 60},
    ]
    model_levels = [admin_config.BlindLevelIn(**level) for level in raw]
    require(all(level.minutes == 10 for level in model_levels), "direct API minute values were not canonicalized")
    normalized = admin_config.normalize_structure(raw, 30_000)
    require([level["minutes"] for level in normalized] == [10, 10], "new structure writes retain ineffective minute settings")
    legacy = admin_config.normalize_structure(raw, 30_000, preserve_legacy_minutes=True)
    require([level["minutes"] for level in legacy] == [1, 60], "legacy stored minute metadata lost read compatibility")

    hand_source = (ROOT / "sitngo_hand_levels.py").read_text(encoding="utf-8")
    require(".write_text(" not in hand_source, "Sit&Go hand-level install still mutates admin files at runtime")
    asset_source = (ROOT / "sitngo_asset_cache.py").read_text(encoding="utf-8")
    require("def transform_index" not in asset_source, "Sit&Go cache bootstrap still owns a second browser transform path")
    served_source = (ROOT / "served_assets.py").read_text(encoding="utf-8")
    require(
        served_source.index("sitngo_browser_config.install()") < served_source.index("from sitngo_ui import ("),
        "standalone asset build binds Sit&Go transforms before canonical browser configuration",
    )

    admin_index = (ROOT / "admin_static" / "index.html").read_text(encoding="utf-8")
    require(sitngo_hand_levels.ADMIN_CACHE_QUERY in admin_index, "committed admin Sit&Go cache contract missing")

    with tempfile.TemporaryDirectory(prefix="jj-sng-contract-build-") as directory:
        root = Path(directory)
        served_assets.build_all(root)
        js = (root / "static" / "app.js").read_text(encoding="utf-8")
        index = (root / "index.html").read_text(encoding="utf-8")
        require(sitngo_browser_config.HAND_LEVEL_UI_MARKER in js, "standalone build lost 12-hand player UI")
        require(sitngo_browser_config.CHIP_UI_MARKER in js, "standalone build lost chip-unit player UI")
        require(sitngo_browser_config.TURN_UI_MARKER in js, "standalone build lost turn-token player UI")
        require(sitngo_browser_config.CACHE_QUERY in index, "standalone build lost Sit&Go cache token")

    print("JJ_SITNGO_CONTRACT_CONSOLIDATION_OK")


if __name__ == "__main__":
    main()
