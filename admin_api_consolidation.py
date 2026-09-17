from __future__ import annotations

from fastapi import Depends, HTTPException


LEGACY_ADMIN_ROUTES = (
    ("GET", "/api/admin/members"),
    ("PATCH", "/api/admin/members/{user_id}"),
    ("POST", "/api/admin/members/{user_id}/reset-pin"),
)


def _remove_route(app, method: str, path: str) -> None:
    method = method.upper()
    app.router.routes[:] = [
        route
        for route in app.router.routes
        if not (
            str(getattr(route, "path", "")) == path
            and method in set(getattr(route, "methods", set()) or set())
        )
    ]


def install(app, server) -> None:
    """Retire the duplicate legacy member-admin API surface.

    The canonical administration surface is now exclusively ``/admin`` backed
    by ``/api/admin/console/...``. Old cached clients receive an authenticated
    410 response instead of silently using a second authorization/audit path.
    This keeps account reads and writes under one contract and prevents future
    security fixes from drifting between two admin implementations.
    """
    if getattr(app.state, "jj_admin_api_consolidated", False):
        return
    app.state.jj_admin_api_consolidated = True

    for method, path in LEGACY_ADMIN_ROUTES:
        _remove_route(app, method, path)

    def retired(detail: str):
        async def endpoint(user=Depends(server.admin_user)):
            raise HTTPException(410, detail)
        return endpoint

    async def retired_member_patch(user_id: int, user=Depends(server.admin_user)):
        raise HTTPException(
            410,
            "旧ユーザー管理APIは廃止されました。管理コンソール /admin を利用してください",
        )

    async def retired_member_pin_reset(user_id: int, user=Depends(server.admin_user)):
        raise HTTPException(
            410,
            "旧PINリセットAPIは廃止されました。管理コンソール /admin を利用してください",
        )

    app.add_api_route(
        "/api/admin/members",
        retired("旧ユーザー一覧APIは廃止されました。管理コンソール /admin を利用してください"),
        methods=["GET"],
        name="retired_legacy_member_list",
        include_in_schema=False,
    )
    app.add_api_route(
        "/api/admin/members/{user_id}",
        retired_member_patch,
        methods=["PATCH"],
        name="retired_legacy_member_patch",
        include_in_schema=False,
    )
    app.add_api_route(
        "/api/admin/members/{user_id}/reset-pin",
        retired_member_pin_reset,
        methods=["POST"],
        name="retired_legacy_member_pin_reset",
        include_in_schema=False,
    )


__all__ = ["LEGACY_ADMIN_ROUTES", "install"]
