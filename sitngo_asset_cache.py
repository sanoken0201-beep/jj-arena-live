"""Sit&Go runtime bootstrap plus compatibility cache-token export.

Browser mutation is owned by ``sitngo_browser_config`` and is compiled during
asset build. This module remains the runtime bootstrap for tournament-only
scheduler/action-safety wrappers so the app install order stays stable.
"""
from __future__ import annotations

from sitngo_browser_config import CACHE_QUERY


def install() -> None:
    import sitngo
    import sitngo_action_safety
    import sitngo_browser_config
    import sitngo_hand_levels
    import sitngo_runtime
    import sitngo_tournament_rules

    sitngo_tournament_rules.install(sitngo_runtime)
    sitngo_hand_levels.install(sitngo, sitngo_runtime)
    sitngo_action_safety.install(sitngo_runtime)
    sitngo_browser_config.install()


__all__ = ["CACHE_QUERY", "install"]
