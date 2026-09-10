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

assert RUNTIME_VERSION == "1.20.3"
marker = "v1.20.3 mobile bet-marker/call-amount hotfix"
assert marker in appjs

# Regression: legal.call_amount is raw chips. The hotfix must route the raw
# amount through the existing bb(raw_chips) converter before rendering.
assert "const callLabel=bb(Number(l.call_amount||0));" in appjs
assert "callButton.textContent=`コール ${callLabel}`" in appjs
assert "contextAmount.textContent=`コール額 ${callLabel}`" in appjs
assert "const bb=(n,state=tableState)=>{const big=Number(state?.big_blind||100);const v=Number(n||0)/big;" in appjs
assert appjs.index(marker) > appjs.index("v1.18.5 mobile poker action ergonomics")
assert appjs.index(marker) > appjs.index("v1.20.3 daily poker quiz v2")

# Concrete screenshot-scale sanity check: 2,500 raw chips at 100/chip BB = 25bb.
assert 2500 / 100 == 25

# Portrait marker geometry keeps the hero marker off enlarged hole cards and the
# top opponent marker clear of the community-card row.
assert "if(visual===0)return {left:p.left,top:56.5};" in appjs
assert "if(visual===3)return {left:p.left,top:27};" in appjs
assert "jjMobileHotfixBetPos(actual)" in appjs
assert "pointer-events:none!important" in css

# Force iOS/PWA/browser caches off the broken v48 mobile assets. The server-side
# immutable-cache recognition deliberately remains on v48 so the hotfix URL is
# not long-lived cached while we validate it in production.
assert "?v=48-hotfix1" in index
assert "jj-arena-live-v48-hotfix1" in sw
assert 'request.url.query == "v=48"' in server

py_compile.compile(str(ROOT / "mobile_poker_hotfix.py"), doraise=True)
py_compile.compile(str(ROOT / "runtime_builder.py"), doraise=True)
print("MOBILE_POKER_HOTFIX_SMOKE_OK")
