from __future__ import annotations

import os
import tempfile
from pathlib import Path


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="jj-entrypoint-") as td:
        # A production-entrypoint import can create schemas, seed data, apply
        # guarded migrations, restore table state and install middleware. Force
        # it onto an isolated SQLite database so CI can never touch a supplied
        # PostgreSQL DATABASE_URL by accident.
        os.environ.pop("DATABASE_URL", None)
        os.environ["JJ_DB_PATH"] = str(Path(td) / "entrypoint.db")
        os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"
        os.environ.setdefault("JJ_ADMIN_NAME", "CI_ADMIN")

        import app as production  # noqa: PLC0415

        fastapi_app = production.app
        routes = list(fastapi_app.router.routes)
        paths = [str(getattr(route, "path", "") or "") for route in routes]

        assert "/api/health" in paths
        assert any(path.startswith("/api/quiz/") for path in paths)
        assert any(path.startswith("/api/analysis") for path in paths)
        assert any(path.startswith("/api/admin/console") for path in paths)
        assert "/api/learning-content" in paths
        assert any(path in {"/admin", "/admin/"} for path in paths)

        catch_all_index = next(
            (i for i, path in enumerate(paths) if "path:path" in path or path == "/{path}"),
            None,
        )
        if catch_all_index is not None:
            for i, path in enumerate(paths):
                if (
                    path in {"/admin", "/admin/", "/api/learning-content"}
                    or path.startswith("/admin-static")
                    or path.startswith("/api/admin/console")
                    or path.startswith("/api/analysis")
                    or path.startswith("/api/quiz/")
                    or path.startswith("/api/home/")
                ):
                    assert i < catch_all_index, f"extension route shadowed by SPA catch-all: {path}"

        db_path = Path(os.environ["JJ_DB_PATH"])
        assert db_path.exists(), "isolated startup database was not initialized"

    print("JJ_PRODUCTION_ENTRYPOINT_ISOLATED_OK")


if __name__ == "__main__":
    main()
