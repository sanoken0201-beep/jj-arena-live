from __future__ import annotations

import tempfile
from pathlib import Path

from non_sng_safety import MARKER, apply_to_build
from poker_connection_fix import apply_to_build as apply_oop_check_freshness
from poker_control_safety import apply_to_build as apply_poker_control_safety
from served_assets import build_all


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="jj-non-sng-safety-") as directory:
        root = Path(directory)
        manifest = build_all(root)
        manifest = apply_oop_check_freshness(root, manifest)
        manifest = apply_poker_control_safety(root, manifest)
        manifest = apply_to_build(root, manifest)

        js = (root / "static/app.js").read_text(encoding="utf-8")
        index = (root / "index.html").read_text(encoding="utf-8")
        assert MARKER in js
        assert "form.dataset.jjSubmitting==='1'" in js
        assert "form.dataset.jjSubmitting='1'" in js
        assert "submit.disabled=true" in js
        assert "delete form.dataset.jjSubmitting" in js
        assert "submit.disabled=false" in js
        assert "ns=point-submit-safety-20260917-1" in index
        assert manifest["post_transforms"]["non_sng_safety"] == MARKER

    print("JJ_NON_SNG_SAFETY_OK")


if __name__ == "__main__":
    main()
