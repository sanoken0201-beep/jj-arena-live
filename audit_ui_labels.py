from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

import admin_copy_patch
from runtime_builder import RUNTIME_VERSION, build_runtime

ROOT = Path(__file__).resolve().parent
WORK = Path(tempfile.mkdtemp(prefix="jj-ui-audit-"))
DEST = build_runtime(WORK / "runtime")
ADMIN = WORK / "admin_static"
shutil.copytree(ROOT / "admin_static", ADMIN)
admin_copy_patch.apply(ADMIN)

files = [
    DEST / "static" / "index.html",
    DEST / "static" / "app.js",
    ADMIN / "index.html",
    ADMIN / "admin.js",
    ADMIN / "admin_delete.js",
    ADMIN / "admin_pin_verify.js",
    ADMIN / "admin_ui_foundation.js",
]

# Keep this audit intentionally broad: it lists Japanese UI copy and a small set
# of English operational labels so future UI passes can spot drift quickly.
seen: set[tuple[str, str]] = set()
out: list[tuple[str, str]] = []
pat_q = re.compile(r"(['\"`])((?:\\.|(?!\1).){1,180})\1", re.S)
pat_html = re.compile(r">([^<>]{1,120})<")
for path in files:
    text = path.read_text(encoding="utf-8")
    vals = [m.group(2) for m in pat_q.finditer(text)]
    vals += [m.group(1) for m in pat_html.finditer(text)]
    for value in vals:
        value = re.sub(r"\\[nrt]", " ", value)
        value = re.sub(r"\s+", " ", value).strip()
        if not value or len(value) > 160:
            continue
        if not (
            re.search(r"[ぁ-んァ-ン一-龯]", value)
            or re.search(
                r"\b(READY|Lobby|Rebuy|SIT OUT|ACTIVE|DELETE|CANCEL|SAVE|OPEN TABLE|HAND IN PROGRESS|STRATEGY|MOTIVATION)\b",
                value,
                re.I,
            )
        ):
            continue
        key = (path.name, value)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)

for name, value in out:
    print(f"{name}\t{value}", flush=True)

# Administrator-facing copy should remain consistent with the current policy.
admin_index = (ADMIN / "index.html").read_text(encoding="utf-8")
admin_js = (ADMIN / "admin.js").read_text(encoding="utf-8")
assert "ポイント振込" not in admin_index
assert "＋ 振込" not in admin_index
assert "ポイント振込" not in admin_js
assert "'ACTIVE'" not in admin_js
assert "admin_ui_foundation.css" in admin_index
assert "admin_ui_foundation.js" in admin_index
assert "admin_pin_verify.js" in admin_index

print(f"UI_LABEL_AUDIT_OK version={RUNTIME_VERSION} count={len(out)}", flush=True)
