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

    # Timeout processing must never fail silently. Log only the exception type
    # to avoid accidentally printing request/session data.
    old_timeout = '''        except Exception:\n            pass\n\n\n@app.websocket("/ws/tables/{table_id}")'''
    new_timeout = '''        except Exception as exc:\n            print(f"JJ_TIMEOUT_LOOP_ERROR {type(exc).__name__}")\n\n\n@app.websocket("/ws/tables/{table_id}")'''
    if old_timeout not in text:
        raise RuntimeError("v1.20.2 timeout-loop target missing")
    text = text.replace(old_timeout, new_timeout, 1)

    # Session tokens in WebSocket query strings can be exposed in browser
    # history, reverse-proxy access logs, tracing systems and copied URLs.
    # Authenticate using the first WSS message instead. No table state is sent
    # before authentication succeeds.
    pattern = re.compile(
        r'@app\.websocket\("/ws/tables/\{table_id\}"\)\n'
        r'async def table_ws\(ws: WebSocket, table_id: str\):\n'
        r'.*?\n\n\napp\.mount\("/static",',
        re.DOTALL,
    )
    replacement = '''@app.websocket("/ws/tables/{table_id}")\nasync def table_ws(ws: WebSocket, table_id: str):\n    await ws.accept()\n    try:\n        raw = await asyncio.wait_for(ws.receive_text(), timeout=5.0)\n        if len(raw) > 4096:\n            raise ValueError("auth frame too large")\n        payload = json.loads(raw)\n        if not isinstance(payload, dict):\n            raise ValueError("auth frame must be an object")\n        token = str(payload.get("token") or "") if payload.get("type") == "auth" else ""\n        if not token or len(token) > 512:\n            raise ValueError("invalid auth token")\n    except (asyncio.TimeoutError, json.JSONDecodeError, TypeError, ValueError):\n        await ws.close(code=4401)\n        return\n\n    user = db.get_user_by_token(token)\n    if not user:\n        await ws.close(code=4401)\n        return\n    if int(user.get("disabled") or 0):\n        await ws.close(code=4403)\n        return\n    try:\n        state = load_table(table_id)\n    except HTTPException:\n        await ws.close(code=4404)\n        return\n\n    await hub.add(table_id, ws, user["id"])\n    try:\n        await ws.send_json({"type":"state","state":public_state(state,user["id"]),"messages":get_messages(table_id)})\n        while True:\n            message = await ws.receive_text()\n            if message == "ping":\n                continue\n    except WebSocketDisconnect:\n        pass\n    except Exception as exc:\n        print(f"JJ_WS_CONNECTION_ERROR {type(exc).__name__}")\n    finally:\n        hub.remove(table_id, ws)\n\n\napp.mount("/static",'''
    text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"v1.20.2 websocket handler target mismatch: {count}")
    path.write_text(text, encoding="utf-8")


def _app(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "v1.20.2 websocket token privacy"
    if marker in text:
        return

    old_socket = "tableWS=new WebSocket(`${proto}://${location.host}/ws/tables/${encodeURIComponent(id)}?token=${encodeURIComponent(token)}`);"
    new_socket = "tableWS=new WebSocket(`${proto}://${location.host}/ws/tables/${encodeURIComponent(id)}`);"
    if text.count(old_socket) != 1:
        raise RuntimeError(f"v1.20.2 websocket URL target mismatch: {text.count(old_socket)}")
    text = text.replace(old_socket, new_socket, 1)

    old_open = "tableWS.onopen=()=>{if(tablePoll){clearInterval(tablePoll);tablePoll=null}tableHeartbeat=setInterval(()=>{if(tableWS?.readyState===WebSocket.OPEN)tableWS.send('ping')},15000)};"
    new_open = "tableWS.onopen=()=>{tableWS.send(JSON.stringify({type:'auth',token}));if(tablePoll){clearInterval(tablePoll);tablePoll=null}tableHeartbeat=setInterval(()=>{if(tableWS?.readyState===WebSocket.OPEN)tableWS.send('ping')},15000)};"
    if text.count(old_open) != 1:
        raise RuntimeError(f"v1.20.2 websocket onopen target mismatch: {text.count(old_open)}")
    text = text.replace(old_open, new_open, 1)

    insert = "\n  // v1.20.2 websocket token privacy: session token is sent only after WSS opens, never in the URL.\n"
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
