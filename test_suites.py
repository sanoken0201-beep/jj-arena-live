from __future__ import annotations

"""Named test ownership for JJ Arena.

The goal is not to reduce coverage. It is to make failures understandable and
keep release-gate selection explicit. Browser-only Playwright tests can belong
to a group without being executed inside Render.
"""

TEST_SUITES: dict[str, tuple[str, ...]] = {
    "auth_security": (
        "smoke_test_auth_hardening.py",
        "smoke_test_websocket_auth.py",
        "smoke_test_public_proxy_security.py",
        "smoke_test_structure_consolidation.py",
    ),
    "points_integrity": (
        "smoke_test_point_ledger_precision.py",
        "smoke_test_admin_reversal_safety.py",
        "smoke_test_admin_export_safety.py",
        "smoke_test_non_sng_safety.py",
    ),
    "ring_gameplay": (
        "smoke_test_v1244.py",
        "smoke_test_single_public_table.py",
        "smoke_test_poker_simple.py",
        "smoke_test_oop_check_browser.py",
        "smoke_test_poker_control_safety.py",
    ),
    "browser_contract": (
        "smoke_test_prebuilt_assets.py",
        "smoke_test_pwa_update.py",
        "audit_ui_labels.py",
    ),
    "runtime_release": (
        "smoke_test_runtime_performance.py",
        "smoke_test_runtime_observability.py",
        "smoke_test_resilience_retention.py",
        "smoke_test_materialized_import_scope.py",
        "smoke_test_production_entrypoint_isolated.py",
        "smoke_test_v2_production_cutover.py",
    ),
    "sitngo": (
        "smoke_test_sitngo_phase1.py",
        "smoke_test_sitngo_gameplay.py",
    ),
}

# Deterministic tests safe in the Render build image. Real-browser tests remain
# GitHub-only even though they are categorized above.
PRODUCTION_RELEASE_SELECTION: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("browser_contract", (
        "smoke_test_prebuilt_assets.py",
        "smoke_test_pwa_update.py",
        "audit_ui_labels.py",
    )),
    ("auth_security", (
        "smoke_test_public_proxy_security.py",
        "smoke_test_structure_consolidation.py",
    )),
    ("points_integrity", (
        "smoke_test_admin_reversal_safety.py",
        "smoke_test_admin_export_safety.py",
        "smoke_test_non_sng_safety.py",
        "smoke_test_point_ledger_precision.py",
    )),
    ("runtime_release", (
        "smoke_test_runtime_performance.py",
        "smoke_test_runtime_observability.py",
        "smoke_test_resilience_retention.py",
        "smoke_test_materialized_import_scope.py",
        "smoke_test_production_entrypoint_isolated.py",
        "smoke_test_v2_production_cutover.py",
    )),
    ("ring_gameplay", (
        "smoke_test_v1244.py",
        "smoke_test_single_public_table.py",
    )),
    ("sitngo", (
        "smoke_test_sitngo_phase1.py",
        "smoke_test_sitngo_gameplay.py",
    )),
)


def production_release_tests() -> tuple[tuple[str, str], ...]:
    return tuple(
        (group, filename)
        for group, filenames in PRODUCTION_RELEASE_SELECTION
        for filename in filenames
    )


__all__ = ["PRODUCTION_RELEASE_SELECTION", "TEST_SUITES", "production_release_tests"]
