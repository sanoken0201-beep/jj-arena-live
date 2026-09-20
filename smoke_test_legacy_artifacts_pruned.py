from __future__ import annotations

"""Guard the Stage 7B.2 removal of orphaned historical artifacts."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent
REMOVED_ARTIFACTS = (
    ROOT / "release_v14",
    ROOT / "v18_assets",
    ROOT / "v54_patch.py",
)


def main() -> None:
    restored = [str(path.relative_to(ROOT)) for path in REMOVED_ARTIFACTS if path.exists()]
    if restored:
        raise RuntimeError(f"Stage 7B.2 legacy artifact returned: {restored}")

    runtime_builder = (ROOT / "runtime_builder.py").read_text(encoding="utf-8")
    if 'SOURCE_DIR = MATERIALIZED_DIR.resolve()' not in runtime_builder:
        raise RuntimeError("compatibility builder no longer uses materialized_v1244 as its source")
    if "build_runtime" not in runtime_builder or "verify_materialized_source" not in runtime_builder:
        raise RuntimeError("compatibility runtime verification contract is incomplete")

    print("JJ_STAGE7B2_LEGACY_PRUNED_OK")


if __name__ == "__main__":
    main()
