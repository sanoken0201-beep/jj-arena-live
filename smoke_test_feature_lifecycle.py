from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from feature_lifecycle import ACTIVE, COMPATIBILITY_ONLY, RETIRED, assert_disjoint


def main() -> None:
    assert_disjoint()
    assert "admin.console" in ACTIVE
    assert "schedule.backend_data" in COMPATIBILITY_ONLY
    assert "nav.schedule" in RETIRED
    assert "nav.discussion" in RETIRED

    work = Path(tempfile.mkdtemp(prefix="jj-feature-lifecycle-"))
    os.environ.pop("DATABASE_URL", None)
    os.environ["JJ_DB_PATH"] = str(work / "lifecycle.sqlite3")
    os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"
    os.environ["JJ_ADMIN_NAME"] = "セイリカンリ"
    os.environ["JJ_ADMIN_PIN"] = "654321"
    os.environ["RENDER"] = "1"

    import app
    from build_served_assets import main as build_assets
    from served_assets import BUILD_ROOT, validate_built_assets

    routes = list(app.app.router.routes)

    def matches(path: str, method: str):
        return [
            route
            for route in routes
            if str(getattr(route, "path", "")) == path
            and method in set(getattr(route, "methods", set()) or set())
        ]

    # All legacy member-admin routes are tombstones, not secondary product APIs.
    expected_legacy = {
        ("/api/admin/members", "GET"): "retired_legacy_member_list",
        ("/api/admin/members/{user_id}", "PATCH"): "retired_legacy_member_patch",
        ("/api/admin/members/{user_id}/reset-pin", "POST"): "retired_legacy_member_pin_reset",
    }
    for (path, method), route_name in expected_legacy.items():
        found = matches(path, method)
        assert len(found) == 1, (path, method, len(found))
        assert getattr(found[0], "name", "") == route_name

    # Canonical admin surface remains available.
    assert matches("/api/admin/console/users", "GET")
    assert matches("/api/admin/console/users/{uid}", "PATCH")
    assert matches("/api/admin/console/users/{uid}/reset-pin", "POST")

    # Tombstones require admin authentication; anonymous callers must not learn
    # data from the old API surface.
    with TestClient(app.app, base_url="https://testserver") as client:
        assert client.get("/api/admin/members").status_code == 401
        login = client.post("/api/auth/pin", json={"name": "セイリカンリ", "pin": "654321"})
        assert login.status_code == 200, login.text
        retired = client.get("/api/admin/members")
        assert retired.status_code == 410, retired.text

    build_assets()
    manifest = validate_built_assets(BUILD_ROOT)
    assert manifest.get("browser_output_contract") == "canonical-prebuilt-v1"

    index = (BUILD_ROOT / "index.html").read_text(encoding="utf-8")
    js = (BUILD_ROOT / "static/app.js").read_text(encoding="utf-8")

    # Retired top-level destinations stay hidden, while retained backend/data
    # remains available to announcements/history compatibility.
    assert 'data-view="schedule"' not in index
    assert 'data-view="discussion"' not in index
    assert "if(v==='members'){location.assign('/admin');return}" in js

    # app.py is transport-only for browser assets: deterministic mutations live
    # in the build pipeline and the served app.js carries the consolidation mark.
    app_source = Path(app.__file__).read_text(encoding="utf-8")
    assert "remove_fast_fold" not in app_source
    assert "RAKE 10% · ${fmt(t.rake_cap_bb)}bb CAP" not in app_source
    assert "pot*0.10,Number(tableState.rake_cap||500)" not in app_source
    assert "v75 runtime browser consolidation 2026-09-17" in js
    assert "check_fold" not in js

    print("JJ_FEATURE_LIFECYCLE_OK")


if __name__ == "__main__":
    main()
