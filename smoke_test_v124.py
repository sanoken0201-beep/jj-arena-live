from __future__ import annotations

import importlib.util
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
    test_real_no_flop_no_drop,
    test_real_three_way_sidepot_runout,
)


def load_engine(root: Path):
    path = root / "poker_engine.py"
    spec = importlib.util.spec_from_file_location("jj_v124_runtime_engine", path)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load v1.24 runtime engine")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    assert RUNTIME_VERSION == "1.24.0"
    with tempfile.TemporaryDirectory() as td:
        root = build_runtime(Path(td) / "runtime")
        engine = load_engine(root)
        server = (root / "server.py").read_text(encoding="utf-8")
        app = (root / "static" / "app.js").read_text(encoding="utf-8")
        css = (root / "static" / "styles.css").read_text(encoding="utf-8")
        index = (root / "static" / "index.html").read_text(encoding="utf-8")
        sw = (root / "static" / "sw.js").read_text(encoding="utf-8")

        assert 'version="1.24.0"' in server or '"version":"1.24.0"' in server
        assert 'request.url.query == "v=52"' in server
        assert "?v=52" in index
        assert "jj-arena-live-v52" in sw

        marker = "v1.24.0 unified online-poker presentation layer"
        assert marker in app
        v124 = app.split(marker, 1)[1]
        assert app.rfind(marker) > app.rfind("v1.20.3 mobile bet-marker/call-amount hotfix")

        # Regression for the screenshot bug: no rank is a <b> descendant that an
        # old generic call-amount selector can overwrite. Call amount has its own id.
        assert '<span class="jj-card-rank">' in v124
        assert '<b class="jj-card-rank">' not in v124
        assert 'id="jjV124CallAmount"' in v124
        assert 'id="jjV124CallButtonAmount"' in v124
        assert "function jjV124RawBb" in v124
        assert "Number(chips||0)/big" in v124
        assert "$('#actionBar .jj-action-context b')" not in v124
        assert "jj-hero-cards" not in v124

        # Desktop action system: one fact row, one sizing row, one primary action row.
        for token in ("STREET", "POT", "TO CALL", "STACK", "EFFECTIVE", "TIME"):
            assert token in v124
        assert "jj-v124-stepper" in v124
        assert "data-jj-raise-step" in v124
        assert "jj-actions-${actions.length}" in v124
        assert "jj-main-actions.jj-actions-3" in css
        assert "grid-template-columns:repeat(3,minmax(0,1fr))" in css

        # Cards and units are structural non-wrapping elements on desktop.
        assert "white-space:nowrap!important" in css
        assert "writing-mode:horizontal-tb!important" in css
        assert "jj-v124-stepper label span" in css
        assert "word-break:keep-all!important" in css

        # Bet chips and hole cards must occupy separate desktop visual lanes.
        assert "{left:61,top:68}" in v124
        assert "{left:61,top:25}" in v124
        assert "jj-v124-desktop-poker #pokerRoom .jj-seat.is-hero .jj-hole{z-index:20" in css
        assert "jj-v124-desktop-poker #pokerRoom .jj-bet-marker{z-index:9" in css

        # Existing v1.23 game rules and safety remain authoritative.
        test_no_flop_no_drop(engine)
        test_staged_allin_runout(engine)
        test_real_allin_runout_settles(engine)
        test_showdown_hold_and_reasons(engine)
        test_real_no_flop_no_drop(engine)
        test_real_three_way_sidepot_runout(engine)

    print("v1.24 unified online poker redesign smoke: ok")


if __name__ == "__main__":
    main()
