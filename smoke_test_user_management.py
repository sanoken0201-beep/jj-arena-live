from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from fastapi import HTTPException, Response
from starlette.requests import Request

from runtime_builder import build_runtime


def _request(path: str = "/api/auth/pin") -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
    )


def _route(app, path: str, method: str):
    method = method.upper()
    for route in app.router.routes:
        if getattr(route, "path", None) == path and method in (getattr(route, "methods", None) or set()):
            return route
    raise AssertionError(f"route missing: {method} {path}")


def _expect_404(fn) -> None:
    try:
        fn()
    except HTTPException as exc:
        assert exc.status_code == 404, exc
    else:
        raise AssertionError("deleted account operation unexpectedly succeeded")


def run() -> None:
    work = Path(tempfile.mkdtemp(prefix="jj-user-management-smoke-"))
    runtime = build_runtime(work / "runtime")
    db_path = work / "users.sqlite3"

    previous = {k: os.environ.get(k) for k in (
        "DATABASE_URL",
        "JJ_DB_PATH",
        "JJ_ADMIN_NAME",
        "JJ_ADMIN_PIN",
        "JJ_ENABLE_DEMO_MEMBER",
    )}
    os.environ.pop("DATABASE_URL", None)
    os.environ["JJ_DB_PATH"] = str(db_path)
    os.environ["JJ_ADMIN_NAME"] = "ケンイチロウ"
    os.environ["JJ_ADMIN_PIN"] = "654321"
    os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"

    sys.path.insert(0, str(runtime))
    try:
        import db  # type: ignore
        import server  # type: ignore
        import admin_console
        import admin_delete
        import admin_pin_verification

        admin_console.install_admin_console(server.app)
        admin_delete.install_account_deletion(server.app)
        admin_pin_verification.install(server.app, admin_console)

        with db.connect() as con:
            admin = dict(con.execute("SELECT * FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone())

        canonical = server.normalize_login_name(" てすと ")
        assert canonical == "テスト"
        assert server.normalize_login_name("テスト") == canonical
        login_id = server.internal_login_id(canonical)
        assert server.internal_login_id(server.normalize_login_name("　てすと　")) == login_id

        old_pin = "111111"
        new_pin = "222222"

        old_login = server.pin_access(
            server.PinAccess(name=" てすと ", pin=old_pin),
            Response(),
            _request(),
        )
        assert old_login["created"] is True
        old_uid = int(old_login["user"]["id"])

        delete_ep = _route(server.app, "/api/admin/console/users/{uid}", "DELETE").endpoint
        deleted = delete_ep(uid=old_uid, user=admin)
        assert deleted["ok"] is True

        with db.connect() as con:
            old = dict(con.execute(
                "SELECT id,name,email,password_hash,disabled,ranking_name,deleted_at FROM users WHERE id=?",
                (old_uid,),
            ).fetchone())
        assert old["deleted_at"]
        assert int(old["disabled"] or 0) == 1
        assert str(old["name"]).startswith(admin_delete.DELETED_PREFIX)
        assert old["email"] != login_id
        assert old["ranking_name"] == canonical
        assert not db.verify_password(old_pin, old["password_hash"])
        assert not db.verify_password(new_pin, old["password_hash"])

        users_ep = _route(server.app, "/api/admin/console/users", "GET").endpoint
        visible = users_ep(q="", include_disabled=True, user=admin)
        assert old_uid not in {int(r["id"]) for r in visible}

        legacy_members_route = next(
            (
                r for r in server.app.router.routes
                if getattr(r, "path", None) == "/api/admin/members"
                and "GET" in (getattr(r, "methods", None) or set())
            ),
            None,
        )
        if legacy_members_route is not None:
            legacy_visible = legacy_members_route.endpoint(user=admin)
            assert old_uid not in {int(r["id"]) for r in legacy_visible}

        new_login = server.pin_access(
            server.PinAccess(name="テスト", pin=new_pin),
            Response(),
            _request(),
        )
        assert new_login["created"] is True
        new_uid = int(new_login["user"]["id"])
        assert new_uid != old_uid

        with db.connect() as con:
            new = dict(con.execute(
                "SELECT id,name,email,password_hash,disabled,ranking_name,deleted_at FROM users WHERE id=?",
                (new_uid,),
            ).fetchone())
            same_identity_rows = con.execute("SELECT id FROM users WHERE email=?", (login_id,)).fetchall()
        assert new["email"] == login_id
        assert new["name"] == canonical
        assert new["deleted_at"] is None
        assert int(new["disabled"] or 0) == 0
        assert db.verify_password(new_pin, new["password_hash"])
        assert not db.verify_password(old_pin, new["password_hash"])
        assert len(same_identity_rows) == 1

        try:
            server.pin_access(
                server.PinAccess(name="テスト", pin=old_pin),
                Response(),
                _request(),
            )
        except HTTPException as exc:
            assert exc.status_code == 401
        else:
            raise AssertionError("old PIN authenticated against the replacement account")

        equivalent_login = server.pin_access(
            server.PinAccess(name="てすと", pin=new_pin),
            Response(),
            _request(),
        )
        assert equivalent_login["created"] is False
        assert int(equivalent_login["user"]["id"]) == new_uid

        # A player can change their own PIN using the existing authenticated API.
        changed_pin = "555555"
        changed = server.change_pin(
            server.ChangePinIn(current_pin=new_pin, new_pin=changed_pin),
            _request("/api/auth/change-pin"),
            user=equivalent_login["user"],
        )
        assert changed["ok"] is True
        with db.connect() as con:
            changed_row = dict(con.execute("SELECT password_hash FROM users WHERE id=?", (new_uid,)).fetchone())
        assert db.verify_password(changed_pin, changed_row["password_hash"])
        assert not db.verify_password(new_pin, changed_row["password_hash"])

        changed_login = server.pin_access(
            server.PinAccess(name="テスト", pin=changed_pin),
            Response(),
            _request(),
        )
        assert changed_login["created"] is False
        assert int(changed_login["user"]["id"]) == new_uid

        # Admins can verify a candidate PIN without retrieving the stored PIN.
        verify_ep = _route(server.app, "/api/admin/console/users/{uid}/verify-pin", "POST").endpoint
        mismatch = verify_ep(
            uid=new_uid,
            payload=admin_pin_verification.AdminPinVerify(pin=new_pin),
            user=admin,
        )
        assert mismatch == {"ok": True, "matches": False}
        match = verify_ep(
            uid=new_uid,
            payload=admin_pin_verification.AdminPinVerify(pin=changed_pin),
            user=admin,
        )
        assert match == {"ok": True, "matches": True}
        with db.connect() as con:
            audits = con.execute(
                "SELECT detail_json FROM admin_audit_log WHERE action='user.pin_verify' AND target_user_id=? ORDER BY id",
                (new_uid,),
            ).fetchall()
        assert len(audits) == 2
        assert all(new_pin not in str(row["detail_json"]) for row in audits)
        assert all(changed_pin not in str(row["detail_json"]) for row in audits)

        visible = users_ep(q="", include_disabled=True, user=admin)
        ids = [int(r["id"]) for r in visible]
        assert old_uid not in ids
        assert ids.count(new_uid) == 1

        other = server.pin_access(
            server.PinAccess(name="ホカノヒト", pin="333333"),
            Response(),
            _request(),
        )
        other_uid = int(other["user"]["id"])
        update_ep = _route(server.app, "/api/admin/console/users/{uid}", "PATCH").endpoint
        update_ep(uid=other_uid, p=admin_console.AdminUserPatch(disabled=True), user=admin)
        shown_with_disabled = users_ep(q="", include_disabled=True, user=admin)
        hidden_without_disabled = users_ep(q="", include_disabled=False, user=admin)
        assert other_uid in {int(r["id"]) for r in shown_with_disabled}
        assert other_uid not in {int(r["id"]) for r in hidden_without_disabled}

        reset_ep = _route(server.app, "/api/admin/console/users/{uid}/reset-pin", "POST").endpoint
        revoke_ep = _route(server.app, "/api/admin/console/users/{uid}/revoke-sessions", "POST").endpoint
        point_ep = _route(server.app, "/api/admin/console/points", "POST").endpoint
        _expect_404(lambda: update_ep(uid=old_uid, p=admin_console.AdminUserPatch(disabled=False), user=admin))
        _expect_404(lambda: reset_ep(uid=old_uid, p=admin_console.AdminPinReset(pin="444444"), user=admin))
        _expect_404(lambda: verify_ep(uid=old_uid, payload=admin_pin_verification.AdminPinVerify(pin="444444"), user=admin))
        _expect_404(lambda: revoke_ep(uid=old_uid, user=admin))
        _expect_404(lambda: point_ep(
            p=admin_console.AdminPointIn(
                user_id=old_uid,
                direction="credit",
                amount=10,
                reason="削除済み確認",
            ),
            user=admin,
        ))

        overview_ep = _route(server.app, "/api/admin/console/overview", "GET").endpoint
        overview = overview_ep(user=admin)
        with db.connect() as con:
            live_count = int(con.execute("SELECT COUNT(*) n FROM users WHERE deleted_at IS NULL").fetchone()["n"])
        assert int(overview["accounts"]["total"]) == live_count
        assert all(
            not str(item.get("target_name") or "").startswith(admin_delete.DELETED_PREFIX)
            for item in overview.get("recent_audit") or []
        )

        print("JJ_USER_MANAGEMENT_SMOKE_OK")
    finally:
        sys.path.remove(str(runtime))
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    run()
