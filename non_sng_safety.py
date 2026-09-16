from __future__ import annotations

"""Browser safety hardening outside Sit&Go.

This post-transform is intentionally narrow: the club point-entry form is a
financial/accounting operation and must permit only one in-flight submission.
It does not alter point formulas, poker rules, or Sit&Go assets/semantics.
"""

import hashlib
import json
from pathlib import Path

MARKER = "v73 non-sng point submission safety 2026-09-17"
CACHE_QUERY = "ns=point-submit-safety-20260917-1"

_POINT_START = "$('#pointForm').addEventListener('submit',async e=>{e.preventDefault();try{"
_POINT_START_NEW = "$('#pointForm').addEventListener('submit',async e=>{e.preventDefault();const form=e.currentTarget;if(form.dataset.jjSubmitting==='1')return;form.dataset.jjSubmitting='1';const submit=form.querySelector('button[type=\"submit\"],button:not([type])');if(submit)submit.disabled=true;try{"
_POINT_END = "await renderPoints()}catch(err){toast(err.message)}});"
_POINT_END_NEW = "await renderPoints()}catch(err){toast(err.message)}finally{delete form.dataset.jjSubmitting;if(submit&&submit.isConnected)submit.disabled=false}});"


def transform_app_js(source: str) -> str:
    if MARKER in source:
        return source
    if source.count(_POINT_START) != 1:
        raise RuntimeError("non-Sit&Go safety drift: point submit start anchor not found exactly once")
    if source.count(_POINT_END) != 1:
        raise RuntimeError("non-Sit&Go safety drift: point submit end anchor not found exactly once")
    source = source.replace(_POINT_START, _POINT_START_NEW, 1)
    source = source.replace(_POINT_END, _POINT_END_NEW, 1)
    # Keep a searchable marker without adding UI or changing behavior.
    return source + f"\n/* {MARKER} */\n"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def apply_to_build(output_root: Path | str, manifest: dict) -> dict:
    root = Path(output_root)
    app_path = root / "static/app.js"
    index_path = root / "index.html"

    app_js = transform_app_js(app_path.read_text(encoding="utf-8"))
    app_path.write_text(app_js, encoding="utf-8", newline="\n")

    index = index_path.read_text(encoding="utf-8")
    asset_version = int(manifest.get("asset_version", 0))
    base = f"/static/app.js?v={asset_version}"
    if CACHE_QUERY not in index:
        if index.count(base) != 1:
            raise RuntimeError("non-Sit&Go safety drift: app.js asset URL not found exactly once")
        start = index.index(base)
        end = index.find('"', start)
        if end < 0:
            raise RuntimeError("non-Sit&Go safety drift: app.js URL terminator missing")
        current = index[start:end]
        separator = '&' if '?' in current else '?'
        index = index[:start] + current + separator + CACHE_QUERY + index[end:]
    index_path.write_text(index, encoding="utf-8", newline="\n")

    outputs = dict(manifest.get("outputs") or {})
    outputs["static/app.js"] = _digest(app_js)
    outputs["index.html"] = _digest(index)
    manifest["outputs"] = outputs
    post = dict(manifest.get("post_transforms") or {})
    post["non_sng_safety"] = MARKER
    manifest["post_transforms"] = post
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


__all__ = ["CACHE_QUERY", "MARKER", "apply_to_build", "transform_app_js"]
