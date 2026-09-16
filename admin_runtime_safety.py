from __future__ import annotations

"""Preserve live-ring safety when account management moves to the admin console.

The historical `/api/admin/members/{id}` endpoint revoked sessions and removed a
suspended player from ring tables (or marked an in-hand player to leave after
that hand).  The modern console originally revoked sessions only.  API
consolidation must not weaken that runtime behavior, so this wrapper applies the
same ring transition to the canonical console PATCH endpoint.

Sit&Go is intentionally outside this module.
"""

import inspect


def _route(app, path: str, method: str):
    method = method.upper()
    for route in app.router.routes:
        if getattr(route, "path", None) == path and method in (getattr(route, "methods", None) or set()):
            return route
    return None


async def _call(endpoint, **kwargs):
    result = endpoint(**kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


def install(app, server, db) -> None:
    if getattr(app.state, "jj_admin_runtime_safety_installed", False):
        return
    app.state.jj_admin_runtime_safety_installed = True

    route = _route(app, "/api/admin/console/users/{uid}", "PATCH")
    if route is None or not getattr(route, "dependant", None):
        raise RuntimeError("canonical admin user update route missing")

    original_call = route.dependant.call
    original_endpoint = route.endpoint

    async def guarded_update(uid, p, user):
        result = await _call(original_call, uid=uid, p=p, user=user)
        if getattr(p, "disabled", None) is not True:
            return result

        user_id = int(uid)
        changed_tables: list[str] = []
        for table_id, _ in db.FIXED_TABLES:
            async with server.get_table_lock(table_id):
                state = server.load_table(table_id)
                player = next(
                    (seat for seat in state.get("seats", []) if int(seat.get("user_id", -1)) == user_id),
                    None,
                )
                if not player:
                    continue

                if state.get("status") == "playing" and bool(player.get("in_hand")):
                    player["leave_after_hand"] = True
                    player["ready"] = False
                else:
                    state["seats"] = [
                        seat for seat in state.get("seats", [])
                        if int(seat.get("user_id", -1)) != user_id
                    ]
                    server.table_presence.pop((table_id, user_id), None)
                server.save_table(state)
                changed_tables.append(table_id)

        for table_id in changed_tables:
            await server.hub.broadcast(table_id)
        return result

    route.dependant.call = guarded_update
    route.endpoint = guarded_update
    route._jj_admin_runtime_original_endpoint = original_endpoint


__all__ = ["install"]
