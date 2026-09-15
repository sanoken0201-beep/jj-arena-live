from __future__ import annotations

import os
import tempfile
from pathlib import Path

import production_release_gate as gate


def main() -> None:
    original_database_url = os.environ.get("DATABASE_URL")
    original_secret = os.environ.get("JJ_ADMIN_PIN")
    try:
        os.environ["DATABASE_URL"] = "postgresql://production-must-never-be-used.invalid/jj"
        os.environ["JJ_ADMIN_PIN"] = "999999"
        with tempfile.TemporaryDirectory(prefix="jj-release-gate-contract-") as directory:
            db_path = Path(directory) / "isolated.sqlite3"
            env = gate.isolated_child_env(db_path)
            assert "DATABASE_URL" not in env
            assert "JJ_ADMIN_PIN" not in env
            assert env["JJ_DB_PATH"] == str(db_path.resolve())
            assert env["JJ_ENABLE_DEMO_MEMBER"] == "0"
            assert env["RENDER"] == "1"

        expected = {
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
            "smoke_test_single_public_table.py",
            "smoke_test_sitngo_phase1.py",
            "smoke_test_poker_table_focus.py",
            "audit_ui_labels.py",
        }
        assert set(gate.RELEASE_TESTS) == expected
        for filename in gate.RELEASE_TESTS:
            assert (gate.ROOT / filename).is_file(), filename

        wrapper = (gate.ROOT / "smoke_test_v190.py").read_text(encoding="utf-8")
        assert "production_release_gate import main" in wrapper
        print("JJ_PRODUCTION_RELEASE_GATE_CONTRACT_OK")
    finally:
        if original_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_database_url
        if original_secret is None:
            os.environ.pop("JJ_ADMIN_PIN", None)
        else:
            os.environ["JJ_ADMIN_PIN"] = original_secret


if __name__ == "__main__":
    main()
