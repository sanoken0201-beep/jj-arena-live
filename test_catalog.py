from __future__ import annotations

"""Central test catalog for JJ Arena.

Workflow names may remain stable for branch protection, but test ownership is
organized by product surface rather than historical implementation phase.
"""

SUITES: dict[str, tuple[str, ...]] = {
    "auth-security": (
        "smoke_test_auth_hardening.py",
        "smoke_test_websocket_auth.py",
        "smoke_test_public_proxy_security.py",
        "smoke_test_admin_api_consolidation.py",
    ),
    "points-integrity": (
        "smoke_test_point_ledger_precision.py",
        "smoke_test_admin_reversal_safety.py",
        "smoke_test_admin_export_safety.py",
        "smoke_test_non_sng_safety.py",
    ),
    "frontend-contract": (
        "smoke_test_prebuilt_assets.py",
        "smoke_test_pwa_update.py",
        "smoke_test_frontend_pipeline.py",
        "smoke_test_feature_lifecycle.py",
        "audit_ui_labels.py",
    ),
    "ring-gameplay": (
        "smoke_test_v1244.py",
        "smoke_test_single_public_table.py",
        "smoke_test_runtime_performance.py",
        "smoke_test_runtime_observability.py",
        "smoke_test_resilience_retention.py",
    ),
    "production-architecture": (
        "smoke_test_materialized_import_scope.py",
        "smoke_test_production_entrypoint_isolated.py",
        "smoke_test_v2_production_cutover.py",
    ),
    "sitngo": (
        "smoke_test_sitngo_phase1.py",
        "smoke_test_sitngo_gameplay.py",
    ),
}

# Render-safe critical subset. Keep the order stable because build logs are used
# operationally to identify the first broken surface.
PRODUCTION_RELEASE_TESTS: tuple[str, ...] = (
    "smoke_test_prebuilt_assets.py",
    "smoke_test_pwa_update.py",
    "smoke_test_frontend_pipeline.py",
    "smoke_test_feature_lifecycle.py",
    "smoke_test_public_proxy_security.py",
    "smoke_test_admin_api_consolidation.py",
    "smoke_test_admin_reversal_safety.py",
    "smoke_test_admin_export_safety.py",
    "smoke_test_non_sng_safety.py",
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
)


def suite_for(test_name: str) -> str | None:
    for suite, tests in SUITES.items():
        if test_name in tests:
            return suite
    return None


def main() -> None:
    for suite, tests in SUITES.items():
        print(f"[{suite}]")
        for test in tests:
            print(f"  {test}")


if __name__ == "__main__":
    main()
