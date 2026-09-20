"""Runtime-only bootstrap for Sit&Go tournament safety integrations.

Player browser behavior and cache-busting are compiled deterministically by
`sitngo_browser_config.py` during `build_served_assets.py`. Production startup
must not mutate browser source or transform functions.
"""
from __future__ import annotations

from sitngo_browser_config import CACHE_QUERY


def install() -> None:
    # app.py calls this after sitngo_chip_rules.install() and before the service
    # constructs its isolated engine. Install order matters: action safety wraps
    # the final 12-hand scheduler and route contract, while all changes remain
    # tournament-only.
    import sitngo
    import sitngo_action_safety
    import sitngo_hand_levels
    import sitngo_runtime
    import sitngo_tournament_rules

    sitngo_tournament_rules.install(sitngo_runtime)
    sitngo_hand_levels.install(sitngo, sitngo_runtime)
    sitngo_action_safety.install(sitngo_runtime)


__all__ = ["CACHE_QUERY", "install"]
