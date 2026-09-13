"""Production-safe release gate shared by GitHub CI and Render builds.

The Render build environment contains the real production ``DATABASE_URL``.
Every subprocess launched here deliberately removes that variable and receives
a fresh temporary SQLite database, so release validation can never migrate or
write the production PostgreSQL database.

The full GitHub Actions suite remains a superset: disposable PostgreSQL 18 and
real-browser tests stay there. This gate contains the critical checks that are
safe and useful to run in both environments using only production dependencies.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from build_served_assets import main as build_assets

ROOT = Path(__file__).resolve().parent

# Keep this list deliberately small, deterministic and production-dependency-only.
RELEASE_TESTS = (
    "smoke_test_prebuilt_assets.py",
    "smoke_test_pwa_update.py",
    "smoke_test_runtime_performance.py",
    "smoke_test_runtime_observability.py",
    "smoke_test_point_ledger_precision.py",
    "smoke_test_v1244.py",
    "smoke_test_resilience_retention.py",
    "smoke_test_materialized_import_scope.py",
    "smoke_test_production_entrypoint_isolated.py",
    "smoke_test_v2_production_cutover.py",
    "audit_ui_labels.py",
)

_SECRET_ENV_KEYS = (
    "JJ_ADMIN_PIN",
    "JJ_ADMIN_EMAIL",
    "JJ_ADMIN_LOGIN_EMAIL",
    "JJ_ADMIN_LOGIN_PASSWORD",
    "JJ_ADMIN_PASSWORD",
)


def isolated_child_env(db_path: Path) -> dict[str, str]:
    """Return a production-like environment that cannot reach the real DB."""
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    for key in _SECRET_ENV_KEYS:
        env.pop(key, None)
    env["JJ_DB_PATH"] = str(db_path.resolve())
    env["JJ_ENABLE_DEMO_MEMBER"] = "0"
    env["JJ_ADMIN_NAME"] = "リリースゲート"
    # Exercise production cookie / fail-closed asset behavior while using SQLite.
    env["RENDER"] = "1"
    return env


def _run_test(filename: str) -> None:
    path = ROOT / filename
    if not path.is_file():
        raise RuntimeError(f"release-gate test is missing: {filename}")

    with tempfile.TemporaryDirectory(prefix="jj-release-gate-") as directory:
        db_path = Path(directory) / "release.sqlite3"
        env = isolated_child_env(db_path)
        if "DATABASE_URL" in env:
            raise RuntimeError("release gate isolation failure: DATABASE_URL leaked into child")
        if Path(env["JJ_DB_PATH"]).parent != Path(directory).resolve():
            raise RuntimeError("release gate isolation failure: SQLite path escaped temp directory")

        print(f"JJ_RELEASE_GATE_START test={filename}", flush=True)
        subprocess.run(
            [sys.executable, str(path)],
            cwd=str(ROOT),
            env=env,
            check=True,
        )
        print(f"JJ_RELEASE_GATE_PASS test={filename}", flush=True)


def main() -> None:
    # Render must produce the exact browser assets that app.py will later serve.
    build_assets()
    for filename in RELEASE_TESTS:
        _run_test(filename)
    print(f"JJ_PRODUCTION_RELEASE_GATE_OK tests={len(RELEASE_TESTS)}", flush=True)


if __name__ == "__main__":
    main()
