from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="jj-import-scope-") as directory:
        os.environ.pop("DATABASE_URL", None)
        os.environ["JJ_DB_PATH"] = str(Path(directory) / "import-scope.sqlite3")
        os.environ["JJ_ADMIN_NAME"] = "インポートテスト"
        os.environ["JJ_ADMIN_PIN"] = "654321"
        os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"

        before = list(sys.path)
        import app_materialized as production

        dest = production.DEST.resolve()
        assert sys.path == before, "app_materialized changed process-wide sys.path"
        assert str(dest) not in sys.path, "materialized core path leaked after startup"

        modules = {
            "server": production.runtime_server,
            "db": production.db,
            "poker_engine": production.runtime_poker_engine,
        }
        for name, module in modules.items():
            module_path = Path(str(getattr(module, "__file__", ""))).resolve()
            assert module_path.parent == dest, (name, module_path)
            assert sys.modules.get(name) is module, f"{name} is not the canonical loaded module"

        assert production.app is production.runtime_server.app
        source = (ROOT / "app_materialized.py").read_text(encoding="utf-8")
        assert "finally:\n        sys.path[:] = original_path" in source
        assert "sys.path.insert(0, str(DEST))" in source
        assert "materialized core path leaked into process-wide sys.path" in source

    print("JJ_MATERIALIZED_IMPORT_SCOPE_OK")


if __name__ == "__main__":
    main()
