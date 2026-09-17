from __future__ import annotations

from fastapi import Depends, HTTPException


LEGACY_MUTATIONS = (
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
    """Retire duplicate legacy admin write APIs.

    Read-only ``GET /api/admin/members`` remains temporarily for old cached
    clients. All account mutations are canonical under ``/api/admin/console``.
    Keeping a single write surface prevents future authorization and audit
    behavior from drifting between old and new endpoints.
    """
    if getattr(app.state, "jj_admin_api_consolidated", False):
        return
    app.state.jj_admin_api_consolidated = True

    for method, path in LEGACY_MUTATIONS:
        _remove_route(app, method, path)

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


__all__ = ["LEGACY_MUTATIONS", "install"]
