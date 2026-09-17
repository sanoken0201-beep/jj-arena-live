from __future__ import annotations

"""Single orchestration point for JJ Arena browser output.

Historical transform modules remain as tested implementation units, but their
production ordering is declared here instead of being spread across the build
entrypoint. New browser changes should either be folded into an existing stage
or registered here explicitly.
"""

from pathlib import Path

from browser_structure_consolidation import apply_to_build as apply_structure_consolidation
from non_sng_safety import apply_to_build as apply_non_sng_safety
from poker_connection_fix import apply_to_build as apply_oop_check_freshness
from poker_control_safety import apply_to_build as apply_poker_control_safety

PIPELINE_VERSION = 2
POST_BUILD_STAGES = (
    ("oop_check_freshness", apply_oop_check_freshness),
    ("poker_control_safety", apply_poker_control_safety),
    ("non_sng_safety", apply_non_sng_safety),
    ("structure_consolidation", apply_structure_consolidation),
)


def finalize_build(output_root: Path | str, manifest: dict) -> dict:
    root = Path(output_root)
    applied: list[str] = []
    for name, transform in POST_BUILD_STAGES:
        manifest = transform(root, manifest)
        applied.append(name)

    manifest["pipeline_version"] = PIPELINE_VERSION
    manifest["pipeline_stages"] = applied

    import json

    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


__all__ = ["PIPELINE_VERSION", "POST_BUILD_STAGES", "finalize_build"]
