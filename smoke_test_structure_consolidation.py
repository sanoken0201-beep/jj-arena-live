from __future__ import annotations

import os
import tempfile
from pathlib import Path


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="jj-structure-"))
    os.environ.pop("DATABASE_URL", None)
    os.environ["JJ_DB_PATH"] = str(work / "structure.sqlite3")
    os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"
    os.environ["JJ_ADMIN_NAME"] = "コウゾウカンリ"
    os.environ["RENDER"] = "1"

    import app
    from browser_asset_pipeline import PIPELINE_VERSION, POST_BUILD_STAGES
    from build_served_assets import main as build_assets
    from served_assets import BUILD_ROOT, validate_built_assets

    # Every legacy member-admin route is now an authenticated tombstone.
    # Canonical reads and writes live only under /api/admin/console.
    routes = list(app.app.router.routes)

    def matches(path: str, method: str):
        return [
            route
            for route in routes
            if str(getattr(route, "path", "")) == path
            and method in set(getattr(route, "methods", set()) or set())
        ]

    legacy_list = matches("/api/admin/members", "GET")
    legacy_patch = matches("/api/admin/members/{user_id}", "PATCH")
    legacy_reset = matches("/api/admin/members/{user_id}/reset-pin", "POST")
    assert len(legacy_list) == 1
    assert len(legacy_patch) == 1
    assert len(legacy_reset) == 1
    assert getattr(legacy_list[0], "name", "") == "retired_legacy_member_list"
    assert getattr(legacy_patch[0], "name", "") == "retired_legacy_member_patch"
    assert getattr(legacy_reset[0], "name", "") == "retired_legacy_member_pin_reset"

    assert matches("/api/admin/console/users", "GET"), "canonical user list missing"
    assert matches("/api/admin/console/users/{uid}", "PATCH"), "canonical user update missing"
    assert matches("/api/admin/console/users/{uid}/reset-pin", "POST"), "canonical PIN reset missing"

    build_assets()
    manifest = validate_built_assets(BUILD_ROOT)
    assert manifest.get("pipeline_version") == PIPELINE_VERSION
    expected = [name for name, _ in POST_BUILD_STAGES]
    assert manifest.get("pipeline_stages") == expected

    js = (BUILD_ROOT / "static/app.js").read_text(encoding="utf-8")
    assert "if(v==='members'){location.assign('/admin');return}" in js
    assert "v74 structure consolidation 2026-09-17" in js

    print("JJ_STRUCTURE_CONSOLIDATION_OK")


if __name__ == "__main__":
    main()
