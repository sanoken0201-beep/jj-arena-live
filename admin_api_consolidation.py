from __future__ import annotations

"""Retire the historical `/api/admin/members*` surface.

The modern admin contract lives under `/api/admin/console/*`.  The immutable
v1.24.4 core still registers the older member-management routes, including an
older PIN reset path with weaker admin-to-admin protections.  Production keeps
those core files untouched, so this integration layer removes the legacy
routes after the modern console is installed and replaces them with authenticated
410 tombstones for stale browser bundles.
"""

from fastapi import Depends, HTTPException

LEGACY_PATHS = {
    ("GET", "/api/admin/members"),
    ("PATCH", "/api/admin/members/{user_id}"),
    ("POST", "/api/admin/members/{user_id}/reset-pin"),
}


def _remove_legacy_routes(app) -> None:
    retained = []
    for route in app.router.routes:
        path = str(getattr(route, "path", "") or "")
        methods = set(getattr(route, "methods", set()) or set())
        if any(path == legacy_path and method in methods for method, legacy_path in LEGACY_PATHS):
            continue
        retained.append(route)
    app.router.routes[:] = retained


def install(app, server) -> None:
    if getattr(app.state, "jj_admin_api_consolidated", False):
        return
    app.state.jj_admin_api_consolidated = True

    _remove_legacy_routes(app)

    def retired(user=Depends(server.admin_user)):
        raise HTTPException(
            status_code=410,
            detail="旧ユーザー管理APIは廃止されました。/admin の管理コンソールを使用してください",
        )

    def retired_user(user_id: int, user=Depends(server.admin_user)):
        return retired(user)

    app.add_api_route(
        "/api/admin/members",
        retired,
        methods=["GET"],
        include_in_schema=False,
        name="retired_admin_members",
    )
    app.add_api_route(
        "/api/admin/members/{user_id}",
        retired_user,
        methods=["PATCH"],
        include_in_schema=False,
        name="retired_admin_member_update",
    )
    app.add_api_route(
        "/api/admin/members/{user_id}/reset-pin",
        retired_user,
        methods=["POST"],
        include_in_schema=False,
        name="retired_admin_member_pin_reset",
    )


__all__ = ["LEGACY_PATHS", "install"]
