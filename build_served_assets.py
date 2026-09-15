"""Compile production browser assets from the immutable materialized core."""
from __future__ import annotations

import hashlib
import json

from poker_table_focus import (
    POKER_TABLE_FOCUS_MARKER,
    transform_app_js as transform_poker_focus_app_js,
    transform_styles as transform_poker_focus_styles,
)
from served_assets import ASSET_VERSION, BUILD_ROOT, build_all, validate_built_assets


POKER_FOCUS_QUERY = "pf=poker-focus-20260915-1"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _apply_poker_focus(manifest: dict) -> dict:
    """Apply the final table-only UX layer after every canonical asset transform."""
    paths = {
        "static/app.js": transform_poker_focus_app_js,
        "static/styles.css": transform_poker_focus_styles,
    }
    for relative, transform in paths.items():
        path = BUILD_ROOT / relative
        value = transform(path.read_text(encoding="utf-8"))
        path.write_text(value, encoding="utf-8", newline="\n")
        manifest["outputs"][relative] = _digest(value)

    # app.py adds its own compatibility query token to this prefix at response
    # time. A second build token guarantees this release bypasses any cached
    # v70 poker assets without changing the immutable materialized core.
    index_path = BUILD_ROOT / "index.html"
    index = index_path.read_text(encoding="utf-8")
    index = index.replace(
        f"/static/app.js?v={ASSET_VERSION}",
        f"/static/app.js?v={ASSET_VERSION}&{POKER_FOCUS_QUERY}",
    )
    index = index.replace(
        f"/static/styles.css?v={ASSET_VERSION}",
        f"/static/styles.css?v={ASSET_VERSION}&{POKER_FOCUS_QUERY}",
    )
    index_path.write_text(index, encoding="utf-8", newline="\n")
    manifest["outputs"]["index.html"] = _digest(index)
    post = dict(manifest.get("post_transforms") or {})
    post["poker_table_focus"] = POKER_TABLE_FOCUS_MARKER
    manifest["post_transforms"] = post
    (BUILD_ROOT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


def main() -> None:
    manifest = build_all(BUILD_ROOT)
    manifest = _apply_poker_focus(manifest)
    validate_built_assets(BUILD_ROOT)
    print(
        "JJ_SERVED_ASSETS_BUILT "
        f"version={ASSET_VERSION} outputs={len(manifest['outputs'])} root={BUILD_ROOT}"
    )


if __name__ == "__main__":
    main()
