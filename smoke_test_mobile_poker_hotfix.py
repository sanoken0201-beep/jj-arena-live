from __future__ import annotations

import py_compile
import tempfile
from pathlib import Path

from runtime_builder import RUNTIME_VERSION, build_runtime

ROOT = Path(__file__).resolve().parent
WORK = Path(tempfile.mkdtemp(prefix="jj-mobile-hotfix-smoke-"))
DEST = build_runtime(WORK / "runtime")

server = (DEST / "server.py").read_text(encoding="utf-8")
appjs = (DEST / "static" / "app.js").read_text(encoding="utf-8")
css = (DEST / "static" / "styles.css").read_text(encoding="utf-8")
index = (DEST / "static" / "index.html").read_text(encoding="utf-8")
sw = (DEST / "static" / "sw.js").read_text(encoding="utf-8")

assert tuple(int(part) for part in RUNTIME_VERSION.split(".")) >= (1, 20, 3)
legacy_marker = "v1.20.3 mobile bet-marker/call-amount hotfix"
final_marker = "v1.24.0 unified online-poker presentation layer"
assert legacy_marker in appjs
assert final_marker in appjs
assert appjs.rfind(final_marker) > appjs.rfind(legacy_marker)
final = appjs.split(final_marker, 1)[1]
assert "function jjV124RawBb" in final
assert "Number(chips||0)/big" in final
assert 'id="jjV124CallAmount"' in final
assert 'id="jjV124CallButtonAmount"' in final
assert '<span class="jj-card-rank">' in final
assert "$('#actionBar .jj-action-context b')" not in final
assert "if(visual===0)return {left:p.left,top:56.5};" in appjs
assert "if(visual===3)return {left:p.left,top:27};" in appjs
assert "jjV124MobileBetPos(actual)" in final
assert "pointer-events:none!important" in css

assert f'version="{RUNTIME_VERSION}"' in server or f'"version":"{RUNTIME_VERSION}"' in server
assert 'request.url.query == "v=' in server
assert "?v=" in index
assert "jj-arena-live-v" in sw

for filename in ("mobile_poker_hotfix.py", "v52_patch.py", "v52_post_patch.py", "v53_patch.py", "v54_patch.py", "v55_patch.py", "v55_post_patch.py", "runtime_builder.py"):
    py_compile.compile(str(ROOT / filename), doraise=True)
print("MOBILE_POKER_HOTFIX_SMOKE_OK")
