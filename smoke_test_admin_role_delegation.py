"""End-to-end administrator succession regression on a disposable SQLite DB."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


def run() -> None:
    root = Path(tempfile.mkdtemp(prefix="jj-admin-delegation-"))
    os.environ.pop("DATABASE_URL", None)
    os.environ["JJ_DB_PATH"] = str(root / "roles.sqlite3")
    os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"
    os.environ["JJ_ADMIN_NAME"] = "カンリシャ"
    os.environ["JJ_ADMIN_PIN"] = "654321"
    os.environ["RENDER"] = "1"

    from build_served_assets import main as build_assets
    build_assets()
    import app as production

    base = "https://testserver"
    with (
        TestClient(production.app, base_url=base) as original,
        TestClient(production.app, base_url=base) as successor,
        TestClient(production.app, base_url=base) as candidate,
    ):
        def login(client, name, pin, expected_role):
            response = client.post("/api/auth/pin", json={"name":name, "pin":pin})
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["user"]["role"] == expected_role, data
            return int(data["user"]["id"])

        admin_id = login(original, "カンリシャ", "654321", "admin")
        next_id = login(successor, "ヒキツギ", "112233", "member")
        candidate_id = login(candidate, "ホカノカンリ", "223344", "member")
        endpoint = lambda uid: f"/api/admin/console/users/{uid}/role"

        assert original.get("/admin-static/admin_role_delegation.js").status_code == 200
        assert successor.post(endpoint(candidate_id), json={"role":"admin","current_pin":"112233"}).status_code == 403
        assert original.post(endpoint(next_id), headers={"Sec-Fetch-Site":"cross-site"}, json={"role":"admin","current_pin":"654321"}).status_code == 403
        assert original.post(endpoint(next_id), json={"role":"owner","current_pin":"654321"}).status_code == 422
        assert original.post(endpoint(next_id), json={"role":"admin","current_pin":"654321"}).status_code == 409

        for uid in (next_id, candidate_id):
            verified = original.patch(f"/api/admin/console/users/{uid}", json={"club_verified":True})
            assert verified.status_code == 200, verified.text

        wrong = original.post(endpoint(next_id), json={"role":"admin","current_pin":"000000"})
        assert wrong.status_code == 403, wrong.text
        assert original.get("/api/admin/console/users").status_code == 200
        promoted = original.post(endpoint(next_id), json={"role":"admin","current_pin":"654321"})
        assert promoted.status_code == 200 and promoted.json()["changed"], promoted.text
        assert successor.get("/api/me").status_code == 401, "promoted user's old session survived"
        assert login(successor, "ヒキツギ", "112233", "admin") == next_id
        repeated = original.post(endpoint(next_id), json={"role":"admin","current_pin":"654321"})
        assert repeated.status_code == 200 and not repeated.json()["changed"], repeated.text

        delegated = successor.post(endpoint(candidate_id), json={"role":"admin","current_pin":"112233"})
        assert delegated.status_code == 200 and delegated.json()["changed"], delegated.text
        assert candidate.get("/api/me").status_code == 401
        assert login(candidate, "ホカノカンリ", "223344", "admin") == candidate_id

        removed = original.post(endpoint(candidate_id), json={"role":"member","current_pin":"654321"})
        assert removed.status_code == 200 and removed.json()["changed"], removed.text
        assert candidate.get("/api/me").status_code == 401, "demoted user's old session survived"
        assert login(candidate, "ホカノカンリ", "223344", "member") == candidate_id
        assert candidate.get("/api/admin/console/users").status_code == 403

        # The original owner can be relieved by the successor; the remaining
        # administrator cannot strip themselves of the last administrator role.
        retire = successor.post(endpoint(admin_id), json={"role":"member","current_pin":"112233"})
        assert retire.status_code == 200 and retire.json()["changed"], retire.text
        assert original.get("/api/me").status_code == 401
        assert login(original, "カンリシャ", "654321", "member") == admin_id
        assert original.post(endpoint(next_id), json={"role":"member","current_pin":"654321"}).status_code == 403
        sole = successor.post(endpoint(next_id), json={"role":"member","current_pin":"112233"})
        assert sole.status_code == 409, sole.text

        with production.db.connect() as con:
            admins = con.execute("SELECT id FROM users WHERE role='admin' AND deleted_at IS NULL").fetchall()
            assert [int(row["id"]) for row in admins] == [next_id], admins
            audit = con.execute(
                "SELECT actor_id,target_user_id,detail_json FROM admin_audit_log "
                "WHERE action='user.role_change' ORDER BY id"
            ).fetchall()
            assert len(audit) == 4, audit
            assert [int(row["target_user_id"]) for row in audit] == [
                next_id,candidate_id,candidate_id,admin_id
            ]
            assert all("654321" not in row["detail_json"] and "112233" not in row["detail_json"]
                       for row in audit), "A PIN appeared in role audit"
    print("JJ_ADMIN_ROLE_DELEGATION_OK")


if __name__ == "__main__":
    run()
