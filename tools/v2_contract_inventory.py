from __future__ import annotations

import argparse
import importlib
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _route_inventory(app) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for route in app.router.routes:
        path = str(getattr(route, "path", "") or "")
        methods = sorted(str(x) for x in (getattr(route, "methods", None) or []))
        class_name = route.__class__.__name__.lower()
        kind = "websocket" if "websocket" in class_name else "http"
        rows.append(
            {
                "kind": kind,
                "path": path,
                "methods": methods,
                "name": str(getattr(route, "name", "") or ""),
            }
        )
    return rows


def _sqlite_schema(path: Path) -> dict[str, Any]:
    with sqlite3.connect(path) as con:
        con.row_factory = sqlite3.Row
        objects = [
            dict(row)
            for row in con.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_master "
                "WHERE type IN ('table','index') AND name NOT LIKE 'sqlite_%' "
                "ORDER BY type,name"
            ).fetchall()
        ]
        tables = [row["name"] for row in objects if row["type"] == "table"]
        columns: dict[str, list[dict[str, Any]]] = {}
        for table in tables:
            safe = str(table).replace('"', '""')
            columns[table] = [dict(row) for row in con.execute(f'PRAGMA table_info("{safe}")').fetchall()]

        migrations: list[dict[str, Any]] = []
        if "app_migrations" in tables:
            migrations = [
                dict(row)
                for row in con.execute("SELECT key,applied_at FROM app_migrations ORDER BY key").fetchall()
            ]

    return {"objects": objects, "columns": columns, "migrations": migrations}


def collect_contract() -> dict[str, Any]:
    """Load the production entrypoint against isolated SQLite and record contracts.

    This function deliberately removes DATABASE_URL before importing `app`. The
    production entrypoint performs startup-time schema/migration/resilience work,
    so the inventory must never run against an ambient production database.
    """
    with tempfile.TemporaryDirectory(prefix="jj-v2-contract-") as td:
        db_path = Path(td) / "contract.db"
        os.environ.pop("DATABASE_URL", None)
        os.environ["JJ_DB_PATH"] = str(db_path)
        os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"
        os.environ.setdefault("JJ_ADMIN_NAME", "V2_CONTRACT_AUDIT")

        if "app" in sys.modules:
            raise RuntimeError("tools.v2_contract_inventory must run before importing app")

        production = importlib.import_module("app")
        fastapi_app = production.app

        middleware = []
        for entry in fastapi_app.user_middleware:
            cls = getattr(entry, "cls", None)
            middleware.append(getattr(cls, "__name__", str(cls or entry)))

        if not db_path.exists():
            raise RuntimeError("isolated production entrypoint did not create its SQLite database")

        return {
            "routes": _route_inventory(fastapi_app),
            "middleware": middleware,
            "sqlite": _sqlite_schema(db_path),
        }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record JJ Arena legacy application contracts for v2 parity")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    payload = collect_contract()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "JJ_V2_CONTRACT_INVENTORY_OK "
        f"routes={len(payload['routes'])} tables={len(payload['sqlite']['columns'])} "
        f"middleware={len(payload['middleware'])}"
    )


if __name__ == "__main__":
    main()
