from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from runtime_builder import build_runtime


def expect_close(client: TestClient, code: int, path: str = "/ws/tables/jj-table-a", headers=None) -> None:
    try:
        with client.websocket_connect(path, headers=headers or {}) as ws:
            ws.receive_json()
    except WebSocketDisconnect as exc:
        assert exc.code == code, exc
    else:
        raise AssertionError(f"websocket unexpectedly accepted connection for close code {code}")


def run() -> None:
    work = Path(tempfile.mkdtemp(prefix="jj-ws-auth-smoke-"))
    runtime = build_runtime(work / "runtime")
    db_path = work / "ws.sqlite3"
    previous = {k: os.environ.get(k) for k in (
        "DATABASE_URL", "JJ_DB_PATH", "JJ_ADMIN_NAME", "JJ_ADMIN_PIN", "JJ_ENABLE_DEMO_MEMBER"
    )}
    os.environ.pop("DATABASE_URL", None)
    os.environ["JJ_DB_PATH"] = str(db_path)
    os.environ["JJ_ADMIN_NAME"] = "ケンイチロウ"
    os.environ["JJ_ADMIN_PIN"] = "654321"
    os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"

    old_modules = {}
    for name in ("db", "server", "poker_engine"):
        if name in sys.modules:
            old_modules[name] = sys.modules.pop(name)
    sys.path.insert(0, str(runtime))
    try:
        import db  # type: ignore
        import server  # type: ignore

        appjs = (runtime / "static" / "app.js").read_text(encoding="utf-8")
        server_source = (runtime / "server.py").read_text(encoding="utf-8")

        # WSS must rely on the server-managed same-origin session cookie rather
        # than exposing a bearer credential in the URL or in browser JS.
        assert "v1.20.2 websocket token privacy" in appjs
        assert "?token=${encodeURIComponent(token)}" not in appjs
        assert "JSON.stringify({type:'auth',token})" not in appjs
        assert 'ws.query_params.get("token")' not in server_source
        assert 'token = request_token(ws)' in server_source
        assert 'origin = str(ws.headers.get("origin") or "").rstrip("/")' in server_source
        assert 'JJ_TIMEOUT_LOOP_ERROR' in server_source
        assert 'finally:\n        hub.remove(table_id, ws)' in server_source

        # Use HTTPS so Secure cookies, if configured, behave exactly like the
        # production browser path. Logging in through the real PIN endpoint also
        # guards against a false-positive test that bypasses normal auth wiring.
        with TestClient(server.app, base_url="https://testserver") as client:
            login = client.post(
                "/api/auth/pin",
                json={"name": "テストユーザー", "pin": "123456"},
            )
            assert login.status_code == 200, login.text
            user = login.json()["user"]
            uid = int(user["id"])
            set_cookie = login.headers.get("set-cookie", "").lower()
            assert "httponly" in set_cookie
            assert client.cookies

            # No token is sent by JavaScript. The cookie on the WSS handshake is
            # enough to authenticate and the first server frame is table state.
            with client.websocket_connect(
                "/ws/tables/jj-table-a",
                headers={"origin": "https://testserver"},
            ) as ws:
                payload = ws.receive_json()
                assert payload["type"] == "state"
                assert payload["state"]["id"] == "jj-table-a"
                ws.send_text("ping")

            # Explicit cross-origin browser handshakes are rejected even when a
            # valid session cookie is present.
            expect_close(
                client,
                4403,
                headers={"origin": "https://evil.example"},
            )

            # Capture only this ephemeral test token so we can verify that the
            # old query-string transport is no longer honored. A separate client
            # has no session cookie, therefore a valid token in the URL must fail.
            cookie_values = [value for _, value in client.cookies.items()]
            assert cookie_values
            test_token = cookie_values[0]
            with TestClient(server.app, base_url="https://testserver") as anonymous:
                expect_close(
                    anonymous,
                    4401,
                    path=f"/ws/tables/jj-table-a?token={test_token}",
                    headers={"origin": "https://testserver"},
                )
                expect_close(
                    anonymous,
                    4401,
                    headers={"origin": "https://testserver"},
                )

            # Disabled accounts are rejected even while their old browser cookie
            # still exists, matching the HTTP authorization lifecycle.
            with db.connect() as con:
                con.execute("UPDATE users SET disabled=1 WHERE id=?", (uid,))
            expect_close(
                client,
                4403,
                headers={"origin": "https://testserver"},
            )

        print("JJ_WEBSOCKET_AUTH_SMOKE_OK")
    finally:
        if str(runtime) in sys.path:
            sys.path.remove(str(runtime))
        for name in ("db", "server", "poker_engine"):
            sys.modules.pop(name, None)
        sys.modules.update(old_modules)
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    run()
