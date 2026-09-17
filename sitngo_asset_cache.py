"""Cache-bust only the Sit&Go player JavaScript contract.

The repository-wide ``served_assets.ASSET_VERSION`` is shared by many release
checks. Sit&Go configuration changes therefore use a dedicated query token
instead of mutating that global contract.
"""
from __future__ import annotations

CACHE_QUERY = "sngcfg=admin-structure-20260917-1"


def install() -> None:
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
