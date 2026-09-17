from __future__ import annotations

import os
import tempfile
from pathlib import Path

import production_release_gate as gate
from test_suites import PRODUCTION_RELEASE_SELECTION, production_release_tests


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
            "smoke_test_public_proxy_security.py",
            "smoke_test_structure_consolidation.py",
            "smoke_test_admin_reversal_safety.py",
            "smoke_test_admin_export_safety.py",
            "smoke_test_non_sng_safety.py",
            "smoke_test_test_ownership.py",
            "smoke_test_feature_lifecycle.py",
            "smoke_test_root_core_pruned.py",
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
            "smoke_test_sitngo_gameplay.py",
            "audit_ui_labels.py",
        }
        assert gate.RELEASE_TESTS == production_release_tests()
        assert {filename for _, filename in gate.RELEASE_TESTS} == expected
        assert {group for group, _ in gate.RELEASE_TESTS} == {
            group for group, _ in PRODUCTION_RELEASE_SELECTION
        }
        for group, filename in gate.RELEASE_TESTS:
            assert group
            assert (gate.ROOT / filename).is_file(), filename

        wrapper = (gate.ROOT / "smoke_test_v190.py").read_text(encoding="utf-8")
        assert "production_release_gate import main" in wrapper
        # Reproduce a test replacing final assets with base-only output. The
        # release gate must always rebuild the complete final pipeline after all
        # isolated tests, regardless of their group ownership.
        from unittest.mock import patch
        import build_served_assets as compiler
        import served_assets
        from browser_runtime_consolidation import MARKER as runtime_browser_marker
        from browser_structure_consolidation import MARKER as structure_marker
        from non_sng_safety import MARKER as non_sng_marker
        from poker_connection_fix import MARKER as connection_marker
        from poker_control_safety import MARKER as controls_marker
        with tempfile.TemporaryDirectory(prefix="jj-final-assets-") as directory:
            root = Path(directory)
            def overwrite(_filename, *, group="adhoc"):
                assert group
                served_assets.build_all(root)
            with patch.object(compiler, "BUILD_ROOT", root), patch.object(gate, "_run_test", overwrite):
                gate.main()
            js = (root / "static/app.js").read_text()
            assert connection_marker in js
            assert controls_marker in js
            assert non_sng_marker in js
            assert structure_marker in js
            assert runtime_browser_marker in js
            manifest = served_assets.validate_built_assets(root)
            assert manifest.get("pipeline_version") == 3
            assert manifest.get("pipeline_stages") == [
                "oop_check_freshness",
                "poker_control_safety",
                "non_sng_safety",
                "structure_consolidation",
                "runtime_browser_consolidation",
            ]
            assert manifest.get("browser_output_contract") == "canonical-prebuilt-v1"
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
