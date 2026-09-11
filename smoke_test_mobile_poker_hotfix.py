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

assert RUNTIME_VERSION == "1.24.2"
legacy_marker = "v1.20.3 mobile bet-marker/call-amount hotfix"
final_marker = "v1.24.0 unified online-poker presentation layer"
assert legacy_marker in appjs
assert final_marker in appjs
assert appjs.rfind(final_marker) > appjs.rfind(legacy_marker)

# The legacy raw-chip correction remains in the compatibility history, but v1.24
# owns the final renderer and uses dedicated call amount nodes. This specifically
# prevents the old generic `.jj-action-context b` lookup from rewriting a card rank.
final = appjs.split(final_marker, 1)[1]
assert "function jjV124RawBb" in final
assert "Number(chips||0)/big" in final
assert 'id="jjV124CallAmount"' in final
assert 'id="jjV124CallButtonAmount"' in final
assert '<span class="jj-card-rank">' in final
assert "$('#actionBar .jj-action-context b')" not in final

# Portrait mobile geometry from the validated hotfix remains available upstream;
# v1.24 only replaces desktop bet lanes.
assert "if(visual===0)return {left:p.left,top:56.5};" in appjs
assert "if(visual===3)return {left:p.left,top:27};" in appjs
assert "jjV124MobileBetPos(actual)" in final
assert "pointer-events:none!important" in css

# v1.24.2 owns browser caching and the production query key.
assert "?v=54" in index
assert "jj-arena-live-v54" in sw
assert 'request.url.query == "v=54"' in server

py_compile.compile(str(ROOT / "mobile_poker_hotfix.py"), doraise=True)
py_compile.compile(str(ROOT / "v52_patch.py"), doraise=True)
py_compile.compile(str(ROOT / "v52_post_patch.py"), doraise=True)
py_compile.compile(str(ROOT / "v53_patch.py"), doraise=True)
py_compile.compile(str(ROOT / "runtime_builder.py"), doraise=True)
print("MOBILE_POKER_HOTFIX_SMOKE_OK")
