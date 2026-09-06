from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path

WORK = Path(tempfile.mkdtemp(prefix="jj-admin-route-"))
os.environ["JJ_DB_PATH"] = str(WORK / "route.db")
os.environ.pop("DATABASE_URL", None)
os.environ["JJ_ADMIN_NAME"] = "ケンイチロウ"
os.environ["JJ_ADMIN_PIN"] = "123456"
os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"


async def asgi_get(app, path: str):
    messages = []
    sent_request = False

    async def receive():
        nonlocal sent_request
        if not sent_request:
            sent_request = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver")],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    await app(scope, receive, send)
    start = next(m for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    headers = {k.decode("latin1").lower(): v.decode("latin1") for k, v in start.get("headers", [])}
    return int(start["status"]), headers, body


def main() -> None:
    from app import app

    paths = [str(getattr(r, "path", "")) for r in app.router.routes]
    admin_index = min(i for i, p in enumerate(paths) if p in {"/admin", "/admin/"})
    fallback_indexes = [i for i, p in enumerate(paths) if p in {"/{path:path}", "/{full_path:path}"}]
    if fallback_indexes:
        assert admin_index < min(fallback_indexes), (admin_index, fallback_indexes, paths)

    status, headers, body = asyncio.run(asgi_get(app, "/admin"))
    text = body.decode("utf-8", errors="replace")
    assert status == 200, status
    assert "Admin Console" in text, text[:200]

    status, headers, body = asyncio.run(asgi_get(app, "/admin-static/admin.css"))
    css = body.decode("utf-8", errors="replace")
    assert status == 200, status
    assert "--bg:" in css and ".sidebar" in css
    assert "text/css" in headers.get("content-type", "")

    status, headers, body = asyncio.run(asgi_get(app, "/admin-static/admin.js"))
    js = body.decode("utf-8", errors="replace")
    assert status == 200, status
    assert "loadOverview" in js and "admin/console/users" in js
    assert "javascript" in headers.get("content-type", "")

    status, headers, body = asyncio.run(asgi_get(app, "/api/admin/console/overview"))
    payload = body.decode("utf-8", errors="replace")
    assert status in {401, 403}, (status, payload[:200])
    assert "text/html" not in headers.get("content-type", "")

    print("ADMIN_ROUTE_SMOKE_OK", flush=True)


if __name__ == "__main__":
    try:
        main()
    finally:
        shutil.rmtree(WORK, ignore_errors=True)
