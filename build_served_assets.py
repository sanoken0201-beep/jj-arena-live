"""Compile production browser assets from the immutable materialized core."""
from __future__ import annotations

import hashlib
import json

from served_assets import ASSET_VERSION, BUILD_ROOT, build_all, validate_built_assets
from sitngo_ui import (
    SITNGO_UI_MARKER,
    transform_app_js as transform_sitngo_app_js,
    transform_index as transform_sitngo_index,
    transform_styles as transform_sitngo_styles,
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _apply_sitngo_post_transform(manifest: dict) -> dict:
    transforms = {
        "index.html": transform_sitngo_index,
        "static/app.js": transform_sitngo_app_js,
        "static/styles.css": transform_sitngo_styles,
    }
    for relative, transform in transforms.items():
        path = BUILD_ROOT / relative
        value = transform(path.read_text(encoding="utf-8"))
        path.write_text(value, encoding="utf-8", newline="\n")
        manifest["outputs"][relative] = _digest(value)
    manifest["post_transforms"] = {"sitngo_ui": SITNGO_UI_MARKER}
    (BUILD_ROOT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


def main() -> None:
    manifest = build_all(BUILD_ROOT)
    manifest = _apply_sitngo_post_transform(manifest)
    validate_built_assets(BUILD_ROOT)
    print(
        "JJ_SERVED_ASSETS_BUILT "
        f"version={ASSET_VERSION} outputs={len(manifest['outputs'])} root={BUILD_ROOT}"
    )


if __name__ == "__main__":
    main()
