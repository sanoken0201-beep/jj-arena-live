from __future__ import annotations

import tempfile
from pathlib import Path

from frontend_build_pipeline import PIPELINE_VERSION, POST_BUILD_STAGES, build_production_frontend
from frontend_governance import ADMIN_NEW, ADMIN_OLD, MARKER as GOVERNANCE_MARKER
from non_sng_safety import MARKER as NON_SNG_MARKER
from poker_connection_fix import MARKER as CONNECTION_MARKER
from poker_control_safety import MARKER as CONTROL_MARKER
from served_assets import validate_built_assets


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="jj-frontend-pipeline-") as directory:
        root = Path(directory)
        first = build_production_frontend(root)
        validate_built_assets(root)
        first_outputs = dict(first["outputs"])
        first_app = (root / "static/app.js").read_text(encoding="utf-8")
        first_index = (root / "index.html").read_text(encoding="utf-8")

        pipeline = first.get("frontend_pipeline") or {}
        assert pipeline.get("version") == PIPELINE_VERSION
        assert pipeline.get("compatibility_compiler") == "served_assets.build_all"
        assert pipeline.get("post_build_stages") == [name for name, _ in POST_BUILD_STAGES]

        for marker in (CONNECTION_MARKER, CONTROL_MARKER, NON_SNG_MARKER, GOVERNANCE_MARKER):
            assert marker in first_app, marker

        assert ADMIN_OLD not in first_app
        assert ADMIN_NEW in first_app
        assert 'data-view="schedule"' not in first_index
        assert 'data-view="discussion"' not in first_index

        # The production compiler must be deterministic. Rebuilding the same
        # immutable inputs into the same directory cannot change output hashes.
        second = build_production_frontend(root)
        assert second["outputs"] == first_outputs
        assert (root / "static/app.js").read_text(encoding="utf-8") == first_app
        assert (root / "index.html").read_text(encoding="utf-8") == first_index

    print("JJ_FRONTEND_PIPELINE_OK")


if __name__ == "__main__":
    main()
