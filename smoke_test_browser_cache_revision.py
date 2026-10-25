"""No browser may reuse immutable JavaScript after an app-only deployment."""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

from browser_asset_pipeline import finalize_build, stamp_browser_cache
from served_assets import build_all, validate_built_assets


def _snapshot(root: Path) -> tuple[str, str, str]:
    html = (root / "index.html").read_text(encoding="utf-8")
    sw = (root / "static/sw.js").read_text(encoding="utf-8")
    js_url = re.search(r'(/static/app\.js\?[^"\s]+)', html)
    css_url = re.search(r'(/static/styles\.css\?[^"\s]+)', html)
    cache = re.search(r"const CACHE='([^']+)';", sw)
    assert js_url and css_url and cache
    assert f"'{js_url.group(1)}'" in sw
    assert f"'{css_url.group(1)}'" in sw
    return js_url.group(1), css_url.group(1), cache.group(1)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="jj-cache-revision-") as td:
        root = Path(td)
        manifest = finalize_build(root, build_all(root))
        validate_built_assets(root)
        original = _snapshot(root)
        assert all("&build=" in url for url in original[:2])

        # A repeat of an identical production build must retain its URLs.
        assert original == _snapshot(root)
        old_outputs = dict(manifest["outputs"])
        unchanged = stamp_browser_cache(root, manifest)
        assert _snapshot(root) == original
        assert unchanged["outputs"] == old_outputs

        # Test the previously broken case: app.js changes, while the manual
        # asset version and build-index code do not change.
        script = root / "static/app.js"
        script.write_text(script.read_text(encoding="utf-8") + "\n// browser cache regression\n", encoding="utf-8")
        manifest = stamp_browser_cache(root, manifest)
        new_js, new_css, new_cache = _snapshot(root)
        assert new_js != original[0], "changed JS reused the old immutable URL"
        assert new_css == original[1], "unmodified CSS need not be redownloaded"
        assert new_cache != original[2], "unchanged SW leaves old clients stale"

        stylesheet = root / "static/styles.css"
        stylesheet.write_text(stylesheet.read_text(encoding="utf-8") + "\n/* cache revision */\n", encoding="utf-8")
        stamp_browser_cache(root, manifest)
        newer_js, newer_css, newer_cache = _snapshot(root)
        assert newer_js == new_js
        assert newer_css != new_css
        assert newer_cache != new_cache
    print("JJ_BROWSER_CACHE_REVISION_OK")


if __name__ == "__main__":
    main()
