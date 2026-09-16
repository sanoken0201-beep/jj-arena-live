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
    app_js = transform_app_js(app_path.read_text(encoding="utf-8"))
    app_path.write_text(app_js, encoding="utf-8", newline="\n")

    outputs = dict(manifest.get("outputs") or {})
    outputs["static/app.js"] = _digest(app_js)
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


__all__ = ["ADMIN_NEW", "ADMIN_OLD", "MARKER", "apply_to_build", "transform_app_js"]
