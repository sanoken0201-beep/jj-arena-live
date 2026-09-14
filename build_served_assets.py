"""Compile production browser assets from the immutable materialized core."""
from __future__ import annotations

from served_assets import ASSET_VERSION, BUILD_ROOT, build_all, validate_built_assets


def main() -> None:
    manifest = build_all(BUILD_ROOT)
    validate_built_assets(BUILD_ROOT)
    print(
        "JJ_SERVED_ASSETS_BUILT "
        f"version={ASSET_VERSION} outputs={len(manifest['outputs'])} root={BUILD_ROOT}"
    )


if __name__ == "__main__":
    main()
