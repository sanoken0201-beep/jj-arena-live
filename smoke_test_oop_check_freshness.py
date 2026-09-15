from __future__ import annotations

import tempfile
from pathlib import Path

from poker_connection_fix import CACHE_QUERY, MARKER, apply_to_build
from served_assets import build_all, validate_built_assets


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="jj-oop-check-") as directory:
        root = Path(directory)
        manifest = build_all(root)
        manifest = apply_to_build(root, manifest)
        validate_built_assets(root)

        app = (root / "static/app.js").read_text(encoding="utf-8")
        index = (root / "index.html").read_text(encoding="utf-8")

        assert MARKER in app
        assert "function jjV71SocketOpen(id)" in app
        assert "const preserveFresh=!!tableState&&!!jjV2Connection.fresh;" in app
        assert "jjV71SocketOpen(id);" in app
        assert "jjV2SetConnection('syncing',false);\n      tableHeartbeat=setInterval" not in app
        assert "const latest=await api('/tables/'+id);" in app
        assert "jjV2AcceptState('poll',before);" in app
        assert CACHE_QUERY in index
        assert manifest.get("post_transforms", {}).get("oop_check_freshness") == MARKER

        # Re-applying the post-transform must be safe for deterministic builds.
        again = apply_to_build(root, manifest)
        validate_built_assets(root)
        assert again["outputs"] == manifest["outputs"]

    print("JJ_OOP_CHECK_FRESHNESS_OK")


if __name__ == "__main__":
    main()
