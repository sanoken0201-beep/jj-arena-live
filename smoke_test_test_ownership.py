from __future__ import annotations

from pathlib import Path

import production_release_gate as gate
from test_suites import (
    BROWSER_ONLY_TESTS,
    TEST_SUITES,
    production_release_tests,
    test_owner,
    tests_for_group,
    validate_test_ownership,
)


def main() -> None:
    root = Path(__file__).resolve().parent
    validate_test_ownership(root)

    # Critical ownership boundaries. These assertions make accidental movement
    # visible in review instead of silently changing which concern owns a test.
    assert test_owner("smoke_test_auth_hardening.py") == "auth_security"
    assert test_owner("smoke_test_point_ledger_precision.py") == "points_integrity"
    assert test_owner("smoke_test_single_public_table.py") == "ring_gameplay"
    assert test_owner("smoke_test_prebuilt_assets.py") == "browser_contract"
    assert test_owner("smoke_test_feature_lifecycle.py") == "runtime_release"
    assert test_owner("smoke_test_sitngo_gameplay.py") == "sitngo"

    # Browser-only coverage belongs to a named suite but may not enter Render's
    # production-dependency release gate.
    assert BROWSER_ONLY_TESTS <= set(tests_for_group("ring_gameplay"))
    release_files = {filename for _, filename in production_release_tests()}
    assert not (BROWSER_ONLY_TESTS & release_files)

    # The executable release gate must consume the ownership source of truth,
    # not maintain a second hand-written list.
    assert gate.RELEASE_TESTS == production_release_tests()

    # Every active suite is non-empty and every active test has one owner.
    assert set(TEST_SUITES) == {
        "auth_security",
        "points_integrity",
        "ring_gameplay",
        "browser_contract",
        "runtime_release",
        "sitngo",
    }

    print("JJ_TEST_OWNERSHIP_OK")


if __name__ == "__main__":
    main()
