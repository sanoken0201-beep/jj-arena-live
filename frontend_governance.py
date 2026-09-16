from __future__ import annotations

"""Final browser-contract cleanup after historical UI transforms.

The historical materialized bundle still contains calls to the pre-console
`/api/admin/members*` endpoints.  The active browser contract is the modern
`/api/admin/console/users*` surface.  Keeping this mapping in one final pass
lets the immutable core and rollback transforms remain untouched while the
served bundle has one canonical admin API.
"""

import hashlib
import json
from pathlib import Path

MARKER = "frontend governance 2026-09-17"
CACHE_QUERY = "fg=admin-api-20260917-1"
ADMIN_OLD = "/admin/members"
ADMIN_NEW = "/admin/console/users"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def transform_app_js(source: str) -> str:
    if MARKER in source:
        return source
    if ADMIN_OLD not in source:
        raise RuntimeError("frontend governance drift: legacy admin API reference missing")
    value = source.replace(ADMIN_OLD, ADMIN_NEW)
    if ADMIN_OLD in value:
        raise RuntimeError("frontend governance failed to retire legacy admin API")
    return value.rstrip() + f"\n/* {MARKER} */\n"


def apply_to_build(output_root: Path | str, manifest: dict) -> dict:
    root = Path(output_root)
    app_path = root / "static/app.js"
    index_path = root / "index.html"

    app_js = transform_app_js(app_path.read_text(encoding="utf-8"))
    app_path.write_text(app_js, encoding="utf-8", newline="\n")

    index = index_path.read_text(encoding="utf-8")
    if CACHE_QUERY not in index:
        needle = f"/static/app.js?v={int(manifest.get('asset_version', 0))}"
        start = index.find(needle)
        if start < 0:
            raise RuntimeError("frontend governance drift: app.js URL missing")
        end = index.find('"', start)
        if end < 0:
            raise RuntimeError("frontend governance drift: app.js URL terminator missing")
        current = index[start:end]
        index = index[:start] + current + "&" + CACHE_QUERY + index[end:]
    index_path.write_text(index, encoding="utf-8", newline="\n")

    outputs = dict(manifest.get("outputs") or {})
    outputs["static/app.js"] = _digest(app_js)
    outputs["index.html"] = _digest(index)
    manifest["outputs"] = outputs
    post = dict(manifest.get("post_transforms") or {})
    post["frontend_governance"] = MARKER
    manifest["post_transforms"] = post
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


__all__ = ["ADMIN_NEW", "ADMIN_OLD", "CACHE_QUERY", "MARKER", "apply_to_build", "transform_app_js"]
