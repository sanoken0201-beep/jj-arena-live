from __future__ import annotations

"""Single orchestration point for JJ Arena browser output.

Historical transform modules remain as tested implementation units, but their
production ordering is declared here instead of being spread across the build
entrypoint or request-serving path. New browser behavior must be compiled into
`.jj_build` here; `app.py` serves that validated output without mutation.
"""

import hashlib
import json
import re
from pathlib import Path

from browser_runtime_consolidation import apply_to_build as apply_runtime_browser_consolidation
from browser_structure_consolidation import apply_to_build as apply_structure_consolidation
from non_sng_safety import apply_to_build as apply_non_sng_safety
from poker_connection_fix import apply_to_build as apply_oop_check_freshness
from poker_control_safety import apply_to_build as apply_poker_control_safety
from ux_telemetry_followup import apply_to_build as apply_ux_telemetry_followup

from quiz_request_diagnostics import apply_to_build as apply_quiz_request_diagnostics

from ranking_read_optimization import apply_to_build as apply_ranking_reads
from hand_result_trends_ui import apply_to_build as apply_hand_result_trends

PIPELINE_VERSION = 10
POST_BUILD_STAGES = (
    ("oop_check_freshness", apply_oop_check_freshness),
    ("poker_control_safety", apply_poker_control_safety),
    ("non_sng_safety", apply_non_sng_safety),
    ("structure_consolidation", apply_structure_consolidation),
    # Runtime consolidation absorbs the former request-time browser mutations.
    ("runtime_browser_consolidation", apply_runtime_browser_consolidation),
    # Final append-only instrumentation: no UI/gameplay mutation and no polling.
    ("ux_telemetry_followup", apply_ux_telemetry_followup),
    ("quiz_request_diagnostics", apply_quiz_request_diagnostics),
    ("ranking_read_optimization", apply_ranking_reads),
    ("hand_result_trends", apply_hand_result_trends),
)


def stamp_browser_cache(root: Path, manifest: dict) -> dict:
    """Bind immutable asset URLs and the SW cache to the *final* build bytes.

    A new app.js post-transform must not keep the prior versioned URL: both the
    browser's immutable HTTP cache and the service worker are cache-first.
    """
    js = (root / "static/app.js").read_bytes()
    css = (root / "static/styles.css").read_bytes()
    revisions = {
        "app.js": hashlib.sha256(js).hexdigest()[:16],
        "styles.css": hashlib.sha256(css).hexdigest()[:16],
    }
    cache_revision = hashlib.sha256(js + b"\0" + css).hexdigest()[:16]

    index_path = root / "index.html"
    index = index_path.read_text(encoding="utf-8")
    urls = {}
    for asset in ("app.js", "styles.css"):
        name = re.escape(asset)
        pattern = rf'(/static/{name}\?[^"\s]+)'
        matches = re.findall(pattern, index)
        if len(matches) != 1:
            raise RuntimeError(f"cache revision needs one index reference to {asset}")
        previous = matches[0]
        clean = re.sub(r"&build=[0-9a-f]{16}", "", previous)
        urls[asset] = f"{clean}&build={revisions[asset]}"
        index = index.replace(previous, urls[asset], 1)
    index_path.write_text(index, encoding="utf-8", newline="\n")

    worker_path = root / "static/sw.js"
    worker = worker_path.read_text(encoding="utf-8")
    worker, count = re.subn(
        r"const CACHE='jj-arena-live-v[^']+';",
        f"const CACHE='jj-arena-live-v{manifest['asset_version']}-{cache_revision}';",
        worker,
        count=1,
    )
    if count != 1:
        raise RuntimeError("service worker cache identity missing")
    for asset in ("app.js", "styles.css"):
        worker, count = re.subn(
            rf"'/static/{re.escape(asset)}\?[^']*'",
            lambda _match, asset=asset: f"'{urls[asset]}'",
            worker,
            count=1,
        )
        if count != 1:
            raise RuntimeError(f"service worker reference to {asset} missing")
    worker_path.write_text(worker, encoding="utf-8", newline="\n")

    outputs = dict(manifest["outputs"])
    for filename in ("index.html", "static/app.js", "static/styles.css", "static/sw.js"):
        outputs[filename] = hashlib.sha256((root / filename).read_bytes()).hexdigest()
    manifest["outputs"] = outputs
    manifest.setdefault("post_transforms", {})["content_addressed_browser_cache"] = cache_revision
    return manifest


def finalize_build(output_root: Path | str, manifest: dict) -> dict:
    root = Path(output_root)
    applied: list[str] = []
    for name, transform in POST_BUILD_STAGES:
        manifest = transform(root, manifest)
        applied.append(name)

    manifest = stamp_browser_cache(root, manifest)
    applied.append("content_addressed_browser_cache")

    manifest["pipeline_version"] = PIPELINE_VERSION
    manifest["pipeline_stages"] = applied
    manifest["browser_output_contract"] = "canonical-prebuilt-v1"

    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


__all__ = ["PIPELINE_VERSION", "POST_BUILD_STAGES", "finalize_build"]
