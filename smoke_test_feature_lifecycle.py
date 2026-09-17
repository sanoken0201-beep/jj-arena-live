from __future__ import annotations

import asyncio
import inspect
import os
import sys
import tempfile
from pathlib import Path

from fastapi import HTTPException

from feature_lifecycle import (
    ACTIVE_FEATURES,
    COMPATIBILITY_FEATURES,
    COMPATIBILITY_ROUTE_CONTRACTS,
    RETIRED_FEATURES,
    RETIRED_ROUTE_TOMBSTONES,
    assert_valid,
)


def _assert_direct_410(route) -> None:
    """Verify a retired endpoint is an explicit 410 without TestClient/httpx.

    Render's production build installs only production requirements, so the
    release gate must not depend on the optional HTTP test client stack. Route
    dependencies are intentionally not resolved here; authentication behavior
    is covered by the security/structure suites. This check owns the retirement
    behavior itself.
    """

    endpoint = route.endpoint
    kwargs = {}
    for name, parameter in inspect.signature(endpoint).parameters.items():
        if parameter.default is not inspect.Parameter.empty:
            continue
        kwargs[name] = 1 if name in {"user_id", "uid", "thread_id"} else None

    try:
        if inspect.iscoroutinefunction(endpoint):
            asyncio.run(endpoint(**kwargs))
        else:
            endpoint(**kwargs)
    except HTTPException as exc:
        assert exc.status_code == 410, (getattr(route, "path", ""), exc.status_code)
    else:
        raise AssertionError(f"retired route did not raise HTTP 410: {getattr(route, 'path', '')}")


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
        route = found[0]
        assert getattr(route, "name", "") == route_name, (path, method, getattr(route, "name", ""))
        _assert_direct_410(route)

    # Compatibility-only data/backends stay present for history/stale clients,
    # but their UI destinations remain retired below.
    for method, path in COMPATIBILITY_ROUTE_CONTRACTS:
        assert matches(path, method), (path, method)

    # Canonical admin surface remains the only live account-management API.
    assert matches("/api/admin/console/users", "GET")
    assert matches("/api/admin/console/users/{uid}", "PATCH")
    assert matches("/api/admin/console/users/{uid}/reset-pin", "POST")

    # Public one-table behavior is independently exercised by
    # smoke_test_single_public_table.py in the same production release gate.
    # Keep this lifecycle test focused on ownership/retirement so it remains
    # runnable with production-only dependencies on Render.

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
