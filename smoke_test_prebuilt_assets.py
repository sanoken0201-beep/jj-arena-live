from __future__ import annotations

"""Regression for build-time browser assets and production fail-closed behavior."""

import hashlib
import os
import tempfile
from pathlib import Path

import served_assets


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    root = Path(__file__).resolve().parent
    build_entry_source = (root / "build_served_assets.py").read_text(encoding="utf-8")
    compiler_source = (root / "served_assets.py").read_text(encoding="utf-8")
    assert "sitngo_browser_config.install()" not in build_entry_source, (
        "build entrypoint must not initialize individual browser transforms"
    )
    assert compiler_source.count("sitngo_browser_config.install()") == 1, (
        "served_assets must be the single Sit&Go browser transform owner"
    )

    canonical = served_assets.MATERIALIZED_STATIC
    source_before = {
        name: _sha(canonical / name)
        for name in ("index.html", "app.js", "styles.css", "sw.js")
    }

    old_root = served_assets.BUILD_ROOT
    old_render = os.environ.get("RENDER")
    try:
        with tempfile.TemporaryDirectory(prefix="jj-prebuilt-assets-") as directory:
            root = Path(directory) / "built"
            first = served_assets.build_all(root)
            first_bytes = {
                relative: (root / relative).read_bytes()
                for relative in first["outputs"]
            }
            second = served_assets.build_all(root)
            served_assets.validate_built_assets(root)
            assert first == second, "asset manifest is not deterministic"
            assert first_bytes == {
                relative: (root / relative).read_bytes()
                for relative in second["outputs"]
            }, "compiled asset bytes changed across identical builds"

            source_after = {
                name: _sha(canonical / name)
                for name in ("index.html", "app.js", "styles.css", "sw.js")
            }
            assert source_before == source_after, "canonical materialized assets were mutated"

            missing = Path(directory) / "missing"
            served_assets.BUILD_ROOT = missing
            os.environ["RENDER"] = "1"
            try:
                served_assets.ensure_runtime_assets()
            except RuntimeError as exc:
                assert "prebuilt served assets" in str(exc)
            else:
                raise AssertionError("production silently compiled missing browser assets at runtime")
            assert not missing.exists(), "production fail-closed path created runtime build output"

            served_assets.BUILD_ROOT = root
            assert served_assets.ensure_runtime_assets() == root

        print("JJ_PREBUILT_ASSET_CONTRACT_OK")
    finally:
        served_assets.BUILD_ROOT = old_root
        if old_render is None:
            os.environ.pop("RENDER", None)
        else:
            os.environ["RENDER"] = old_render


if __name__ == "__main__":
    main()
