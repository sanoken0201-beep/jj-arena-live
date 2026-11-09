"""Persistent account bans, independent of temporary suspension and soft deletion.

A permanent ban survives account deletion and blocks reusing recorded login and
ranking aliases. It does not prove that a newly named account belongs to the
same person; that requires an independent member-verification process.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

import account_name_safety


class BanRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class LiftRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


def _route(app, path, method):
    return next(
        (r for r in app.router.routes
         if getattr(r, "path", None) == path
         and method in (getattr(r, "methods", None) or set())),
        None,
    )


def ensure_schema(db):
    id_type = "BIGSERIAL PRIMARY KEY" if getattr(db, "IS_POSTGRES", False) else "INTEGER PRIMARY KEY AUTOINCREMENT"
    uid_type = "BIGINT" if getattr(db, "IS_POSTGRES", False) else "INTEGER"
    with db.connect() as con:
        con.execute(
            f"""CREATE TABLE IF NOT EXISTS permanent_bans (
                id {id_type},
                user_id {uid_type} NOT NULL REFERENCES users(id),
                display_name TEXT NOT NULL,
                ranking_name TEXT NOT NULL,
                login_key TEXT NOT NULL,
                ranking_key TEXT NOT NULL,
                reason TEXT NOT NULL,
                banned_by {uid_type} NOT NULL REFERENCES users(id),
                banned_at TEXT NOT NULL,
                lifted_by {uid_type} REFERENCES users(id),
                lifted_at TEXT,
                lift_reason TEXT
            )"""
        )
        con.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_permanent_bans_active_user "
            "ON permanent_bans(user_id) WHERE lifted_at IS NULL"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_permanent_bans_name "
            "ON permanent_bans(login_key,ranking_key,lifted_at)"
        )


def _active_user(con, uid):
    return con.execute(
        "SELECT id FROM permanent_bans WHERE user_id=? AND lifted_at IS NULL LIMIT 1",
        (int(uid),),
    ).fetchone()


def _active_name(con, name):
    key = account_name_safety.identity_key(name)
    if not key:
        return None
    return con.execute(
        "SELECT id FROM permanent_bans "
        "WHERE lifted_at IS NULL AND (login_key=? OR ranking_key=?) LIMIT 1",
        (key, key),
    ).fetchone()


async def _evict_live_player(db, server, uid):
    # Removing a player mid-hand would corrupt gameplay, so mark for departure
    # after the hand; remove immediately when the player is not in a hand.
    for table_id, _ in getattr(db, "FIXED_TABLES", ()):
        affected = False
        async with server.get_table_lock(table_id):
            state = server.load_table(table_id)
            player = next(
                (p for p in state.get("seats", []) if int(p.get("user_id") or 0) == uid),
                None,
            )
            if player:
                affected = True
                if state.get("status") == "playing" and player.get("in_hand"):
                    player["leave_after_hand"] = True
                else:
                    state["seats"] = [
                        p for p in state["seats"]
                        if int(p.get("user_id") or 0) != uid
                    ]
                server.save_table(state)
        if affected:
            await server.hub.broadcast(table_id)
    # Close any already-open observer socket as well as authenticated sessions.
    for table_id, connections in list(server.hub.connections.items()):
        for ws, connected_uid in list(connections):
            if int(connected_uid) == uid:
                try:
                    await ws.close(code=4403)
                except Exception:
                    pass
                server.hub.remove(table_id, ws)


def install(app, server, db, admin_console):
    if getattr(app.state, "jj_permanent_ban_installed", False):
        return
    ensure_schema(db)

    pin_route = _route(app, "/api/auth/pin", "POST")
    user_list = _route(app, "/api/admin/console/users", "GET")
    user_update = _route(app, "/api/admin/console/users/{uid}", "PATCH")
    if not pin_route or not user_list or not user_update:
        raise RuntimeError("permanent ban requires canonical account routes")

    original_pin = pin_route.dependant.call

    def guarded_pin(payload, response, request):
        with db.connect() as con:
            if _active_name(con, server.normalize_login_name(payload.name)):
                raise HTTPException(403, "このアカウントは永久利用禁止です")
        return original_pin(payload=payload, response=response, request=request)

    pin_route.endpoint = pin_route.dependant.call = guarded_pin

    original_list = user_list.dependant.call

    def decorated_users(q: str = "", include_disabled: bool = True, user=None):
        rows = original_list(q=q, include_disabled=include_disabled, user=user)
        with db.connect() as con:
            banned = {
                int(r["user_id"]) for r in con.execute(
                    "SELECT user_id FROM permanent_bans WHERE lifted_at IS NULL"
                ).fetchall()
            }
        return [{**row, "permanent_banned": int(row["id"]) in banned} for row in rows]

    user_list.endpoint = user_list.dependant.call = decorated_users

    original_update = user_update.dependant.call

    def guarded_update(uid, p, user):
        if getattr(p, "disabled", None) is False:
            # Serialize with the BAN write so a simultaneous normal resume
            # cannot clear disabled after the permanent-ban transaction.
            with account_name_safety._NAME_LOCK:
                with db.connect() as con:
                    if _active_user(con, uid):
                        raise HTTPException(409, "永久BAN中のアカウントは通常の利用再開では解除できません")
                return original_update(uid=uid, p=p, user=user)
        return original_update(uid=uid, p=p, user=user)

    user_update.endpoint = user_update.dependant.call = guarded_update

    @app.post("/api/admin/console/users/{uid}/permanent-ban")
    async def ban_user(uid: int, payload: BanRequest, actor=Depends(server.admin_user)):
        if uid == int(actor["id"]):
            raise HTTPException(400, "管理者自身を永久BANにはできません")
        reason = payload.reason.strip()
        if len(reason) < 3:
            raise HTTPException(422, "BAN理由を3文字以上入力してください")
        actor_id = int(actor["id"])
        with account_name_safety._NAME_LOCK:
            with db.connect() as con:
                account_name_safety._serialize(con, db)
                target = con.execute(
                    "SELECT id,name,ranking_name,role,deleted_at FROM users WHERE id=?",
                    (uid,),
                ).fetchone()
                if not target or target["deleted_at"]:
                    raise HTTPException(404, "user not found")
                if target["role"] == "admin":
                    raise HTTPException(403, "管理者アカウントは永久BANにできません")
                if _active_user(con, uid):
                    raise HTTPException(409, "このアカウントは既に永久BAN中です")
                login_key = account_name_safety.identity_key(target["name"])
                ranking_name = str(target["ranking_name"] or target["name"])
                ranking_key = account_name_safety.identity_key(ranking_name)
                con.execute(
                    "INSERT INTO permanent_bans("
                    "user_id,display_name,ranking_name,login_key,ranking_key,"
                    "reason,banned_by,banned_at) VALUES (?,?,?,?,?,?,?,?)",
                    (uid, str(target["name"]), ranking_name, login_key,
                     ranking_key, reason, actor_id, db.utcnow()),
                )
                con.execute("UPDATE users SET disabled=1 WHERE id=?", (uid,))
                admin_console._audit(
                    db, actor_id, "user.permanent_ban", uid, con=con, reason=reason
                )
        db.delete_user_sessions(uid)
        await _evict_live_player(db, server, uid)
        return {"ok": True, "user_id": uid, "permanent_banned": True}

    @app.get("/api/admin/console/permanent-bans")
    def list_bans(include_lifted: bool = False, actor=Depends(server.admin_user)):
        where = "" if include_lifted else "WHERE b.lifted_at IS NULL"
        with db.connect() as con:
            rows = con.execute(
                "SELECT b.id,b.user_id,b.display_name,b.ranking_name,b.reason,"
                "b.banned_at,b.lifted_at,b.lift_reason,"
                "a.name banned_by_name, l.name lifted_by_name, "
                "u.deleted_at account_deleted_at "
                "FROM permanent_bans b "
                "LEFT JOIN users a ON a.id=b.banned_by "
                "LEFT JOIN users l ON l.id=b.lifted_by "
                "LEFT JOIN users u ON u.id=b.user_id "
                f"{where} ORDER BY b.id DESC LIMIT 500"
            ).fetchall()
        return [dict(r) for r in rows]

    @app.post("/api/admin/console/permanent-bans/{ban_id}/lift")
    def lift_ban(ban_id: int, payload: LiftRequest, actor=Depends(server.admin_user)):
        reason = payload.reason.strip()
        if len(reason) < 3:
            raise HTTPException(422, "解除理由を3文字以上入力してください")
        with db.connect() as con:
            row = con.execute(
                "SELECT user_id,lifted_at FROM permanent_bans WHERE id=?",
                (ban_id,),
            ).fetchone()
            if not row:
                raise HTTPException(404, "BAN記録が見つかりません")
            if row["lifted_at"]:
                raise HTTPException(409, "このBANは既に解除済みです")
            con.execute(
                "UPDATE permanent_bans SET lifted_at=?,lifted_by=?,lift_reason=? "
                "WHERE id=? AND lifted_at IS NULL",
                (db.utcnow(), int(actor["id"]), reason, ban_id),
            )
            admin_console._audit(
                db, int(actor["id"]), "user.permanent_ban_lift",
                int(row["user_id"]), con=con, reason=reason, ban_id=ban_id
            )
        # Lifting a ban does not silently reactivate a suspended account.
        return {"ok": True, "ban_id": ban_id, "account_reactivated": False}

    app.state.jj_permanent_ban_installed = True


__all__ = ["install", "ensure_schema", "BanRequest", "LiftRequest"]
