from __future__ import annotations

"""Named test ownership for JJ Arena.

This module is the source of truth for active regression ownership. Historical
one-off regression files may remain in the repository, but any test selected by
an active suite or the production release gate has exactly one owner here.

The goal is not to reduce coverage. It is to make failures understandable,
keep release-gate selection explicit, prevent browser-only tests from being
accidentally pulled into Render's production build image, and prevent tests that
were deliberately retired after supersession from silently returning.
"""
from pathlib import Path

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
        "smoke_test_poker_control_audit.py",
        "smoke_test_rake_settlement_fix.py",
    ),
    "browser_contract": (
        "smoke_test_prebuilt_assets.py",
        "smoke_test_pwa_update.py",
        "audit_ui_labels.py",
    ),
    "runtime_release": (
        "smoke_test_test_ownership.py",
        "smoke_test_feature_lifecycle.py",
        "smoke_test_runtime_builder_snapshot.py",
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

# Historical regressions that were deliberately removed because newer active
# suites cover the live contract. Keeping the filenames here makes accidental
# reintroduction visible in the ownership gate.
RETIRED_TEST_FILES = frozenset(
    {
        "smoke_test_v186.py",
        "smoke_test_mobile_poker_ux.py",
        "smoke_test_portrait_table.py",
        "smoke_test_clear_poker_copy.py",
        "smoke_test_admin.py",
        "smoke_test_ui_copy.py",
    }
)

# Tests that require a real browser / optional browser dependencies and therefore
# must never be selected by the Render production release gate.
BROWSER_ONLY_TESTS = frozenset(
    {
        "smoke_test_poker_simple.py",
        "smoke_test_oop_check_browser.py",
        "smoke_test_poker_control_audit.py",
    }
)

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
        "smoke_test_test_ownership.py",
        "smoke_test_feature_lifecycle.py",
        "smoke_test_runtime_builder_snapshot.py",
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
        "smoke_test_rake_settlement_fix.py",
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


def test_owner(filename: str) -> str:
    owners = [group for group, filenames in TEST_SUITES.items() if filename in filenames]
    if len(owners) != 1:
        raise RuntimeError(f"test ownership must be unique: test={filename} owners={owners}")
    return owners[0]


def tests_for_group(group: str) -> tuple[str, ...]:
    try:
        return TEST_SUITES[group]
    except KeyError as exc:
        raise KeyError(f"unknown JJ Arena test suite: {group}") from exc


def validate_test_ownership(root: Path | None = None) -> None:
    """Validate active suite ownership and Render release selection invariants."""
    seen: dict[str, str] = {}
    for group, filenames in TEST_SUITES.items():
        if not group or not filenames:
            raise RuntimeError(f"empty active test suite: {group!r}")
        for filename in filenames:
            previous = seen.get(filename)
            if previous is not None:
                raise RuntimeError(
                    f"test appears in multiple suites: test={filename} groups={[previous, group]}"
                )
            seen[filename] = group
            if root is not None and not (root / filename).is_file():
                raise RuntimeError(f"owned test file is missing: group={group} test={filename}")

    if RETIRED_TEST_FILES & set(seen):
        raise RuntimeError(
            f"retired test assigned to active suite: {sorted(RETIRED_TEST_FILES & set(seen))}"
        )
    if root is not None:
        restored = sorted(filename for filename in RETIRED_TEST_FILES if (root / filename).exists())
        if restored:
            raise RuntimeError(f"retired test file has returned: {restored}")

    release_seen: set[str] = set()
    for group, filenames in PRODUCTION_RELEASE_SELECTION:
        if group not in TEST_SUITES:
            raise RuntimeError(f"release selection references unknown suite: {group}")
        for filename in filenames:
            owner = test_owner(filename)
            if owner != group:
                raise RuntimeError(
                    f"release test selected by wrong suite: test={filename} selected={group} owner={owner}"
                )
            if filename in release_seen:
                raise RuntimeError(f"duplicate production release test: {filename}")
            release_seen.add(filename)
            if filename in BROWSER_ONLY_TESTS:
                raise RuntimeError(f"browser-only test selected for Render release gate: {filename}")


validate_test_ownership()

__all__ = [
    "BROWSER_ONLY_TESTS",
    "PRODUCTION_RELEASE_SELECTION",
    "RETIRED_TEST_FILES",
    "TEST_SUITES",
    "production_release_tests",
    "test_owner",
    "tests_for_group",
    "validate_test_ownership",
]
