from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

from runtime_builder import RUNTIME_VERSION, build_runtime


def load_engine(root: Path):
    path = root / "poker_engine.py"
    spec = importlib.util.spec_from_file_location("jj_v123_runtime_engine", path)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load v1.23 runtime engine")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_flop_no_drop(engine) -> None:
    original_finish = engine._jj_v123_base_finish_hand
    original_award = engine._jj_v123_base_award_uncontested
    try:
        engine._jj_v123_base_finish_hand = lambda state: state.update({"status": "waiting"})

        def forbidden_legacy_award(_state):
            raise AssertionError("preflop uncontested pot must bypass legacy rake settlement")

        engine._jj_v123_base_award_uncontested = forbidden_legacy_award
        state = {
            "status": "playing",
            "big_blind": 100,
            "seats": [
                {"user_id": 1, "name": "アリス", "seat": 0, "stack": 900, "contributed": 100, "round_bet": 100, "in_hand": True, "folded": False, "all_in": False},
                {"user_id": 2, "name": "ボブ", "seat": 1, "stack": 950, "contributed": 50, "round_bet": 50, "in_hand": False, "folded": True, "all_in": False},
            ],
            "hand": {"phase": "preflop", "board": [], "showdown": None},
        }
        engine._award_uncontested(state)
        assert state["hand"]["rake"] == 0
        assert state["seats"][0]["stack"] == 1050
        assert all(int(p["contributed"]) == 0 and int(p["round_bet"]) == 0 for p in state["seats"])
        result = state.get("last_result") or {}
        assert result.get("type") == "uncontested"
        assert int((result.get("winners") or [{}])[0].get("amount") or 0) == 150

        delegated = {"value": False}
        engine._jj_v123_base_award_uncontested = lambda _state: delegated.__setitem__("value", True)
        postflop = {**state, "status": "playing", "hand": {"phase": "flop", "board": ["As", "7c", "2d"]}}
        postflop["seats"] = [
            {"user_id": 1, "name": "アリス", "seat": 0, "stack": 900, "contributed": 200, "round_bet": 100, "in_hand": True, "folded": False, "all_in": False},
        ]
        engine._award_uncontested(postflop)
        assert delegated["value"], "postflop settlement must remain delegated to the established rake path"
    finally:
        engine._jj_v123_base_finish_hand = original_finish
        engine._jj_v123_base_award_uncontested = original_award


def test_staged_allin_runout(engine) -> None:
    original_advance = engine._jj_v123_base_advance_round
    original_showdown = engine._showdown
    try:
        def deal_one_stage(state):
            hand = state["hand"]
            n = len(hand["board"])
            if n == 0:
                hand["board"].extend(["As", "7c", "2d"])
                hand["phase"] = "flop"
            elif n == 3:
                hand["board"].append("Jh")
                hand["phase"] = "turn"
            elif n == 4:
                hand["board"].append("9s")
                hand["phase"] = "river"
            else:
                raise AssertionError(f"unexpected staged board length: {n}")

        engine._jj_v123_base_advance_round = deal_one_stage
        engine._showdown = lambda state: state.__setitem__("jj_test_showdown", True)

        state = {
            "status": "playing",
            "big_blind": 100,
            "seats": [
                {"user_id": 1, "name": "アリス", "seat": 0, "stack": 0, "contributed": 15000, "round_bet": 15000, "in_hand": True, "folded": False, "all_in": True},
                {"user_id": 2, "name": "ボブ", "seat": 1, "stack": 0, "contributed": 15000, "round_bet": 15000, "in_hand": True, "folded": False, "all_in": True},
            ],
            "hand": {"id": "allin-1", "phase": "preflop", "board": [], "current_bet": 15000, "min_raise": 100, "raises_in_round": 1, "action_seat": None, "acted": []},
        }

        engine._auto_progress_if_needed(state)
        assert state["hand"]["forced_runout"] is True
        assert state["hand"]["board"] == [], "preflop all-in must not expose the full board immediately"
        assert all(int(p["contributed"]) == 15000 for p in state["seats"]), "cumulative pot contributions must survive runout staging"
        assert all(int(p["round_bet"]) == 0 for p in state["seats"]), "street bets must be cleared during forced runout"

        expected_lengths = [3, 4, 5]
        for length in expected_lengths:
            state["hand"]["runout_due_at_epoch"] = engine.time.time() - 1
            assert engine.advance_forced_runout(state) is True
            assert len(state["hand"]["board"]) == length
            assert not state.get("jj_test_showdown"), "showdown must wait until after the river frame"

        state["hand"]["runout_due_at_epoch"] = engine.time.time() - 1
        assert engine.advance_forced_runout(state) is True
        assert state.get("jj_test_showdown") is True
    finally:
        engine._jj_v123_base_advance_round = original_advance
        engine._showdown = original_showdown


def test_showdown_hold_and_reasons(engine) -> None:
    original_finish = engine._jj_v123_base_finish_hand
    original_legal = engine._jj_v123_base_legal_actions
    try:
        engine._jj_v123_base_finish_hand = lambda state: state.update(
            {"status": "waiting", "next_hand_at_epoch": engine.time.time() + 2.4, "last_result": {"type": "showdown"}}
        )
        now = engine.time.time()
        state = {"hand": {"showdown": {"scores": {"1": [1], "2": [0]}}}}
        engine._finish_hand(state)
        hold = float(state.get("showdown_hold_until_epoch") or 0)
        assert hold >= now + 7.0
        assert float(state.get("next_hand_at_epoch") or 0) >= hold

        engine._jj_v123_base_legal_actions = lambda _state, _uid: {
            "can_act": False,
            "can_check": False,
            "can_call": False,
            "can_raise": False,
            "can_all_in": False,
            "raise_locked_allin": True,
        }
        waiting = {
            "status": "playing",
            "seats": [
                {"user_id": 1, "name": "アリス", "seat": 0, "in_hand": True, "folded": False, "all_in": False},
                {"user_id": 2, "name": "ボブ", "seat": 1, "in_hand": True, "folded": False, "all_in": False},
            ],
            "hand": {"action_seat": 1, "board": [], "phase": "preflop"},
        }
        legal = engine.legal_actions(waiting, 1)
        assert "ボブ" in legal["status_reason"]
        assert "再レイズ権" in legal["disabled_reasons"]["raise"]
    finally:
        engine._jj_v123_base_finish_hand = original_finish
        engine._jj_v123_base_legal_actions = original_legal


def main() -> None:
    assert RUNTIME_VERSION == "1.23.0"
    with tempfile.TemporaryDirectory() as td:
        root = build_runtime(Path(td) / "runtime")
        engine = load_engine(root)
        server = (root / "server.py").read_text(encoding="utf-8")
        engine_src = (root / "poker_engine.py").read_text(encoding="utf-8")
        appjs = (root / "static" / "app.js").read_text(encoding="utf-8")
        css = (root / "static" / "styles.css").read_text(encoding="utf-8")
        index = (root / "static" / "index.html").read_text(encoding="utf-8")
        sw = (root / "static" / "sw.js").read_text(encoding="utf-8")

        assert 'version="1.23.0"' in server or '"version":"1.23.0"' in server
        assert "v1.23.0 staged forced-runout scheduler" in server
        assert "advance_forced_runout" in server
        assert "v1.23.0 mobile poker second-pass engine UX" in engine_src
        assert "v1.23.0 reconstructed-engine compatibility final" in engine_src

        # JS generates suit classes dynamically; validate its suit map and the
        # concrete CSS classes together instead of searching JS for fixed names.
        assert "jjV123SuitName" in appjs
        assert "{s:'spade',h:'heart',d:'diamond',c:'club'}" in appjs
        assert all(f".suit-{name}" in css for name in ("club", "spade", "diamond", "heart"))
        assert "Math.ceil(Number(chips||0)/big)" in appjs
        assert "もう一度タップで確定" in appjs
        assert "送信中… サーバーの確認を待っています" in appjs
        assert "JJ_V123_SOUND_KEY" in appjs
        assert "navigator.vibrate" in appjs
        assert "jj-v123-action-status" in css
        assert "z-index:13" in css
        assert "safe-area-inset-bottom" in css
        assert "?v=51" in index
        assert "jj-arena-live-v51" in sw

        test_no_flop_no_drop(engine)
        test_staged_allin_runout(engine)
        test_showdown_hold_and_reasons(engine)

    print("v1.23 mobile poker UX smoke: ok")


if __name__ == "__main__":
    main()
