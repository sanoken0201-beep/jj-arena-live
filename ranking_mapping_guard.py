from __future__ import annotations

"""Guard administrator ranking-name mappings without rewriting the core/admin API.

Historical duplicate mappings are surfaced by the admin overview and may need to
be cleaned up manually. This guard does not make unrelated edits impossible for
those accounts. It only prevents an administrator from creating a *new* active
duplicate mapping or re-enabling an account into a duplicate mapping.
"""

from fastapi import HTTPException


def _route(app, path: str, method: str):
    method = method.upper()
    for route in app.router.routes:
        if getattr(route, "path", None) == path and method in (getattr(route, "methods", None) or set()):
            return route
    return None


def install(app, db) -> None:
    if getattr(app.state, "jj_ranking_mapping_guard_installed", False):
        return
    app.state.jj_ranking_mapping_guard_installed = True

    route = _route(app, "/api/admin/console/users/{uid}", "PATCH")
    if route is None or not getattr(route, "dependant", None):
        raise RuntimeError("admin user update route missing for ranking mapping guard")

    original_call = route.dependant.call
    original_endpoint = route.endpoint

    def guarded_update(uid, p, user):
        with db.connect() as con:
            row = con.execute(
                "SELECT id,name,disabled,ranking_name,deleted_at FROM users WHERE id=?",
                (uid,),
            ).fetchone()

        # Preserve the existing deleted/missing-account behavior exactly. The
        # account-deletion guard wrapped this endpoint first and remains the
        # authority for the resulting 404.
        if not row or row["deleted_at"]:
            return original_call(uid=uid, p=p, user=user)

        current_mapping = str(row["ranking_name"] or row["name"])
        requested_mapping = None
        if getattr(p, "ranking_name", None) is not None:
            requested_mapping = str(p.ranking_name).strip()
        effective_mapping = requested_mapping if requested_mapping else current_mapping

        currently_disabled = bool(int(row["disabled"] or 0))
        requested_disabled = getattr(p, "disabled", None)
        resulting_disabled = currently_disabled if requested_disabled is None else bool(requested_disabled)

        mapping_changed = bool(requested_mapping) and requested_mapping != current_mapping
        re_enabling = currently_disabled and requested_disabled is False

        if not resulting_disabled and (mapping_changed or re_enabling):
            with db.connect() as con:
                conflict = con.execute(
                    """SELECT id,name FROM users
                       WHERE id<>?
                         AND deleted_at IS NULL
                         AND COALESCE(disabled,0)=0
                         AND COALESCE(NULLIF(ranking_name,''),name)=?
                       ORDER BY id LIMIT 1""",
                    (uid, effective_mapping),
                ).fetchone()
            if conflict:
                raise HTTPException(
                    409,
                    f"ランキング名「{effective_mapping}」は有効な別アカウント「{conflict['name']}」で使用中です。先に紐付けを整理してください。",
                )

        return original_call(uid=uid, p=p, user=user)

    route.dependant.call = guarded_update
    route.endpoint = guarded_update
    route._jj_ranking_mapping_original_endpoint = original_endpoint
