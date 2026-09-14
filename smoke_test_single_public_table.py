from __future__ import annotations

from fastapi.testclient import TestClient

import app as production_app


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


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

        with TestClient(production_app.app) as client:
            response = client.get("/api/tables")
        require(response.status_code == 200, f"GET /api/tables failed: {response.status_code}")
        payload = response.json()
        require(isinstance(payload, list), "GET /api/tables must return a list")
        require(len(payload) == 1, f"production router exposed {len(payload)} tables instead of one")
        require(payload[0]["id"] == "jj-table-a", "production router exposed the wrong table")
    finally:
        production_app.runtime_server.tables = original_tables
        production_app.app.dependency_overrides.pop(production_app.runtime_server.current_user, None)

    print("single public table smoke test: PASS")


if __name__ == "__main__":
    main()
