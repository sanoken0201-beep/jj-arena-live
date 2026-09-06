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
    with db.connect() as con:
        cols = _cols(db, con, "users")
        if "deleted_at" not in cols:
            con.execute("ALTER TABLE users ADD COLUMN deleted_at TEXT")
        if "deleted_by" not in cols:
            con.execute("ALTER TABLE users ADD COLUMN deleted_by INTEGER")


def _revoke(db, uid: int) -> None:
    if hasattr(db, "delete_user_sessions"):
        db.delete_user_sessions(uid)
    else:
        with db.connect() as con:
            con.execute("DELETE FROM sessions WHERE user_id=?", (uid,))


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
    from admin_console import _audit

    _ensure_schema(db)

    old_users = _route(app, "/api/admin/console/users", "GET")
    old_overview = _route(app, "/api/admin/console/overview", "GET")
    old_point = _route(app, "/api/admin/console/points", "POST")

    @app.get("/api/admin/console/users", include_in_schema=False)
    def users_without_deleted(q: str = "", include_disabled: bool = True, user=Depends(server.admin_user)):
        if old_users is None:
            return []
        rows = old_users.endpoint(q=q, include_disabled=include_disabled, user=user)
        return [r for r in rows if not str(r.get("name") or "").startswith(DELETED_PREFIX)]

    new_users = app.router.routes[-1]
    if old_users is not None:
        _move_route_before(app, new_users, old_users)

    @app.get("/api/admin/console/overview", include_in_schema=False)
    def overview_without_deleted(user=Depends(server.admin_user)):
        if old_overview is None:
            raise HTTPException(500, "admin overview unavailable")
        data = old_overview.endpoint(user=user)
        with db.connect() as con:
            row = con.execute(
                "SELECT COUNT(*) n FROM users WHERE deleted_at IS NOT NULL"
            ).fetchone()
        deleted = int(row["n"] or 0)
        accounts = dict(data.get("accounts") or {})
        accounts["total"] = max(0, int(accounts.get("total") or 0) - deleted)
        accounts["disabled"] = max(0, int(accounts.get("disabled") or 0) - deleted)
        data["accounts"] = accounts
        return data

    new_overview = app.router.routes[-1]
    if old_overview is not None:
        _move_route_before(app, new_overview, old_overview)

    @app.post("/api/admin/console/points", include_in_schema=False)
    def point_guard(p, user=Depends(server.admin_user)):
        if old_point is None:
            raise HTTPException(500, "point endpoint unavailable")
        with db.connect() as con:
            target = con.execute(
                "SELECT deleted_at FROM users WHERE id=?", (p.user_id,)
            ).fetchone()
        if target and target["deleted_at"]:
            raise HTTPException(400, "削除済みアカウントにはポイント操作できません")
        return old_point.endpoint(p=p, user=user)

    # Preserve FastAPI's request-model inference from the existing endpoint.
    if old_point is not None:
        point_guard.__annotations__["p"] = old_point.endpoint.__annotations__.get("p")
        new_point = app.router.routes[-1]
        _move_route_before(app, new_point, old_point)

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

        # Sessions are removed first so the account loses access immediately.
        _revoke(db, uid)

        deleted_at = _now(db)
        tombstone_name = f"{DELETED_PREFIX}{uid}"
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
                sets.append("password_hash=?")
                args.append(db.hash_password(dead_secret))
            # Keep ranking_name intentionally: point/hand history remains attributed
            # correctly even though the login account and personal identifier are gone.
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
