from __future__ import annotations

import re
from pathlib import Path


def apply(root: Path) -> None:
    _server(root / "server.py")
    _app(root / "static" / "app.js")
    _index(root / "static" / "index.html")
    _sw(root / "static" / "sw.js")


def _server(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace('version="1.20.1"', 'version="1.20.2"')
    text = text.replace('"version":"1.20.1"', '"version":"1.20.2"')
    text = text.replace('request.url.query == "v=46"', 'request.url.query == "v=47"')

    # Timeout processing must never fail silently. Patch only the final generic
    # catch inside timeout_loop so earlier nested recovery behavior is preserved.
    timeout_start = text.find("async def timeout_loop():")
    websocket_start = text.find('@app.websocket("/ws/tables/{table_id}")', timeout_start)
    if timeout_start < 0 or websocket_start < 0:
        raise RuntimeError("v1.20.2 timeout-loop boundaries missing")
    timeout_block = text[timeout_start:websocket_start]
    silent_pattern = re.compile(r"(?m)^(\s*)except Exception:\s*\n\1    pass\s*$")
    silent_matches = list(silent_pattern.finditer(timeout_block))
    if silent_matches:
        match = silent_matches[-1]
        indent = match.group(1)
        replacement = (
            f'{indent}except Exception as exc:\n'
            f'{indent}    print(f"JJ_TIMEOUT_LOOP_ERROR {{type(exc).__name__}}")'
        )
        timeout_block = timeout_block[:match.start()] + replacement + timeout_block[match.end():]
        text = text[:timeout_start] + timeout_block + text[websocket_start:]

    # The PIN login flow already issues a server-managed session cookie. Use the
    # same request_token helper for WebSocket handshakes instead of copying the
    # bearer token into a URL or exposing the HttpOnly cookie value to JS.
    pattern = re.compile(
        r'@app\.websocket\("/ws/tables/\{table_id\}"\)\n'
        r'async def table_ws\(ws: WebSocket, table_id: str\):\n'
        r'.*?\n\n\napp\.mount\("/static",',
        re.DOTALL,
    )
    replacement = '''@app.websocket("/ws/tables/{table_id}")\nasync def table_ws(ws: WebSocket, table_id: str):\n    await ws.accept()\n\n    # Browser WebSockets send Origin. Reject an explicit cross-origin handshake\n    # before reading any authenticated table state. Non-browser clients without\n    # Origin are still permitted for health/testing compatibility.\n    origin = str(ws.headers.get("origin") or "").rstrip("/")\n    host = str(ws.headers.get("host") or "").strip()\n    if origin and host and origin not in {f"https://{host}", f"http://{host}"}:\n        await ws.close(code=4403)\n        return\n\n    token = request_token(ws)\n    user = db.get_user_by_token(token)\n    if not user:\n        await ws.close(code=4401)\n        return\n    if int(user.get("disabled") or 0):\n        await ws.close(code=4403)\n        return\n    try:\n        state = load_table(table_id)\n    except HTTPException:\n        await ws.close(code=4404)\n        return\n\n    await hub.add(table_id, ws, user["id"])\n    try:\n        await ws.send_json({"type":"state","state":public_state(state,user["id"]),"messages":get_messages(table_id)})\n        while True:\n            message = await ws.receive_text()\n            if message == "ping":\n                continue\n    except WebSocketDisconnect:\n        pass\n    except Exception as exc:\n        print(f"JJ_WS_CONNECTION_ERROR {type(exc).__name__}")\n    finally:\n        hub.remove(table_id, ws)\n\n\napp.mount("/static",'''
    text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"v1.20.2 websocket handler target mismatch: {count}")
    path.write_text(text, encoding="utf-8")


def _app(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "v1.20.2 websocket token privacy"
    if marker in text:
        return

    # Remove the bearer-token query fragment without depending on the complete
    # connectTable line. Existing same-origin session cookies are automatically
    # included in the WebSocket handshake by the browser.
    ws_query_pattern = re.compile(
        r'(\$\{encodeURIComponent\(id\)\})\?token=\$\{[^}]+\}'
    )
    text, removed = ws_query_pattern.subn(r'\1', text, count=1)
    if removed != 1:
        if "/ws/tables/${encodeURIComponent(id)}" not in text or re.search(
            r'/ws/tables/[^`\n]*\?token=', text
        ):
            raise RuntimeError(f"v1.20.2 websocket query-token target mismatch: {removed}")

    if re.search(r'/ws/tables/[^`\n]*\?token=', text):
        raise RuntimeError("v1.20.2 websocket token query remains after patch")

    insert = "\n  // v1.20.2 websocket token privacy: same-origin session cookie authenticates WSS; no credential is placed in the URL.\n"
    pos = text.rfind("})();")
    if pos < 0:
        raise RuntimeError("v1.20.2 app closing marker missing")
    text = text[:pos] + insert + text[pos:]
    path.write_text(text, encoding="utf-8")


def _index(path: Path) -> None:
    text = path.read_text(encoding="utf-8").replace("?v=46", "?v=47")
    path.write_text(text, encoding="utf-8")


def _sw(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"jj-arena-live-v\d+", "jj-arena-live-v47", text)
    path.write_text(text, encoding="utf-8")
