from __future__ import annotations

"""Single orchestration point for JJ Arena browser output.

Historical transform modules remain as tested implementation units, but their
production ordering is declared here instead of being spread across the build
entrypoint or request-serving path. New browser behavior must be compiled into
`.jj_build` here; `app.py` serves that validated output without mutation.
"""

from pathlib import Path

from browser_runtime_consolidation import apply_to_build as apply_runtime_browser_consolidation
from browser_structure_consolidation import apply_to_build as apply_structure_consolidation
from non_sng_safety import apply_to_build as apply_non_sng_safety
from poker_connection_fix import apply_to_build as apply_oop_check_freshness
from poker_control_safety import apply_to_build as apply_poker_control_safety
from ux_telemetry_followup import apply_to_build as apply_ux_telemetry_followup

PIPELINE_VERSION = 4
POST_BUILD_STAGES = (
    ("oop_check_freshness", apply_oop_check_freshness),
    ("poker_control_safety", apply_poker_control_safety),
    ("non_sng_safety", apply_non_sng_safety),
    ("structure_consolidation", apply_structure_consolidation),
    # Runtime consolidation absorbs the former request-time browser mutations.
    ("runtime_browser_consolidation", apply_runtime_browser_consolidation),
    # Final append-only instrumentation: no UI/gameplay mutation and no polling.
    ("ux_telemetry_followup", apply_ux_telemetry_followup),
)


def finalize_build(output_root: Path | str, manifest: dict) -> dict:
    root = Path(output_root)
    applied: list[str] = []
    for name, transform in POST_BUILD_STAGES:
        manifest = transform(root, manifest)
        applied.append(name)

    manifest["pipeline_version"] = PIPELINE_VERSION
    manifest["pipeline_stages"] = applied
    manifest["browser_output_contract"] = "canonical-prebuilt-v1"

    import json

    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


__all__ = ["PIPELINE_VERSION", "POST_BUILD_STAGES", "finalize_build"]
