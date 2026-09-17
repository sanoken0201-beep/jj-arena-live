from __future__ import annotations

import hashlib
import json
from pathlib import Path

MARKER = "v74 structure consolidation 2026-09-17"
CACHE_QUERY = "sc=structure-consolidation-20260917-1"

_OLD = "if(v==='members')return renderMembers();"
_NEW = "if(v==='members'){location.assign('/admin');return}"


def transform_app_js(source: str) -> str:
    if MARKER in source:
        return source
    if source.count(_OLD) != 1:
        raise RuntimeError("structure consolidation drift: members route anchor missing")
    source = source.replace(_OLD, _NEW, 1)
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
        start = index.find(base)
        if start < 0:
            raise RuntimeError("structure consolidation drift: app.js URL missing")
        end = index.find('"', start)
        if end < 0:
            raise RuntimeError("structure consolidation drift: app.js URL terminator missing")
        current = index[start:end]
        separator = "&" if "?" in current else "?"
        index = index[:start] + current + separator + CACHE_QUERY + index[end:]
    index_path.write_text(index, encoding="utf-8", newline="\n")

    outputs = dict(manifest.get("outputs") or {})
    outputs["static/app.js"] = _digest(app_js)
    outputs["index.html"] = _digest(index)
    manifest["outputs"] = outputs
    post = dict(manifest.get("post_transforms") or {})
    post["structure_consolidation"] = MARKER
    manifest["post_transforms"] = post
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


__all__ = ["CACHE_QUERY", "MARKER", "apply_to_build", "transform_app_js"]
