from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from runtime_builder import build_runtime


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

        # The browser must never place the session token in a WebSocket URL.
        assert "v1.20.2 websocket token privacy" in appjs
        assert "?token=${encodeURIComponent(token)}" not in appjs
        assert "JSON.stringify({type:'auth',token})" in appjs
        assert 'ws.query_params.get("token")' not in server_source
        assert 'await asyncio.wait_for(ws.receive_text(), timeout=5.0)' in server_source
        assert 'JJ_TIMEOUT_LOOP_ERROR' in server_source
        assert 'finally:\n        hub.remove(table_id, ws)' in server_source

        with db.connect() as con:
            uid = db.insert_returning_id(
                con,
                "INSERT INTO users(name,email,password_hash,role,arena_chips,xp,approved,disabled,ranking_name,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("テストユーザー", "ws-test@jj.invalid", db.hash_password("123456"), "member", 0, 0, 1, 0, "テストユーザー", db.utcnow()),
            )
        token = db.create_session(uid)

        with TestClient(server.app) as client:
            # New protocol: connect without credentials in the URL, then send a
            # short authentication frame before any table state is returned.
            with client.websocket_connect("/ws/tables/jj-table-a") as ws:
                ws.send_json({"type": "auth", "token": token})
                payload = ws.receive_json()
                assert payload["type"] == "state"
                assert payload["state"]["id"] == "jj-table-a"
                ws.send_text("ping")

            # Invalid tokens are rejected immediately after the auth frame.
            try:
                with client.websocket_connect("/ws/tables/jj-table-a") as ws:
                    ws.send_json({"type": "auth", "token": "invalid-token"})
                    ws.receive_json()
            except WebSocketDisconnect as exc:
                assert exc.code == 4401
            else:
                raise AssertionError("invalid websocket token was accepted")

            # The old query-string transport is intentionally not accepted.
            try:
                with client.websocket_connect(f"/ws/tables/jj-table-a?token={token}") as ws:
                    ws.send_text("ping")
                    ws.receive_json()
            except WebSocketDisconnect as exc:
                assert exc.code == 4401
            else:
                raise AssertionError("legacy query-string websocket auth still works")

            # Disabled accounts are rejected even with a valid session token.
            with db.connect() as con:
                con.execute("UPDATE users SET disabled=1 WHERE id=?", (uid,))
            try:
                with client.websocket_connect("/ws/tables/jj-table-a") as ws:
                    ws.send_json({"type": "auth", "token": token})
                    ws.receive_json()
            except WebSocketDisconnect as exc:
                assert exc.code == 4403
            else:
                raise AssertionError("disabled user websocket was accepted")

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
