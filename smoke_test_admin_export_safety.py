from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import admin_copy_patch


def main() -> None:
    source = Path(__file__).resolve().parent / "admin_static"
    with tempfile.TemporaryDirectory(prefix="jj-admin-export-safety-") as directory:
        target = Path(directory) / "admin_static"
        shutil.copytree(source, target)
        admin_copy_patch.apply(target)

        html = (target / "index.html").read_text(encoding="utf-8")
        js = (target / "admin.js").read_text(encoding="utf-8")

        assert f"admin.js?v={admin_copy_patch.ADMIN_ASSET_VERSION}" in html
        # Spreadsheet-formula prefixes in user-controlled string cells are
        # prefixed with an apostrophe before normal CSV quoting.
        assert "typeof raw==='string'" in js
        assert "[=+\\-@]" in js
        assert "txt=\"'\"+txt" in js

        # Manual point adjustments are accounting mutations: only one request
        # may be in flight from the form at a time, including on failure paths.
        assert "if(form.dataset.submitting)return" in js
        assert "form.dataset.submitting='1'" in js
        assert "buttons.forEach(b=>b.disabled=true)" in js
        assert "delete form.dataset.submitting" in js
        assert "buttons.forEach(b=>b.disabled=false)" in js

    print("JJ_ADMIN_EXPORT_SAFETY_OK")


if __name__ == "__main__":
    main()
