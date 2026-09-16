from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="jj-admin-api-consolidation-"))
    os.environ.pop("DATABASE_URL", None)
    os.environ["RENDER"] = "1"
    os.environ["JJ_DB_PATH"] = str(work / "admin.sqlite3")
    os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"
    os.environ["JJ_ADMIN_NAME"] = "セイリカンリ"
    os.environ["JJ_ADMIN_PIN"] = "654321"

    import admin_copy_patch
    admin_copy_patch.apply = lambda _path: None

    import app as production

    with TestClient(production.app, base_url="https://testserver") as client:
        member = client.post("/api/auth/pin", json={"name": "イッパンメンバー", "pin": "123456"})
        assert member.status_code == 200, member.text
        member_id = int(member.json()["user"]["id"])

        # Ordinary users cannot use either the retired or canonical admin API.
        assert client.get("/api/admin/members").status_code == 403
        assert client.get("/api/admin/console/users").status_code == 403

        client.post("/api/auth/logout")
        admin = client.post("/api/auth/pin", json={"name": "セイリカンリ", "pin": "654321"})
        assert admin.status_code == 200, admin.text
        admin_id = int(admin.json()["user"]["id"])
        assert admin.json()["user"]["role"] == "admin"

        # Stale clients receive an explicit tombstone rather than reaching the
        # weaker immutable-core member-management implementation.
        old_list = client.get("/api/admin/members")
        assert old_list.status_code == 410, old_list.text
        old_patch = client.patch(f"/api/admin/members/{member_id}", json={"disabled": True})
        assert old_patch.status_code == 410, old_patch.text
        old_reset = client.post(
            f"/api/admin/members/{member_id}/reset-pin",
            json={"pin": "222222"},
        )
        assert old_reset.status_code == 410, old_reset.text

        canonical = client.get("/api/admin/console/users")
        assert canonical.status_code == 200, canonical.text
        ids = {int(row["id"]) for row in canonical.json()}
        assert member_id in ids and admin_id in ids

        # Canonical reset can target members but must reject administrator PINs.
        reset_member = client.post(
            f"/api/admin/console/users/{member_id}/reset-pin",
            json={"pin": "555555"},
        )
        assert reset_member.status_code == 200, reset_member.text
        reset_admin = client.post(
            f"/api/admin/console/users/{admin_id}/reset-pin",
            json={"pin": "777777"},
        )
        assert reset_admin.status_code == 400, reset_admin.text

        client.post("/api/auth/logout")
        assert client.post(
            "/api/auth/pin",
            json={"name": "イッパンメンバー", "pin": "123456"},
        ).status_code == 401
        assert client.post(
            "/api/auth/pin",
            json={"name": "イッパンメンバー", "pin": "555555"},
        ).status_code == 200

    print("JJ_ADMIN_API_CONSOLIDATION_OK")


if __name__ == "__main__":
    main()
