from __future__ import annotations

import os
import tempfile
from pathlib import Path

from feature_lifecycle import ACTIVE, COMPATIBILITY_RETAINED, RETIRED
from frontend_build_pipeline import build_production_frontend


def main() -> None:
    assert ACTIVE.isdisjoint(COMPATIBILITY_RETAINED)
    assert ACTIVE.isdisjoint(RETIRED)
    assert set(COMPATIBILITY_RETAINED).isdisjoint(RETIRED)
    assert "admin.legacy_members_api" in RETIRED
    assert "schedule.backend" in COMPATIBILITY_RETAINED
    assert "discussion.backend" in COMPATIBILITY_RETAINED
    assert "ring.single_public_table" in ACTIVE

    with tempfile.TemporaryDirectory(prefix="jj-feature-lifecycle-") as directory:
        root = Path(directory) / "assets"
        build_production_frontend(root)
        index = (root / "index.html").read_text(encoding="utf-8")
        app_js = (root / "static/app.js").read_text(encoding="utf-8")
        css = (root / "static/styles.css").read_text(encoding="utf-8")

        # Retired primary navigation must not silently return.
        assert 'data-view="schedule"' not in index
        assert 'data-view="discussion"' not in index
        assert '.nav[data-view="schedule"]' in css
        assert '.nav[data-view="discussion"]' in css

        # Compatibility data paths remain deliberately readable by the merged
        # Announcements/history surfaces.
        assert "api('/schedules')" in app_js
        assert "api('/threads')" in app_js

        # Browser code must use the modern management contract exclusively.
        assert "/admin/members" not in app_js
        assert "/admin/console/users" in app_js

    # Route-level lifecycle contract, using an isolated local DB.
    work = Path(tempfile.mkdtemp(prefix="jj-feature-routes-"))
    os.environ.pop("DATABASE_URL", None)
    os.environ["JJ_DB_PATH"] = str(work / "features.sqlite3")
    os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"
    os.environ.pop("RENDER", None)
    import admin_copy_patch
    admin_copy_patch.apply = lambda _path: None
    import app as production

    routes = [
        (str(getattr(route, "path", "") or ""), set(getattr(route, "methods", set()) or set()))
        for route in production.app.router.routes
    ]
    assert any(path == "/api/schedules" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/threads" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/admin/console/users" and "GET" in methods for path, methods in routes)
    assert any(path == "/api/admin/members" and "GET" in methods for path, methods in routes)

    print("JJ_FEATURE_LIFECYCLE_OK")


if __name__ == "__main__":
    main()
