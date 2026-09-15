from __future__ import annotations

import asyncio
import json

import app as production_app


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


async def _asgi_get(path: str) -> tuple[int, bytes]:
    """Exercise the real production ASGI router using production dependencies only."""
    request_sent = False
    messages: list[dict] = []

    async def receive() -> dict:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": [(b"host", b"testserver")],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 443),
        "root_path": "",
    }
    await production_app.app(scope, receive, send)

    start = next((m for m in messages if m.get("type") == "http.response.start"), None)
    require(start is not None, "ASGI response did not start")
    body = b"".join(
        m.get("body", b"")
        for m in messages
        if m.get("type") == "http.response.body"
    )
    return int(start["status"]), body


def main() -> None:
    get_table_routes = [
        route
        for route in production_app.app.router.routes
        if getattr(route, "path", None) == "/api/tables"
        and "GET" in (getattr(route, "methods", None) or set())
    ]
    require(get_table_routes, "GET /api/tables route missing")
    require(
        get_table_routes[0].endpoint is production_app._single_public_table_list,
        "single-table API override must be the first matching GET /api/tables route",
    )

    original_tables = production_app.runtime_server.tables
    production_app.app.dependency_overrides[production_app.runtime_server.current_user] = (
        lambda: {"id": 1, "name": "テスト", "role": "member"}
    )
    try:
        production_app.runtime_server.tables = lambda user: [
            {"id": "jj-table-a", "name": "JJ Table A"},
            {"id": "jj-table-b", "name": "JJ Table B"},
        ]

        direct = production_app._single_public_table_list({"id": 1})
        require(len(direct) == 1, "single-table endpoint must return exactly one table")
        require(direct[0]["id"] == "jj-table-a", "first canonical table must remain public")

        status, body = asyncio.run(_asgi_get("/api/tables"))
        require(status == 200, f"GET /api/tables failed: {status}")
        payload = json.loads(body.decode("utf-8"))
        require(isinstance(payload, list), "GET /api/tables must return a list")
        require(len(payload) == 1, f"production router exposed {len(payload)} tables instead of one")
        require(payload[0]["id"] == "jj-table-a", "production router exposed the wrong table")
    finally:
        production_app.runtime_server.tables = original_tables
        production_app.app.dependency_overrides.pop(production_app.runtime_server.current_user, None)

    print("single public table smoke test: PASS")


if __name__ == "__main__":
    main()
