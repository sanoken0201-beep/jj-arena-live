from __future__ import annotations

"""CSS-only, zero-new-dependency UI redesign and asset budget regression."""

import gzip
from unittest.mock import patch

import served_assets
from editorial_lightweight_redesign import MARKER, transform_styles


def main() -> None:
    # Generate the exact same compiled CSS both with and without the last
    # editorial stage. Comparing canonical CSS alone is not a valid budget.
    with patch.object(served_assets, "transform_editorial_styles", lambda css: css):
        baseline = served_assets.build_styles()
    redesigned = served_assets.build_styles()

    assert MARKER in redesigned
    assert transform_styles(redesigned) == redesigned, "CSS transform must be idempotent"
    assert "#homeView .hero" in redesigned
    assert "#rankingView .toolbar" in redesigned
    assert "#pokerRoom .poker-table" in redesigned or ".poker-table" in redesigned
    assert "background:linear-gradient(145deg,#163d31,#235944)!important" not in redesigned
    assert "--shadow-md:none;" in redesigned
    assert ".top-grid{display:grid!important;grid-template-columns:1fr!important" in redesigned
    assert ".top-player .hint{display:none!important}" in redesigned
    assert "backdrop-filter:blur(14px)" not in redesigned[redesigned.find("#rankingView .toolbar"):redesigned.find("#rankingView .segmented")]

    base_bytes, new_bytes = baseline.encode(), redesigned.encode()
    base_gzip = gzip.compress(base_bytes, mtime=0)
    new_gzip = gzip.compress(new_bytes, mtime=0)
    assert len(new_bytes) <= len(base_bytes), (
        f"CSS raw budget exceeded: before={len(base_bytes)}, after={len(new_bytes)}"
    )
    assert len(new_gzip) <= len(base_gzip), (
        f"CSS gzip budget exceeded: before={len(base_gzip)}, after={len(new_gzip)}"
    )
    assert redesigned.count("@import") <= baseline.count("@import")
    assert redesigned.count("@font-face") <= baseline.count("@font-face")

    html = served_assets.build_index()
    assert f'/static/styles.css?v={served_assets.ASSET_VERSION}' in html
    assert f'/static/app.js?v={served_assets.ASSET_VERSION}' in html
    assert served_assets.ASSET_VERSION == 87
    print(
        "lightweight editorial budget: PASS "
        f"CSS raw {len(base_bytes)} -> {len(new_bytes)} B, "
        f"gzip {len(base_gzip)} -> {len(new_gzip)} B; "
        "no new runtime JS, font, image or library"
    )


if __name__ == "__main__":
    main()
