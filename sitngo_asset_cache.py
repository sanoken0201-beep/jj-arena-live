"""Cache-bust only the Sit&Go player JavaScript contract.

The repository-wide ``served_assets.ASSET_VERSION`` is shared by many release
checks. Sit&Go configuration changes therefore use a dedicated query token
instead of mutating that global contract.

``install()`` is also the final root-level Sit&Go bootstrap invoked by app.py
before ``sitngo.install()`` constructs TournamentRuntime. Tournament-only
button/blind rules, fixed 12-hand blind progression and turn/timeout safety are
installed here so the immutable materialized core remains untouched and
browser-only build jobs stay dependency-free.
"""
from __future__ import annotations

CACHE_QUERY = "sngcfg=audit-hardening-20260919-1"


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

    import sitngo_ui as ui

    if getattr(ui, "_JJ_SNG_CACHE_PATCHED", False):
        return

    original_transform_index = ui.transform_index

    def transform_index(source: str) -> str:
        output = original_transform_index(source)
        if CACHE_QUERY in output:
            return output
        marker = "/static/app.js?v="
        if output.count(marker) != 1:
            raise RuntimeError("Sit&Go cache contract drift: app.js URL not found exactly once")
        start = output.index(marker)
        end = output.find('"', start)
        if end < 0:
            raise RuntimeError("Sit&Go cache contract drift: app.js URL terminator missing")
        current = output[start:end]
        separator = "&" if "?" in current else "?"
        return output[:start] + current + separator + CACHE_QUERY + output[end:]

    ui.transform_index = transform_index
    ui._JJ_SNG_CACHE_PATCHED = True


__all__ = ["CACHE_QUERY", "install"]
