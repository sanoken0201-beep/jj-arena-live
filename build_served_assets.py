"""Compile production browser assets from the immutable materialized core."""
from __future__ import annotations

from browser_asset_pipeline import finalize_build
import sitngo_browser_config

# Browser transforms deliberately remain dependency-free: several release jobs
# compile assets without installing the FastAPI production dependency set.
sitngo_browser_config.install()

from served_assets import ASSET_VERSION, BUILD_ROOT, build_all, validate_built_assets


def main() -> None:
    manifest = build_all(BUILD_ROOT)
    manifest = finalize_build(BUILD_ROOT, manifest)
    validate_built_assets(BUILD_ROOT)
    print(
        "JJ_SERVED_ASSETS_BUILT "
        f"version={ASSET_VERSION} pipeline={manifest.get('pipeline_version')} "
        f"stages={len(manifest.get('pipeline_stages') or [])} "
        f"outputs={len(manifest['outputs'])} root={BUILD_ROOT}"
    )


if __name__ == "__main__":
    main()
