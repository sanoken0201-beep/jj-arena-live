"""Regression for complete Sit&Go acceptance-to-test traceability."""
from __future__ import annotations

from pathlib import Path

from sitngo_acceptance import SITNGO_ACCEPTANCE
from test_suites import BROWSER_ONLY_TESTS, production_release_tests, test_owner, tests_for_group

ROOT = Path(__file__).resolve().parent
SELF = "smoke_test_sitngo_acceptance_manifest.py"


def main() -> None:
    assert SITNGO_ACCEPTANCE, "Sit&Go acceptance manifest is empty"
    assert len(SITNGO_ACCEPTANCE) == len(set(SITNGO_ACCEPTANCE)), "duplicate acceptance ids"

    referenced: set[str] = set()
    for contract_id, contract in SITNGO_ACCEPTANCE.items():
        assert contract_id and contract_id == contract_id.strip()
        description = str(contract.get("description") or "").strip()
        tests = tuple(contract.get("tests") or ())
        assert len(description) >= 20, f"acceptance description too weak: {contract_id}"
        assert tests, f"acceptance contract has no regression: {contract_id}"
        for filename in tests:
            assert isinstance(filename, str) and filename.startswith("smoke_test_sitngo_")
            assert (ROOT / filename).is_file(), f"acceptance evidence missing: {contract_id} -> {filename}"
            assert test_owner(filename) == "sitngo", f"acceptance evidence has wrong owner: {filename}"
            referenced.add(filename)

    active = set(tests_for_group("sitngo")) - {SELF}
    missing = sorted(active - referenced)
    stale = sorted(referenced - active)
    assert not missing, f"active Sit&Go tests lack acceptance mapping: {missing}"
    assert not stale, f"acceptance manifest references inactive Sit&Go tests: {stale}"

    release = {filename for group, filename in production_release_tests() if group == "sitngo"}
    assert SELF in release, "acceptance manifest itself is not release-gated"
    assert "smoke_test_sitngo_browser.py" in BROWSER_ONLY_TESTS
    assert "smoke_test_sitngo_browser.py" not in release

    print(
        "JJ_SITNGO_ACCEPTANCE_MANIFEST_OK "
        f"contracts={len(SITNGO_ACCEPTANCE)} evidence_tests={len(referenced)}"
    )


if __name__ == "__main__":
    main()
