from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path

from browser_runtime_consolidation import CACHE_QUERY

_TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="jj-rake-audit-"))
os.environ["JJ_DB_PATH"] = str(_TEST_DB_DIR / "jj_arena.db")

import rake_settlement_fix as fix

ROOT = Path(__file__).resolve().parent


def _load_engine():
    path = ROOT / "materialized_v1244" / "poker_engine.py"
    spec = importlib.util.spec_from_file_location("jj_rake_test_engine", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _player(uid, name, seat, stack, contributed, cards, *, folded=False):
    return {
        "user_id": uid,
        "name": name,
        "seat": seat,
        "stack": stack,
        "in_hand": True,
        "folded": folded,
        "all_in": stack == 0 and not folded,
        "round_bet": contributed,
        "contributed": contributed,
        "cards": cards,
        "ready": False,
        "sitting_out": False,
        "sit_out_next": False,
    }


def _state(contributions, *, bb=100):
    return {
        "big_blind": bb,
        "rake_percent": 0.10,
        "rake_cap": bb * 5,
        "max_seats": max(2, len(contributions)),
        "button_seat": 0,
        "seats": [
            _player(i + 1, f"P{i + 1}", i, 0, amount, [])
            for i, amount in enumerate(contributions)
        ],
        "hand": {"board": ["2c", "3d", "4h"]},
    }


def _expected_rake(pot, bb):
    return max(0, min((int(pot) * 5) // 100, int(bb) * 3, int(pot)))


def test_formula_exhaustive(engine):
    # Compare the runtime calculation to an integer reference across multiple
    # blind sizes. This catches rounding and 3bb-cap boundary errors.
    for bb in (1, 2, 5, 10, 50, 100, 250):
        state = {"big_blind": bb, "rake_percent": 0.10, "rake_cap": bb * 5}
        for pot in range(max(10_000, bb * 100) + 1):
            assert int(engine._rake_amount(state, pot)) == _expected_rake(pot, bb), (bb, pot)
        assert float(state["rake_percent"]) == 0.05
        assert int(state["rake_cap"]) == bb * 3

    state = {"big_blind": 100, "rake_percent": 0.10, "rake_cap": 500}
    for pot, expected in {
        0: 0,
        1: 0,
        19: 0,
        20: 1,
        99: 4,
        100: 5,
        5_999: 299,
        6_000: 300,
        6_001: 300,
        12_000: 300,
    }.items():
        assert int(engine._rake_amount(state, pot)) == expected


def test_uncalled_refunds():
    for source, expected, refund in (
        ([1000, 500], [500, 500], 500),
        ([1500, 1000, 500], [1000, 1000, 500], 500),
        ([1000, 1000, 500], [1000, 1000, 500], 0),
        ([2000, 1000, 500, 500], [1000, 1000, 500, 500], 1000),
        ([100, 50, 50], [50, 50, 50], 50),
    ):
        state = _state(source)
        before = sum(int(p["stack"]) + int(p["contributed"]) for p in state["seats"])
        assert fix.refund_uncalled_contribution(state) == refund
        assert [int(p["contributed"]) for p in state["seats"]] == expected
        assert fix.refund_uncalled_contribution(state) == 0
        after = sum(int(p["stack"]) + int(p["contributed"]) for p in state["seats"])
        assert after == before


def test_sidepot_allocation(engine):
    state = _state([1500, 1000, 500])
    assert fix.refund_uncalled_contribution(state) == 500
    pots = engine._build_side_pots(state)
    amounts = [int(p["amount"]) for p in pots]
    assert amounts == [1500, 1000]
    gross = sum(amounts)
    rake = int(engine._rake_amount(state, gross))
    assert gross == 2500 and rake == 125
    assert engine._allocate_rake(amounts, rake) == [75, 50]

    # Rake allocation must conserve the hand-level rake for arbitrary side-pot
    # shapes and may never exceed a pot's own amount.
    for amounts in (
        [1], [100, 100], [333, 667], [1500, 1000],
        [300, 700, 1100], [1, 2, 3, 5, 8, 13], [10_000, 1, 1, 1],
    ):
        total_rake = _expected_rake(sum(amounts), 100)
        alloc = engine._allocate_rake(amounts, total_rake)
        assert len(alloc) == len(amounts)
        assert sum(alloc) == total_rake
        assert all(0 <= part <= pot for part, pot in zip(alloc, amounts))


def test_showdown_chop_odd_chip_and_cap(engine):
    # 220 gross - 11 rake = 209. A board-only royal flush ties both players,
    # so exactly one odd chip must be allocated and no chip may disappear.
    state = engine.blank_table_state(
        table_id="rake-odd-chip", name="Rake Odd Chip", max_seats=2,
        small_blind=50, big_blind=100, min_buyin=110, max_buyin=110,
    )
    state.update({"status": "playing", "button_seat": 0, "rake_percent": 0.10, "rake_cap": 500})
    state["seats"] = [
        _player(1, "A", 0, 0, 110, ["2c", "3d"]),
        _player(2, "B", 1, 0, 110, ["4c", "5d"]),
    ]
    state["hand"] = {
        "id": "rake-odd-chip-hand",
        "phase": "river",
        "board": ["Ah", "Kh", "Qh", "Jh", "Th"],
        "deck": [],
        "action_seat": None,
        "acted": [],
        "current_bet": 0,
        "min_raise": 100,
        "log": [],
        "starting_stacks": {"1": 110, "2": 110},
        "revealed_user_ids": [],
    }
    engine._showdown(state)
    result = state["last_result"]
    assert result["gross_pot"] == 220
    assert result["rake"] == 11
    assert sorted(p["stack"] for p in state["seats"]) == [104, 105]
    assert sum(int(p["stack"]) for p in state["seats"]) + 11 == 220

    cap_state = _state([6000, 6000])
    pots = engine._build_side_pots(cap_state)
    gross = sum(int(p["amount"]) for p in pots)
    assert gross == 12_000
    assert int(engine._rake_amount(cap_state, gross)) == 300


def _preflop_fold_state(engine, uid1=1, uid2=2):
    state = engine.blank_table_state(
        table_id="rake-preflop", name="Rake Preflop", max_seats=2,
        small_blind=50, big_blind=100, min_buyin=1000, max_buyin=1000,
    )
    state.update({"status": "playing", "button_seat": 0, "session_active": False, "hand_no": 1})
    state["seats"] = [
        _player(uid1, "BB", 0, 900, 100, ["As", "Kd"]),
        _player(uid2, "SB", 1, 950, 50, ["Qc", "Jh"], folded=True),
    ]
    state["hand"] = {
        "id": "rake-preflop-hand",
        "phase": "preflop",
        "board": [],
        "deck": [],
        "action_seat": None,
        "acted": [uid2],
        "current_bet": 100,
        "min_raise": 100,
        "log": [],
        "starting_stacks": {str(uid1): 1000, str(uid2): 1000},
        "revealed_user_ids": [],
        "result_persisted": False,
    }
    return state


def test_no_flop_no_drop(engine):
    # SB folds to the BB. The BB's unmatched 50 is returned first; only 100 is
    # contested, and No Flop No Drop means rake stays exactly zero.
    state = _preflop_fold_state(engine)
    engine._award_uncontested(state, state["seats"][0])
    result = state["last_result"]
    assert result["gross_pot"] == 100
    assert result["rake"] == 0
    assert result["winners"][0]["amount"] == 100
    assert [p["stack"] for p in state["seats"]] == [1050, 950]
    assert sum(int(p["stack"]) for p in state["seats"]) == 2000
    net = {int(row["user_id"]): int(row["amount"]) for row in result["net_results"]}
    assert net == {1: 50, 2: -50}
    assert state["hand"]["phase"] == "complete"


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
    assert f"/static/app.js?v={app.ASSET_VERSION}&{CACHE_QUERY}" in index
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

    with db.connect() as con:
        assert db._record_online_hand(con, state) is not None
        hand_row = con.execute(
            "SELECT gross_pot_bb,rake_bb FROM online_hands WHERE hand_id=?",
            ("rake-persist-preflop",),
        ).fetchone()
        rows = con.execute(
            "SELECT user_id,result_bb,points FROM online_hand_results WHERE hand_id=? ORDER BY user_id",
            ("rake-persist-preflop",),
        ).fetchall()

    assert float(hand_row["gross_pot_bb"]) == 1.0
    assert float(hand_row["rake_bb"]) == 0.0
    by_uid = {
        int(row["user_id"]): (float(row["result_bb"]), float(row["points"]))
        for row in rows
    }
    assert by_uid[uid1] == (0.5, 1.5)
    assert by_uid[uid2] == (-0.5, -1.5)


def main():
    engine = _load_engine()
    fix._INSTALLED = False
    fix.install(engine)
    test_formula_exhaustive(engine)
    test_uncalled_refunds()
    test_sidepot_allocation(engine)
    test_showdown_chop_odd_chip_and_cap(engine)
    test_no_flop_no_drop(engine)
    test_production_policy_and_persistence()
    print("rake settlement comprehensive regression: ok")


if __name__ == "__main__":
    main()
