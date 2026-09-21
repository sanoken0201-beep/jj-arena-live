from __future__ import annotations

"""Compile the last historical request-time browser patches into `.jj_build`.

Before this module, ``app.py`` still changed ``index.html`` and ``app.js`` while
serving requests: it appended the current release cache query, corrected stale
rake copy/calculation text, and removed the obsolete automatic check/fold
control. Those are deterministic browser-build concerns, not request-time
concerns. Keeping them here makes `.jj_build` the canonical browser output.
"""

import hashlib
import json
from pathlib import Path

from poker_client_cleanup import remove_fast_fold

MARKER = "v75 canonical browser output 2026-09-17"
CACHE_QUERY = "r=timebank-20260921-1"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _append_query(value: str, base: str) -> str:
    start = value.find(base)
    if start < 0:
        raise RuntimeError(f"browser consolidation drift: asset URL missing: {base}")
    end = value.find('"', start)
    if end < 0:
        raise RuntimeError("browser consolidation drift: asset URL terminator missing")
    current = value[start:end]
    if CACHE_QUERY not in current:
        current = current.replace(base, f"{base}&{CACHE_QUERY}", 1)
        value = value[:start] + current + value[end:]
    return value


def transform_index(source: str, asset_version: int) -> str:
    value = source.replace("rake 10%・5bb cap", "rake 5%・3bb cap")
    # Preserve the exact asset cache-busting contract that app.py historically
    # applied at request time to both browser assets.
    value = _append_query(value, f"/static/app.js?v={asset_version}")
    value = _append_query(value, f"/static/styles.css?v={asset_version}")
    return value


def transform_app_js(source: str) -> str:
    value = source.replace(
        "RAKE 10% · ${fmt(t.rake_cap_bb)}bb CAP",
        "RAKE 5% · ${fmt(t.rake_cap_bb)}bb CAP",
    )
    value = value.replace("rake 10% / 5bb cap", "rake 5% / 3bb cap")
    value = value.replace(
        "pot*0.10,Number(tableState.rake_cap||500)",
        "pot*0.05,Number(tableState.rake_cap||300)",
    )
    value = remove_fast_fold(value)
    if MARKER not in value:
        value = value.rstrip() + f"\n/* {MARKER} */\n"
    return value


def apply_to_build(output_root: Path | str, manifest: dict) -> dict:
    root = Path(output_root)
    index_path = root / "index.html"
    app_path = root / "static/app.js"
    asset_version = int(manifest.get("asset_version", 0))

    index = transform_index(index_path.read_text(encoding="utf-8"), asset_version)
    app_js = transform_app_js(app_path.read_text(encoding="utf-8"))
    index_path.write_text(index, encoding="utf-8", newline="\n")
    app_path.write_text(app_js, encoding="utf-8", newline="\n")

    outputs = dict(manifest.get("outputs") or {})
    outputs["index.html"] = _digest(index)
    outputs["static/app.js"] = _digest(app_js)
    manifest["outputs"] = outputs

    post = dict(manifest.get("post_transforms") or {})
    post["runtime_browser_consolidation"] = MARKER
    manifest["post_transforms"] = post
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


__all__ = [
    "CACHE_QUERY",
    "MARKER",
    "apply_to_build",
    "transform_app_js",
    "transform_index",
]
