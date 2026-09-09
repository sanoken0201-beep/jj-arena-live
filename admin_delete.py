from __future__ import annotations

import secrets
import uuid
from fastapi import Depends, HTTPException

DELETED_PREFIX = "削除済みユーザー#"


def _cols(db, con, table: str) -> set[str]:
    if getattr(db, "IS_POSTGRES", False):
        rows = con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=?",
            (table,),
        ).fetchall()
        return {str(r["column_name"]) for r in rows}
    return {str(r["name"]) for r in con.execute(f"PRAGMA table_info({table})").fetchall()}


def _now(db) -> str:
    try:
        return db.utcnow()
    except Exception:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()


def _ensure_schema(db) -> None:
    deleted_by_type = "BIGINT" if getattr(db, "IS_POSTGRES", False) else "INTEGER"
    with db.connect() as con:
        cols = _cols(db, con, "users")
        if "deleted_at" not in cols:
            con.execute("ALTER TABLE users ADD COLUMN deleted_at TEXT")
        if "deleted_by" not in cols:
            con.execute(f"ALTER TABLE users ADD COLUMN deleted_by {deleted_by_type}")

        # Backfill tombstones created by any older deletion implementation. The
        # name prefix is only used for this migration; runtime visibility is
        # based on deleted_at, not on display text.
        con.execute(
            "UPDATE users SET deleted_at=? WHERE deleted_at IS NULL AND name LIKE ?",
            (_now(db), f"{DELETED_PREFIX}%"),
        )
        con.execute(
            "UPDATE users SET disabled=1,club_verified=0 WHERE name LIKE ?",
            (f"{DELETED_PREFIX}%",),
        )


def _revoke(db, uid: int) -> None:
    if hasattr(db, "delete_user_sessions"):
        db.delete_user_sessions(uid)
    else:
        with db.connect() as con:
            con.execute("DELETE FROM sessions WHERE user_id=?", (uid,))


def _deleted_ids(db) -> set[int]:
    with db.connect() as con:
        rows = con.execute("SELECT id FROM users WHERE deleted_at IS NOT NULL").fetchall()
    return {int(r["id"]) for r in rows}


def _require_live_user(db, uid: int) -> None:
    with db.connect() as con:
        row = con.execute("SELECT id,deleted_at FROM users WHERE id=?", (uid,)).fetchone()
    # A tombstone is deliberately indistinguishable from a missing account to
    # account-management APIs.
    if not row or row["deleted_at"]:
        raise HTTPException(404, "user not found")


def _move_route_before(app, new_route, old_route) -> None:
    routes = app.router.routes
    if new_route not in routes or old_route not in routes:
        return
    routes.remove(new_route)
    routes.insert(routes.index(old_route), new_route)


def _route(app, path: str, method: str):
    method = method.upper()
    for route in app.router.routes:
        if getattr(route, "path", None) == path and method in (getattr(route, "methods", None) or set()):
            return route
    return None


def install_account_deletion(app) -> None:
    if getattr(app.state, "jj_account_deletion_installed", False):
        return
    app.state.jj_account_deletion_installed = True

    import db
    import server
    from admin_console import AdminPinReset, AdminPointIn, AdminUserPatch, _audit

    _ensure_schema(db)

    old_users = _route(app, "/api/admin/console/users", "GET")
    old_overview = _route(app, "/api/admin/console/overview", "GET")
    old_point = _route(app, "/api/admin/console/points", "POST")
    old_update = _route(app, "/api/admin/console/users/{uid}", "PATCH")
    old_revoke = _route(app, "/api/admin/console/users/{uid}/revoke-sessions", "POST")
    old_reset = _route(app, "/api/admin/console/users/{uid}/reset-pin", "POST")
    old_legacy_members = _route(app, "/api/admin/members", "GET")
    old_legacy_reset = _route(app, "/api/admin/members/{user_id}/reset-pin", "POST")

    @app.get("/api/admin/console/users", include_in_schema=False)
    def users_without_deleted(q: str = "", include_disabled: bool = True, user=Depends(server.admin_user)):
        if old_users is None:
            return []
        rows = old_users.endpoint(q=q, include_disabled=include_disabled, user=user)
        deleted = _deleted_ids(db)
        return [r for r in rows if int(r.get("id") or 0) not in deleted]

    new_users = app.router.routes[-1]
    if old_users is not None:
        _move_route_before(app, new_users, old_users)

    # Keep the legacy administrator member API consistent with the current UI.
    if old_legacy_members is not None:
        @app.get("/api/admin/members", include_in_schema=False)
        def legacy_members_without_deleted(user=Depends(server.admin_user)):
            rows = old_legacy_members.endpoint(user=user)
            deleted = _deleted_ids(db)
            return [r for r in rows if int(r.get("id") or 0) not in deleted]

        _move_route_before(app, app.router.routes[-1], old_legacy_members)

    @app.get("/api/admin/console/overview", include_in_schema=False)
    def overview_without_deleted(user=Depends(server.admin_user)):
        if old_overview is None:
            raise HTTPException(500, "admin overview unavailable")
        data = old_overview.endpoint(user=user)
        with db.connect() as con:
            row = con.execute(
                """SELECT COUNT(*) total,
                          SUM(CASE WHEN COALESCE(disabled,0)=0 THEN 1 ELSE 0 END) active,
                          SUM(CASE WHEN COALESCE(disabled,0)<>0 THEN 1 ELSE 0 END) disabled,
                          SUM(CASE WHEN COALESCE(club_verified,0)<>0 THEN 1 ELSE 0 END) verified
                   FROM users WHERE deleted_at IS NULL"""
            ).fetchone()
        data["accounts"] = {
            "total": int(row["total"] or 0),
            "active": int(row["active"] or 0),
            "disabled": int(row["disabled"] or 0),
            "verified": int(row["verified"] or 0),
        }
        for item in data.get("recent_audit") or []:
            if str(item.get("target_name") or "").startswith(DELETED_PREFIX):
                item["target_name"] = "削除済みアカウント"
        return data

    new_overview = app.router.routes[-1]
    if old_overview is not None:
        _move_route_before(app, new_overview, old_overview)

    @app.post("/api/admin/console/points", include_in_schema=False)
    def point_guard(p: AdminPointIn, user=Depends(server.admin_user)):
        if old_point is None:
            raise HTTPException(500, "point endpoint unavailable")
        _require_live_user(db, int(p.user_id))
        return old_point.endpoint(p=p, user=user)

    new_point = app.router.routes[-1]
    if old_point is not None:
        _move_route_before(app, new_point, old_point)

    if old_update is not None:
        @app.patch("/api/admin/console/users/{uid}", include_in_schema=False)
        def update_guard(uid: int, p: AdminUserPatch, user=Depends(server.admin_user)):
            _require_live_user(db, uid)
            return old_update.endpoint(uid=uid, p=p, user=user)

        _move_route_before(app, app.router.routes[-1], old_update)

    if old_revoke is not None:
        @app.post("/api/admin/console/users/{uid}/revoke-sessions", include_in_schema=False)
        def revoke_guard(uid: int, user=Depends(server.admin_user)):
            _require_live_user(db, uid)
            return old_revoke.endpoint(uid=uid, user=user)

        _move_route_before(app, app.router.routes[-1], old_revoke)

    if old_reset is not None:
        @app.post("/api/admin/console/users/{uid}/reset-pin", include_in_schema=False)
        def reset_guard(uid: int, p: AdminPinReset, user=Depends(server.admin_user)):
            _require_live_user(db, uid)
            return old_reset.endpoint(uid=uid, p=p, user=user)

        _move_route_before(app, app.router.routes[-1], old_reset)

    # The compatibility reset route uses server.ResetPinIn. Accept raw JSON here
    # and instantiate that exact model before delegating, while still refusing a
    # tombstone user id.
    reset_model = getattr(server, "ResetPinIn", None)
    if old_legacy_reset is not None and reset_model is not None:
        from fastapi import Body

        @app.post("/api/admin/members/{user_id}/reset-pin", include_in_schema=False)
        def legacy_reset_guard(
            user_id: int,
            payload: dict = Body(...),
            user=Depends(server.admin_user),
        ):
            _require_live_user(db, user_id)
            model = reset_model(**payload)
            return old_legacy_reset.endpoint(user_id=user_id, payload=model, user=user)

        _move_route_before(app, app.router.routes[-1], old_legacy_reset)

    @app.delete("/api/admin/console/users/{uid}", include_in_schema=False)
    def delete_account(uid: int, user=Depends(server.admin_user)):
        actor_id = int(user["id"])
        if uid == actor_id:
            raise HTTPException(400, "現在操作中の管理者アカウントは削除できません")

        with db.connect() as con:
            target = con.execute(
                "SELECT id,name,role,ranking_name,deleted_at FROM users WHERE id=?",
                (uid,),
            ).fetchone()
            if not target:
                raise HTTPException(404, "user not found")
            if target["role"] == "admin":
                raise HTTPException(400, "管理者アカウントは削除できません")
            if target["deleted_at"]:
                raise HTTPException(409, "このアカウントはすでに削除済みです")

        _revoke(db, uid)

        deleted_at = _now(db)
        tombstone_name = f"{DELETED_PREFIX}{uid}"
        # Free the deterministic name-derived login identity for a future
        # re-registration without reusing the old account row.
        tombstone_email = f"deleted-{uid}-{uuid.uuid4().hex}@jj.invalid"
        dead_secret = secrets.token_urlsafe(40)

        with db.connect() as con:
            cols = _cols(db, con, "users")
            sets = ["name=?", "disabled=1", "club_verified=0", "admin_note=''", "deleted_at=?", "deleted_by=?"]
            args = [tombstone_name, deleted_at, actor_id]
            if "email" in cols:
                sets.append("email=?")
                args.append(tombstone_email)
            if "password_hash" in cols:
                # Destroy the old PIN hash. A future account with the same
                # normalized name gets an independent hash from its new PIN.
                sets.append("password_hash=?")
                args.append(db.hash_password(dead_secret))
            # ranking_name is deliberately preserved so historical rankings,
            # point ledgers and online-hand results remain attributable.
            con.execute(f"UPDATE users SET {','.join(sets)} WHERE id=?", args + [uid])

        _audit(
            db,
            actor_id,
            "user.delete",
            uid,
            deleted_user_id=uid,
            ranking_name=str(target["ranking_name"] or ""),
            deletion_mode="tombstone",
        )
        return {"ok": True, "user_id": uid, "deleted_at": deleted_at}
