from __future__ import annotations

"""Single production entrypoint for JJ Arena browser compilation.

The project accumulated a number of historical source transforms while the UI
was being iterated.  `served_assets.build_all` remains the compatibility
compiler for those frozen transforms; every *active* post-build mutation is now
ordered and recorded here.  Production, tests and local builds should call this
module rather than assembling transforms independently.
"""

import json
from pathlib import Path
from typing import Callable

from frontend_governance import apply_to_build as apply_frontend_governance
from non_sng_safety import apply_to_build as apply_non_sng_safety
from poker_connection_fix import apply_to_build as apply_oop_check_freshness
from poker_control_safety import apply_to_build as apply_poker_control_safety
from served_assets import ASSET_VERSION, BUILD_ROOT, build_all, validate_built_assets

PIPELINE_VERSION = 2

# Ordered public contract.  Names are deliberately stable so the manifest can
# explain exactly what produced the browser bundle without exposing transform
# implementation details to app.py or Render.
POST_BUILD_STAGES: tuple[tuple[str, Callable], ...] = (
    ("poker_connection_safety", apply_oop_check_freshness),
    ("poker_control_safety", apply_poker_control_safety),
    ("non_sng_accounting_safety", apply_non_sng_safety),
    ("frontend_governance", apply_frontend_governance),
)


def build_production_frontend(output_root: Path | str = BUILD_ROOT) -> dict:
    root = Path(output_root)
    manifest = build_all(root)
    applied: list[str] = []
    for name, stage in POST_BUILD_STAGES:
        manifest = stage(root, manifest)
        applied.append(name)

    manifest["frontend_pipeline"] = {
        "version": PIPELINE_VERSION,
        "compatibility_compiler": "served_assets.build_all",
        "post_build_stages": applied,
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    validate_built_assets(root)
    return manifest


def main() -> None:
    manifest = build_production_frontend(BUILD_ROOT)
    print(
        "JJ_SERVED_ASSETS_BUILT "
        f"version={ASSET_VERSION} pipeline={PIPELINE_VERSION} "
        f"stages={len(POST_BUILD_STAGES)} outputs={len(manifest['outputs'])} root={BUILD_ROOT}"
    )


__all__ = [
    "PIPELINE_VERSION",
    "POST_BUILD_STAGES",
    "build_production_frontend",
    "main",
]


if __name__ == "__main__":
    main()
