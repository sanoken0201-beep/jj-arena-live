from __future__ import annotations

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

    original = production_app.runtime_server.tables
    try:
        production_app.runtime_server.tables = lambda user: [
            {"id": "table-a", "name": "JJ Table A"},
            {"id": "table-b", "name": "JJ Table B"},
        ]
        result = production_app._single_public_table_list({"id": 1})
    finally:
        production_app.runtime_server.tables = original

    require(len(result) == 1, "public table API must return exactly one table")
    require(result[0]["id"] == "table-a", "first canonical table must remain public")
    print("single public table smoke test: PASS")


if __name__ == "__main__":
    main()
