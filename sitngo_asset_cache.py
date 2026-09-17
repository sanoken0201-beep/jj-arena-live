"""Bootstrap Sit&Go entry rules and cache-bust its player JavaScript contract.

The repository-wide ``served_assets.ASSET_VERSION`` is shared by many release
checks. Sit&Go feature changes therefore use a dedicated query token instead of
mutating that global contract.
"""
from __future__ import annotations

CACHE_QUERY = "sngcfg=late-reg-reentry-20260918-2"


def install() -> None:
    # app.py calls this before sitngo.install(); install the server-side entry
    # contract here so all later FastAPI routes bind the extended request models.
    import sitngo
    import sitngo_entry_rules
    import sitngo_runtime

    sitngo_entry_rules.install(sitngo, sitngo_runtime)

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
