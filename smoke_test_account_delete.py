from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from fastapi import HTTPException

WORK = Path(tempfile.mkdtemp(prefix="jj-account-delete-"))
os.environ["JJ_DB_PATH"] = str(WORK / "delete.db")
os.environ.pop("DATABASE_URL", None)
os.environ["JJ_ADMIN_NAME"] = "ケンイチロウ"
os.environ["JJ_ADMIN_PIN"] = "123456"
os.environ["JJ_ENABLE_DEMO_MEMBER"] = "1"


def route(app, path: str, method: str):
    method = method.upper()
    for r in app.router.routes:
        if getattr(r, "path", None) == path and method in (getattr(r, "methods", None) or set()):
            return r
    raise AssertionError((path, method))


def main() -> None:
    from app import app
    import db
    import server
    from admin_console import AdminPointIn, _rankings

    with db.connect() as con:
        admin = con.execute("SELECT id,name,role FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()
        assert admin and admin["name"] == "ケンイチロウ"
        member = con.execute("SELECT id,name FROM users WHERE role='member' ORDER BY id LIMIT 1").fetchone()
        if not member:
            uid = db.insert_returning_id(
                con,
                "INSERT INTO users(name,email,password_hash,role,arena_chips,xp,approved,disabled,ranking_name,created_at,club_verified,admin_note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                ("削除テスト", "delete-smoke@jj.invalid", db.hash_password("654321"), "member", 0, 0, 1, 0, "削除テスト", db.utcnow(), 1, ""),
            )
        else:
            uid = int(member["id"])
        con.execute("UPDATE users SET name='削除テスト',ranking_name='削除テスト',disabled=0,club_verified=1 WHERE id=?", (uid,))
        con.execute(
            "INSERT INTO point_ledger(id,user_id,amount,kind,reason,effective_at,created_by,created_at,reversal_of) VALUES (?,?,?,?,?,?,?,?,NULL)",
            ("delete-smoke-credit", uid, 25.0, "credit", "delete smoke", "2026-09-06T12:00:00", int(admin["id"]), db.utcnow()),
        )

    admin_user = {"id": int(admin["id"]), "name": str(admin["name"]), "role": "admin"}
    before = next(r for r in _rankings(db, server, season="fall") if r["name"] == "削除テスト")
    assert before["admin_points"] == 25.0

    delete_route = route(app, "/api/admin/console/users/{uid}", "DELETE")
    result = delete_route.endpoint(uid=uid, user=admin_user)
    assert result["ok"] is True

    with db.connect() as con:
        deleted = con.execute("SELECT id,name,ranking_name,disabled,club_verified,deleted_at,deleted_by FROM users WHERE id=?", (uid,)).fetchone()
        assert deleted
        assert str(deleted["name"]).startswith("削除済みユーザー#")
        assert deleted["ranking_name"] == "削除テスト"
        assert int(deleted["disabled"] or 0) == 1
        assert int(deleted["club_verified"] or 0) == 0
        assert deleted["deleted_at"]
        assert int(deleted["deleted_by"]) == int(admin["id"])

    users_route = route(app, "/api/admin/console/users", "GET")
    visible = users_route.endpoint(q="", include_disabled=True, user=admin_user)
    assert all(int(u["id"]) != uid for u in visible)

    overview_route = route(app, "/api/admin/console/overview", "GET")
    overview = overview_route.endpoint(user=admin_user)
    with db.connect() as con:
        real_count = con.execute("SELECT COUNT(*) n FROM users WHERE deleted_at IS NULL").fetchone()["n"]
    assert int(overview["accounts"]["total"]) == int(real_count)

    after = next(r for r in _rankings(db, server, season="fall") if r["name"] == "削除テスト")
    assert after["admin_points"] == 25.0

    point_route = route(app, "/api/admin/console/points", "POST")
    try:
        point_route.endpoint(
            p=AdminPointIn(user_id=uid, direction="credit", amount=1, reason="must reject", effective_at="2026-09-06T12:00"),
            user=admin_user,
        )
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("deleted account accepted a point transaction")

    try:
        delete_route.endpoint(uid=int(admin["id"]), user=admin_user)
    except HTTPException as exc:
        assert exc.status_code == 400
    else:
        raise AssertionError("admin account deletion was not blocked")

    assert (Path(__file__).parent / "admin_static" / "admin_delete.js").is_file()
    print("ACCOUNT_DELETE_SMOKE_OK", flush=True)


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(WORK, ignore_errors=True)
