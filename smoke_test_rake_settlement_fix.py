from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

# This regression is intentionally imported by multiple release paths. Keep its
# isolated database selection ahead of imports that initialize the application.
if "JJ_DB_PATH" not in os.environ and "DATABASE_URL" not in os.environ:
    _TMP = tempfile.TemporaryDirectory(prefix="jj-rake-regression-")
    os.environ["JJ_DB_PATH"] = str(Path(_TMP.name) / "rake.sqlite3")
    os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"

import rake_settlement_fix as fix
from browser_runtime_consolidation import CACHE_QUERY as BROWSER_CACHE_QUERY


def _base_state(engine, uid1: int, uid2: int):
    state = engine.new_table("rake-test", "Rake Test", small_blind=50, big_blind=100, rake_percent=0.05, rake_cap=300)
    engine.add_player(state, uid1, "Rake A", 10000, seat=0)
    engine.add_player(state, uid2, "Rake B", 10000, seat=1)
    state["status"] = "playing"
    state["phase"] = "preflop"
    state["button_seat"] = 0
    state["small_blind_seat"] = 0
    state["big_blind_seat"] = 1
    state["action_seat"] = 0
    state["current_bet"] = 100
    state["min_raise"] = 100
    state["pot"] = 150
    state["hand"] = {
        "id": "rake-test-hand",
        "board": [],
        "deck": [],
        "started_at": "2026-01-01T00:00:00Z",
        "actions": [],
    }
    state["seats"][0].update({"stack": 9950, "round_bet": 50, "total_bet": 50, "folded": False, "all_in": False})
    state["seats"][1].update({"stack": 9900, "round_bet": 100, "total_bet": 100, "folded": False, "all_in": False})
    return state


def _preflop_fold_state(engine, uid1: int, uid2: int):
    state = _base_state(engine, uid1, uid2)
    state["seats"][1]["folded"] = True
    state["action_seat"] = 0
    return state


def _postflop_uncontested_state(engine, uid1: int, uid2: int):
    state = _base_state(engine, uid1, uid2)
    state["phase"] = "flop"
    state["hand"]["board"] = ["Ah", "Kd", "2c"]
    state["pot"] = 1200
    state["current_bet"] = 0
    state["seats"][0].update({"round_bet": 0, "total_bet": 600, "stack": 9400})
    state["seats"][1].update({"round_bet": 0, "total_bet": 600, "stack": 9400, "folded": True})
    return state


def _showdown_state(engine, uid1: int, uid2: int):
    state = _base_state(engine, uid1, uid2)
    state["phase"] = "river"
    state["hand"]["board"] = ["Ah", "Kd", "2c", "7s", "9h"]
    state["pot"] = 1200
    state["current_bet"] = 0
    state["seats"][0].update({"round_bet": 0, "total_bet": 600, "stack": 9400, "hole": ["As", "Ad"]})
    state["seats"][1].update({"round_bet": 0, "total_bet": 600, "stack": 9400, "hole": ["Ks", "Kc"]})
    return state


def test_engine_semantics():
    from materialized_v1244 import poker_engine as engine

    state = engine.new_table("x", "X", small_blind=50, big_blind=100, rake_percent=0.05, rake_cap=300)
    assert state["rake_percent"] == 0.05
    assert state["rake_cap"] == 300

    assert engine.calculate_rake(1000, 0.05, 300) == 50
    assert engine.calculate_rake(10000, 0.05, 300) == 300
    assert engine.calculate_rake(150, 0.05, 300) == 7


def test_no_flop_no_drop_and_postflop_rake():
    from materialized_v1244 import poker_engine as engine

    pre = _preflop_fold_state(engine, 1, 2)
    engine._award_uncontested(pre, pre["seats"][0])
    assert pre["last_result"]["gross_pot"] == 150
    assert pre["last_result"]["rake"] == 0
    assert pre["last_result"]["net_pot"] == 150

    post = _postflop_uncontested_state(engine, 1, 2)
    engine._award_uncontested(post, post["seats"][0])
    assert post["last_result"]["gross_pot"] == 1200
    assert post["last_result"]["rake"] == 60
    assert post["last_result"]["net_pot"] == 1140


def test_showdown_rake():
    from materialized_v1244 import poker_engine as engine

    state = _showdown_state(engine, 1, 2)
    engine._settle_showdown(state)
    assert state["last_result"]["gross_pot"] == 1200
    assert state["last_result"]["rake"] == 60
    assert state["last_result"]["net_pot"] == 1140


def test_cap():
    from materialized_v1244 import poker_engine as engine

    state = _postflop_uncontested_state(engine, 1, 2)
    state["pot"] = 20000
    state["seats"][0]["total_bet"] = 10000
    state["seats"][1]["total_bet"] = 10000
    engine._award_uncontested(state, state["seats"][0])
    assert state["last_result"]["rake"] == 300
    assert state["last_result"]["net_pot"] == 19700


def test_short_stack_and_side_pot_accounting():
    from materialized_v1244 import poker_engine as engine

    state = engine.new_table("side", "Side", small_blind=50, big_blind=100, rake_percent=0.05, rake_cap=300)
    engine.add_player(state, 1, "A", 10000, seat=0)
    engine.add_player(state, 2, "B", 10000, seat=1)
    engine.add_player(state, 3, "C", 10000, seat=2)
    state["status"] = "playing"
    state["phase"] = "river"
    state["pot"] = 5000
    state["hand"] = {"id": "side-hand", "board": ["Ah", "Kd", "2c", "7s", "9h"], "actions": []}
    state["seats"][0].update({"total_bet": 1000, "stack": 9000, "hole": ["As", "Ad"], "folded": False})
    state["seats"][1].update({"total_bet": 2000, "stack": 8000, "hole": ["Ks", "Kc"], "folded": False})
    state["seats"][2].update({"total_bet": 2000, "stack": 8000, "hole": ["Qs", "Qc"], "folded": False})
    before = sum(int(s["stack"]) for s in state["seats"] if s)
    engine._settle_showdown(state)
    result = state["last_result"]
    assert result["gross_pot"] == 5000
    assert result["rake"] == 250
    assert result["net_pot"] == 4750
    after = sum(int(s["stack"]) for s in state["seats"] if s)
    assert after - before == 4750


def test_production_policy_and_persistence():
    # Install onto the actual production composition in an isolated SQLite DB.
    fix._INSTALLED = False
    import app

    engine, db = app.runtime_poker_engine, app.db
    assert float(db.RAKE_PERCENT) == 0.05
    assert int(db.RAKE_CAP_BB) == 3

    with db.connect() as con:
        for table_id, _name in db.FIXED_TABLES:
            row = con.execute("SELECT state_json FROM tables WHERE id=?", (table_id,)).fetchone()
            assert row
            state = json.loads(row["state_json"])
            assert float(state["rake_percent"]) == 0.05
            assert int(state["rake_cap"]) == int(state["big_blind"]) * 3

    config = app._poker_config(user={"id": 1})
    assert config["rake_percent"] == 5
    assert config["rake_cap_bb"] == 3

    # The subtractive redesign may omit rake copy from the lobby, so validate
    # the versioned production JS request and the actual client calculation,
    # rather than requiring a particular explanatory sentence to be visible.
    index = app._patched_index()
    js = app._patched_app_js()
    assert f"/static/app.js?v={app.ASSET_VERSION}&{BROWSER_CACHE_QUERY}" in index
    assert "rake 10%・5bb cap" not in index
    assert "pot*0.05,Number(tableState.rake_cap||300)" in js
    assert "pot*0.10,Number(tableState.rake_cap||500)" not in js

    now = db.utcnow()
    with db.connect() as con:
        uid1 = db.insert_returning_id(
            con,
            "INSERT INTO users(name,email,role,approved,disabled,ranking_name,created_at) VALUES (?,?,?,?,?,?,?)",
            ("Rake A", "rake-a@jj.invalid", "member", 1, 0, "Rake A", now),
        )
        uid2 = db.insert_returning_id(
            con,
            "INSERT INTO users(name,email,role,approved,disabled,ranking_name,created_at) VALUES (?,?,?,?,?,?,?)",
            ("Rake B", "rake-b@jj.invalid", "member", 1, 0, "Rake B", now),
        )

    state = _preflop_fold_state(engine, uid1, uid2)
    state["hand"]["id"] = "rake-persist-preflop"
    engine._award_uncontested(state, state["seats"][0])
    assert state["last_result"]["gross_pot"] == 100
    assert state["last_result"]["rake"] == 0
    app.runtime_server.save_table(state)

    state = _postflop_uncontested_state(engine, uid1, uid2)
    state["id"] = "jj-table-a"
    state["hand"]["id"] = "rake-persist-flop"
    engine._award_uncontested(state, state["seats"][0])
    assert state["last_result"]["rake"] == 60
    app.runtime_server.save_table(state)

    with db.connect() as con:
        rows = con.execute(
            "SELECT hand_id,gross_pot,rake,net_pot FROM online_hand_results WHERE hand_id IN (?,?) ORDER BY hand_id",
            ("rake-persist-flop", "rake-persist-preflop"),
        ).fetchall()
    by_id = {str(row["hand_id"]): row for row in rows}
    assert int(by_id["rake-persist-preflop"]["rake"]) == 0
    assert int(by_id["rake-persist-flop"]["rake"]) == 60
    assert int(by_id["rake-persist-flop"]["gross_pot"]) == 1200
    assert int(by_id["rake-persist-flop"]["net_pot"]) == 1140


def main():
    test_engine_semantics()
    test_no_flop_no_drop_and_postflop_rake()
    test_showdown_rake()
    test_cap()
    test_short_stack_and_side_pot_accounting()
    test_production_policy_and_persistence()
    print("JJ_RAKE_SETTLEMENT_FIX_OK")


if __name__ == "__main__":
    main()
