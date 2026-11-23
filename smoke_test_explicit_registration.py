"""Registration/login separation regression using an isolated SQLite database."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


def run() -> None:
    with tempfile.TemporaryDirectory(prefix="jj-explicit-signup-") as temp:
        os.environ.pop("DATABASE_URL", None)
        os.environ["JJ_DB_PATH"] = str(Path(temp) / "test.db")
        os.environ["RENDER"] = "1"
        os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"
        os.environ.pop("JJ_ADMIN_PIN", None)

        import app

        with TestClient(app.app, base_url="https://testserver") as client:
            def login(name: str, pin: str = "123456"):
                return client.post("/api/auth/pin-login", json={"name": name, "pin": pin})

            def register(name: str, pin: str = "123456", confirm_pin: str = "123456"):
                return client.post(
                    "/api/auth/register",
                    json={"name": name, "pin": pin, "confirm_pin": confirm_pin},
                )

            # The login form must never silently create an unknown account.
            missing = login("みどり")
            assert missing.status_code == 401, missing.text
            with app.db.connect() as con:
                assert not con.execute("SELECT id FROM users WHERE name=?", ("みどり",)).fetchone()

            mismatch = register("みどり", "123456", "654321")
            assert mismatch.status_code == 400, mismatch.text
            with app.db.connect() as con:
                assert not con.execute("SELECT id FROM users WHERE name=?", ("みどり",)).fetchone()

            signup = register("みどり")
            assert signup.status_code == 200, signup.text
            assert signup.json()["created"] is True
            assert signup.json()["user"]["name"] == "みどり"
            uid = signup.json()["user"]["id"]
            assert client.get("/api/me").json()["id"] == uid

            # A second registration is never treated as a login.
            duplicate = register("ミドリ")
            assert duplicate.status_code == 409, duplicate.text
            assert register("みどり").status_code == 409
            wrong_pin = login("ミドリ", "222222")
            assert wrong_pin.status_code == 401, wrong_pin.text
            sign_in = login("ミドリ")
            assert sign_in.status_code == 200, sign_in.text
            assert sign_in.json()["created"] is False
            assert sign_in.json()["user"]["id"] == uid

            latin = register("PlayerOne", "246810", "246810")
            assert latin.status_code == 200, latin.text
            latin_id = latin.json()["user"]["id"]
            assert register("playerone", "246810", "246810").status_code == 409
            latin_sign_in = login("PLAYERONE", "246810")
            assert latin_sign_in.status_code == 200, latin_sign_in.text
            assert latin_sign_in.json()["user"]["id"] == latin_id
            assert login("MissingMember", "246810").status_code == 401

            bad = register("test!", "246810", "246810")
            assert bad.status_code == 400, bad.text
            with app.db.connect() as con:
                count = con.execute("SELECT COUNT(*) AS c FROM users WHERE name IN (?,?,?)",
                                    ("みどり", "PlayerOne", "MissingMember")).fetchone()["c"]
                assert count == 2

        html = app._patched_index()
        js = app._patched_app_js()
        assert 'id="registerForm"' in html
        assert 'id="openRegistration"' in html
        assert 'id="registerPinConfirm"' in html
        assert 'id="backToLogin"' in html
        assert "初回はそのままアカウントを作成" not in html
        assert "post('/auth/pin-login'" in js
        assert "post('/auth/register'" in js
        assert "post('/auth/pin',{name:$('#loginName').value" not in js

    print("JJ_EXPLICIT_REGISTRATION_OK")


if __name__ == "__main__":
    run()
