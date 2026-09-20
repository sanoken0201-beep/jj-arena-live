from __future__ import annotations

"""Guard the post-materialization repository boundary."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent

STALE_ROOT_PATHS = (
    ROOT / "server.py",
    ROOT / "db.py",
    ROOT / "poker_engine.py",
    ROOT / "static",
)

CANONICAL_CORE_PATHS = (
    ROOT / "materialized_v1244" / "server.py",
    ROOT / "materialized_v1244" / "db.py",
    ROOT / "materialized_v1244" / "poker_engine.py",
    ROOT / "materialized_v1244" / "static" / "app.js",
    ROOT / "materialized_v1244" / "static" / "styles.css",
    ROOT / "materialized_v1244" / "static" / "index.html",
    ROOT / "materialized_v1244" / "static" / "sw.js",
)


def main() -> None:
    stale = [str(path.relative_to(ROOT)) for path in STALE_ROOT_PATHS if path.exists()]
    if stale:
        raise RuntimeError(f"stale root core resurfaced: {stale}")

    missing = [str(path.relative_to(ROOT)) for path in CANONICAL_CORE_PATHS if not path.exists()]
    if missing:
        raise RuntimeError(f"canonical materialized core is incomplete: {missing}")

    served_assets = (ROOT / "served_assets.py").read_text(encoding="utf-8")
    if 'MATERIALIZED_STATIC = ROOT / "materialized_v1244" / "static"' not in served_assets:
        raise RuntimeError("served_assets no longer points at materialized_v1244/static")

    app_materialized = (ROOT / "app_materialized.py").read_text(encoding="utf-8")
    if 'DEST = (ROOT / "materialized_v1244").resolve()' not in app_materialized:
        raise RuntimeError("app_materialized no longer points at materialized_v1244")

    app = (ROOT / "app.py").read_text(encoding="utf-8")
    if "from app_materialized import app, db, runtime_poker_engine, runtime_server" not in app:
        raise RuntimeError("production app no longer imports the materialized runtime boundary")

    print("JJ_ROOT_CORE_PRUNED_OK")


if __name__ == "__main__":
    main()
