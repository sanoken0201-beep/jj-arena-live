from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from feature_lifecycle import (
    ACTIVE_FEATURES,
    COMPATIBILITY_FEATURES,
    COMPATIBILITY_ROUTE_CONTRACTS,
    RETIRED_FEATURES,
    RETIRED_ROUTE_TOMBSTONES,
    assert_valid,
)


def main() -> None:
    assert_valid()
    assert "admin.console" in ACTIVE_FEATURES
    assert "ring.public_table_a" in ACTIVE_FEATURES
    assert "sitngo.root_integration" in ACTIVE_FEATURES
    assert "ring.internal_table_b" in COMPATIBILITY_FEATURES
    assert "schedule.backend_data" in COMPATIBILITY_FEATURES
    assert "discussion.backend_data" in COMPATIBILITY_FEATURES
    assert "nav.schedule" in RETIRED_FEATURES
    assert "nav.discussion" in RETIRED_FEATURES
    assert "auth.email_login" in RETIRED_FEATURES

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

    # The rollback oracle is retained on disk but must not participate in the
    # production import path.
    assert (Path(app.__file__).resolve().parent / "app_legacy.py").is_file()
    assert "app_legacy" not in sys.modules

    routes = list(app.app.router.routes)

    def matches(path: str, method: str):
        return [
            route
            for route in routes
            if str(getattr(route, "path", "")) == path
            and method in set(getattr(route, "methods", set()) or set())
        ]

    # Retired routes may exist only as explicit tombstones. A later patch must
    # not silently revive a second admin/auth implementation behind the same URL.
    for method, path, route_name in RETIRED_ROUTE_TOMBSTONES:
        found = matches(path, method)
        assert len(found) == 1, (path, method, len(found))
        assert getattr(found[0], "name", "") == route_name, (path, method, getattr(found[0], "name", ""))

    # Compatibility-only data/backends stay present for history/stale clients,
    # but their UI destinations remain retired below.
    for method, path in COMPATIBILITY_ROUTE_CONTRACTS:
        assert matches(path, method), (path, method)

    # Canonical admin surface remains the only live account-management API.
    assert matches("/api/admin/console/users", "GET")
    assert matches("/api/admin/console/users/{uid}", "PATCH")
    assert matches("/api/admin/console/users/{uid}/reset-pin", "POST")

    with TestClient(app.app, base_url="https://testserver") as client:
        # Retired email auth is an explicit 410 rather than a hidden alternate
        # login path.
        assert client.post("/api/auth/signup").status_code == 410
        assert client.post("/api/auth/login").status_code == 410

        # Legacy admin tombstones remain protected before revealing retirement.
        assert client.get("/api/admin/members").status_code == 401
        login = client.post("/api/auth/pin", json={"name": "セイリカンリ", "pin": "654321"})
        assert login.status_code == 200, login.text
        assert client.get("/api/admin/members").status_code == 410

        # One public Ring table is the product contract even though historical
        # Table B remains in storage for rollback/data compatibility.
        table_list = client.get("/api/tables")
        assert table_list.status_code == 200, table_list.text
        public_tables = table_list.json()
        assert len(public_tables) == 1, public_tables
        assert public_tables[0]["id"] == "jj-table-a", public_tables
        assert all(row.get("id") != "jj-table-b" for row in public_tables)

        # Historical data reads remain available to an authenticated stale
        # client without making these destinations active again.
        assert client.get("/api/schedules").status_code == 200
        assert client.get("/api/threads").status_code == 200

    build_assets()
    manifest = validate_built_assets(BUILD_ROOT)
    assert manifest.get("browser_output_contract") == "canonical-prebuilt-v1"

    index = (BUILD_ROOT / "index.html").read_text(encoding="utf-8")
    js = (BUILD_ROOT / "static/app.js").read_text(encoding="utf-8")

    # Retired top-level destinations must stay absent from the canonical browser
    # output. Historical backend data may still feed active surfaces such as
    # Announcements without restoring dedicated navigation.
    assert 'data-view="schedule"' not in index
    assert 'data-view="discussion"' not in index
    assert "if(v==='members'){location.assign('/admin');return}" in js

    print("JJ_FEATURE_LIFECYCLE_OK")


if __name__ == "__main__":
    main()
