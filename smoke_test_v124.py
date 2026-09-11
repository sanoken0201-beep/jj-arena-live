from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path

from runtime_builder import RUNTIME_VERSION, build_runtime
from smoke_test_v123 import (
    test_no_flop_no_drop,
    test_real_allin_runout_settles,
    test_showdown_hold_and_reasons,
    test_staged_allin_runout,
)
from smoke_test_v123_engine_integration import (
    _new_table,
    test_real_no_flop_no_drop,
    test_real_three_way_sidepot_runout,
)


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def test_legal_action_buttons(engine, app):
    start = app.index("  function jjV124ActionButtons(l){")
    end = app.index("  function jjV124DecisionMeta", start)
    renderer = app[start:end]
    cases = []
    for stack, expected in ((150, ["fold", "call", "allin"]),
                            (100, ["fold", "call"]),
                            (75, ["fold", "call"]),
                            (500, ["fold", "call", "raise"])):
        state = _new_table(engine, "action-buttons", [max(100, stack), 1000, 1000])
        hero = next(p for p in state["seats"] if p["user_id"] == 100)
        hero["stack"] = stack
        legal = engine.legal_actions(state, 100)
        assert legal["can_act"]
        cases.append({"hero": dict(hero), "legal": legal, "expected": expected})
        if stack == 150:
            assert not legal["can_raise"] and legal["can_all_in"]
            engine.apply_action(state, 100, "allin")
            assert hero["stack"] == 0 and hero["round_bet"] == 150
    script = """
const assert = require('node:assert/strict');
let hero;
const jjV124Hero=()=>hero, jjV124RawBb=n=>`${n/100}bb`;
const jjRaiseBounds=()=>({min:2}), $=()=>null;
const safe=String, jjV185FmtBb=String;
""" + renderer + "\nconst cases=" + json.dumps(cases) + """;
for (const c of cases) {
  hero=c.hero;
  const html=jjV124ActionButtons(c.legal);
  const actions=[...html.matchAll(/data-action="([^"]+)"/g)].map(m=>m[1]);
  assert.deepEqual(actions,c.expected);
  assert.equal(html.includes('ALL-IN CALL'),c.legal.call_amount>=hero.stack);
}
"""
    subprocess.run(["node", "-e", script], check=True)


def load_engine(root: Path):
    path = root / "poker_engine.py"
    spec = importlib.util.spec_from_file_location("jj_v124_runtime_engine", path)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load v1.24 runtime engine")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    # Preserve the v1.24 poker behavior in every later release. Version/cache
    # identity belongs to the current release-specific smoke test.
    assert _version_tuple(RUNTIME_VERSION) >= (1, 24, 0)
    with tempfile.TemporaryDirectory() as td:
        root = build_runtime(Path(td) / "runtime")
        engine = load_engine(root)
        server = (root / "server.py").read_text(encoding="utf-8")
        app = (root / "static" / "app.js").read_text(encoding="utf-8")
        css = (root / "static" / "styles.css").read_text(encoding="utf-8")
        index = (root / "static" / "index.html").read_text(encoding="utf-8")
        sw = (root / "static" / "sw.js").read_text(encoding="utf-8")

        assert f'version="{RUNTIME_VERSION}"' in server or f'"version":"{RUNTIME_VERSION}"' in server
        assert 'request.url.query == "v=' in server
        assert "?v=" in index
        assert "jj-arena-live-v" in sw

        marker = "v1.24.0 unified online-poker presentation layer"
        assert marker in app
        v124 = app.split(marker, 1)[1]
        assert app.rfind(marker) > app.rfind("v1.20.3 mobile bet-marker/call-amount hotfix")
        assert '<span class="jj-card-rank">' in v124
        assert '<b class="jj-card-rank">' not in v124
        assert 'id="jjV124CallAmount"' in v124
        assert 'id="jjV124CallButtonAmount"' in v124
        assert "function jjV124RawBb" in v124
        assert "Number(chips||0)/big" in v124
        assert "$('#actionBar .jj-action-context b')" not in v124
        assert "jj-hero-cards" not in v124
        for token in ("STREET", "POT", "TO CALL", "STACK", "EFFECTIVE", "TIME"):
            assert token in v124
        assert "jj-v124-stepper" in v124
        assert "data-jj-raise-step" in v124
        assert "jj-actions-${actions.length}" in v124
        assert "jj-main-actions.jj-actions-3" in css
        assert "grid-template-columns:repeat(3,minmax(0,1fr))" in css
        assert "callIsAllin" in v124
        assert "ALL-IN CALL" in v124
        assert "オールインコール" in v124
        test_legal_action_buttons(engine, app)
        assert "white-space:nowrap!important" in css
        assert "writing-mode:horizontal-tb!important" in css
        assert "jj-v124-stepper label span" in css
        assert "word-break:keep-all!important" in css
        assert "{left:61,top:68}" in v124
        assert "{left:61,top:25}" in v124
        assert "jj-v124-desktop-poker #pokerRoom .jj-seat.is-hero .jj-hole{z-index:20" in css
        assert "jj-v124-desktop-poker #pokerRoom .jj-bet-marker{z-index:9" in css

        test_no_flop_no_drop(engine)
        test_staged_allin_runout(engine)
        test_real_allin_runout_settles(engine)
        test_showdown_hold_and_reasons(engine)
        test_real_no_flop_no_drop(engine)
        test_real_three_way_sidepot_runout(engine)

    print("v1.24 poker regression preservation: ok")


if __name__ == "__main__":
    main()
