"""Compile production browser assets from the immutable materialized core."""
from __future__ import annotations

from poker_connection_fix import apply_to_build as apply_oop_check_freshness
from served_assets import ASSET_VERSION, BUILD_ROOT, build_all, validate_built_assets


def main() -> None:
    manifest = build_all(BUILD_ROOT)
    manifest = apply_oop_check_freshness(BUILD_ROOT, manifest)
    validate_built_assets(BUILD_ROOT)
    print(
        "JJ_SERVED_ASSETS_BUILT "
        f"version={ASSET_VERSION} outputs={len(manifest['outputs'])} root={BUILD_ROOT}"
    )


if __name__ == "__main__":
    main()
