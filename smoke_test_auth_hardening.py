from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


def run() -> None:
    work = Path(tempfile.mkdtemp(prefix="jj-auth-hardening-"))
    os.environ.pop("DATABASE_URL", None)
    os.environ["RENDER"] = "1"
    os.environ["JJ_DB_PATH"] = str(work / "auth.sqlite3")
    os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"
    os.environ["JJ_ADMIN_NAME"] = "セキュリティカンリ"
    os.environ["JJ_ADMIN_PIN"] = "654321"

    # Do not let a smoke test rewrite checked-in admin assets.
    import admin_copy_patch

    admin_copy_patch.apply = lambda _path: None

    import app as production

    with TestClient(production.app, base_url="https://testserver") as client:
        member_login = client.post(
            "/api/auth/pin",
            json={"name": "セキュリティテスト", "pin": "123456"},
        )
        assert member_login.status_code == 200, member_login.text
        assert member_login.json()["created"] is True
        member_id = int(member_login.json()["user"]["id"])

        set_cookie = member_login.headers.get("set-cookie", "")
        lower_cookie = set_cookie.lower()
        assert "__host-jj_session=" in lower_cookie, set_cookie
        assert "httponly" in lower_cookie, set_cookie
        assert "secure" in lower_cookie, set_cookie
        assert "samesite=lax" in lower_cookie, set_cookie
        assert "path=/" in lower_cookie, set_cookie

        token = member_login.cookies.get("__Host-jj_session")
        assert token

        # Production must not accept the historical unprefixed cookie anymore.
        with TestClient(production.app, base_url="https://testserver") as legacy_client:
            legacy_client.cookies.set("jj_session", token)
            legacy_me = legacy_client.get("/api/me")
            assert legacy_me.status_code == 401, legacy_me.text

        with TestClient(production.app, base_url="https://testserver") as modern_client:
            modern_client.cookies.set("__Host-jj_session", token)
            modern_me = modern_client.get("/api/me")
            assert modern_me.status_code == 200, modern_me.text
            assert int(modern_me.json()["id"]) == member_id

            # Fetch Metadata supplies a second CSRF boundary beyond Origin/SameSite.
            blocked = modern_client.post(
                "/api/auth/logout",
                headers={"Sec-Fetch-Site": "cross-site"},
            )
            assert blocked.status_code == 403, blocked.text
            assert modern_client.get("/api/me").status_code == 200

            # A stolen authenticated session must not provide unlimited current-PIN guesses.
            for _ in range(5):
                bad = modern_client.post(
                    "/api/auth/change-pin",
                    json={"current_pin": "000000", "new_pin": "222222"},
                )
                assert bad.status_code == 400, bad.text
            limited = modern_client.post(
                "/api/auth/change-pin",
                json={"current_pin": "000000", "new_pin": "222222"},
            )
            assert limited.status_code == 429, limited.text

        # A separate user can still perform a legitimate PIN change.
        second = client.post(
            "/api/auth/pin",
            json={"name": "ホンニンカクニン", "pin": "333333"},
        )
        assert second.status_code == 200, second.text
        changed = client.post(
            "/api/auth/change-pin",
            json={"current_pin": "333333", "new_pin": "444444"},
        )
        assert changed.status_code == 200, changed.text

        # Administrators may reset PINs, but may never use the server as a PIN oracle.
        admin = client.post(
            "/api/auth/pin",
            json={"name": "セキュリティカンリ", "pin": "654321"},
        )
        assert admin.status_code == 200, admin.text
        assert admin.json()["user"]["role"] == "admin"

        retired = client.post(
            f"/api/admin/console/users/{member_id}/verify-pin",
            json={"pin": "123456"},
        )
        assert retired.status_code == 410, retired.text
        assert "matches" not in retired.text.lower()

        reset = client.post(
            f"/api/admin/console/users/{member_id}/reset-pin",
            json={"pin": "555555"},
        )
        assert reset.status_code == 200, reset.text

    print("JJ_AUTH_HARDENING_OK")


if __name__ == "__main__":
    run()
