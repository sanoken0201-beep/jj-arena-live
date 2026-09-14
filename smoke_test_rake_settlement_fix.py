from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

# Production-composition checks use an isolated SQLite database so the test can
# inspect persisted fixed-table rake policy and online hand/result rows safely.
_TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="jj-rake-audit-"))
os.environ["JJ_DB_PATH"] = str(_TEST_DB_DIR / "jj_arena.db")

import rake_settlement_fix as fix


ROOT = Path(__file__).resolve().parent


def _load_materialized_engine():
    path = ROOT / "materialized_v1244" / "poker_engine.py"
    spec = importlib.util.spec_from_file_location("jj_rake_test_engine", path)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load materialized poker engine")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _player(
    user_id: int,
    name: str,
    seat: int,
    stack: int,
    contributed: int,
    cards: list[str],
    *,
    folded: bool = False,
    in_hand: bool = True,
) -> dict:
    return {
        "user_id": user_id,
        "name": name,
        "seat": seat,
        "stack": stack,
        "in_hand": in_hand,
        "folded": folded,
        "all_in": stack == 0 and in_hand and not folded,
        "round_bet": contributed,
        "contributed": contributed,
        "cards": cards,
        "ready": False,
        "sitting_out": False,
        "sit_out_next": False,
    }


def _state(contributions: list[int], *, big_blind: int = 100) -> dict:
    seats = []
    for i, amount in enumerate(contributions):
        seats.append(
            _player(
                i + 1,
                f"P{i + 1}",
                i,
                0,
                amount,
                [],
            )
        )
    # Deliberately start from the former policy to prove every runtime rake call
    # normalizes stale 10% / 5bb state to 5% / 3bb.
    return {
        "big_blind": big_blind,
        "rake_percent": 0.10,
        "rake_cap": big_blind * 5,
        "max_seats": max(2, len(seats)),
        "button_seat": 0,
        "seats": seats,
        "hand": {"board": ["2c", "3d", "4h"]},
    }


def _expected_rake(pot: int, big_blind: int) -> int:
    return max(0, min((int(pot) * 5) // 100, int(big_blind) * 3, int(pot)))


def _gross_and_rake(engine, state: dict) -> tuple[int, int, list[int]]:
    pots = engine._build_side_pots(state)
    amounts = [int(p["amount"]) for p in pots]
    gross = sum(amounts)
    return gross, int(engine._rake_amount(state, gross)), amounts


def test_formula_exhaustive(engine) -> None:
    # Exact integer reference: floor(pot*5/100), capped at 3bb. This sweep checks
    # rounding, the cap threshold, tiny pots and several blind sizes, and also
    # guards against float-boundary off-by-one errors in the canonical helper.
    for big_blind in (1, 2, 5, 10, 50, 100, 250):
        state = {
            "big_blind": big_blind,
            "rake_percent": 0.10,
            "rake_cap": big_blind * 5,
        }
        upper = max(10_000, big_blind * 100)
        for pot in range(upper + 1):
            got = int(engine._rake_amount(state, pot))
            expected = _expected_rake(pot, big_blind)
            assert got == expected, (big_blind, pot, got, expected)
        assert float(state["rake_percent"]) == 0.05
        assert int(state["rake_cap"]) == big_blind * 3

    bb = 100
    explicit = {
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
    }
    state = {"big_blind": bb, "rake_percent": 0.10, "rake_cap": 500}
    for pot, expected in explicit.items():
        assert int(engine._rake_amount(state, pot)) == expected


def test_uncalled_refund_matrix(engine) -> None:
    cases = [
        ([1000, 500], [500, 500], 500),
        ([1500, 1000, 500], [1000, 1000, 500], 500),
        ([1000, 1000, 500], [1000, 1000, 500], 0),
        ([2000, 1000, 500, 500], [1000, 1000, 500, 500], 1000),
        ([100, 50, 50], [50, 50, 50], 50),
    ]
    for contributions, expected, refund in cases:
        state = _state(contributions)
        before = sum(int(p["stack"]) + int(p["contributed"]) for p in state["seats"])
        assert fix.refund_uncalled_contribution(state) == refund
        assert [int(p["contributed"]) for p in state["seats"]] == expected
        assert fix.refund_uncalled_contribution(state) == 0, "refund must be idempotent"
        after = sum(int(p["stack"]) + int(p["contributed"]) for p in state["seats"])
        assert after == before, "refund must never create or destroy chips"


def test_sidepot_rake_allocation(engine) -> None:
    state = _state([1500, 1000, 500])
    assert fix.refund_uncalled_contribution(state) == 500
    gross, rake, pots = _gross_and_rake(engine, state)
    assert pots == [1500, 1000]
    assert gross == 2500
    assert rake == 125
    alloc = engine._allocate_rake(pots, rake)
    assert alloc == [75, 50]
    assert sum(alloc) == rake

    for pots in (
        [1],
        [100, 100],
        [333, 667],
        [1500, 1000],
        [300, 700, 1100],
        [1, 2, 3, 5, 8, 13],
        [10_000, 1, 1, 1],
    ):
        total = sum(pots)
        rake = _expected_rake(total, 100)
        alloc = engine._allocate_rake(pots, rake)
        assert len(alloc) == len(pots)
        assert sum(alloc) == rake
        assert all(0 <= part <= pot for part, pot in zip(alloc, pots))


def test_real_showdown_split_and_cap(engine) -> None:
    # Two-way tie with an odd net pot: 220 gross - 11 rake = 209. The engine
    # must distribute 105/104 without losing a chip.
    state = engine.blank_table_state(
        table_id="rake-odd-chip",
        name="Rake Odd Chip",
        max_seats=2,
        small_blind=50,
        big_blind=100,
        min_buyin=110,
        max_buyin=110,
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
    assert state["last_result"]["gross_pot"] == 220
    assert state["last_result"]["rake"] == 11
    assert sorted(p["stack"] for p in state["seats"]) == [104, 105]
    assert sum(int(p["stack"]) for p in state["seats"]) + 11 == 220

    cap_state = _state([6000, 6000])
    assert fix.refund_uncalled_contribution(cap_state) == 0
    gross, rake, pots = _gross_and_rake(engine, cap_state)
    assert pots == [12000]
    assert gross == 12000
    assert rake == 300


def test_preflop_no_flop_no_drop_payload(engine) -> None:
    # BB wins after SB folds. The unmatched 50 of the BB is returned first, so
    # the actual contested pot is 100; rake is zero because no flop was dealt.
    state = engine.blank_table_state(
        table_id="rake-preflop",
        name="Rake Preflop",
        max_seats=2,
        small_blind=50,
        big_blind=100,
        min_buyin=1000,
        max_buyin=1000,
    )
    state.update({"status": "playing", "button_seat": 0, "session_active": False})
    state["seats"] = [
        _player(1, "BB", 0, 900, 100, ["As", "Kd"]),
        _player(2, "SB", 1, 950, 50, ["Qc", "Jh"], folded=True),
    ]
    state["hand"] = {
        "id": "rake-preflop-hand",
        "phase": "preflop",
        "board": [],
        "deck": [],
        "action_seat": None,
        "acted": [2],
        "current_bet": 100,
        "min_raise": 100,
        "log": [],
        "starting_stacks": {"1": 1000, "2": 1000},
        "revealed_user_ids": [],
        "result_persisted": False,
    }

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


def _install_on_fake_engine():
    observations: list[tuple[str, int, list[int], float, int]] = []

    def original_showdown(state):
        observations.append(
            (
                "showdown",
                sum(int(p.get("contributed", 0)) for p in state["seats"]),
                [int(p.get("stack", 0)) for p in state["seats"]],
                float(state.get("rake_percent", 0)),
                int(state.get("rake_cap", 0)),
            )
        )

    def original_uncontested(state, *args, **kwargs):
        observations.append(
            (
                "uncontested",
                sum(int(p.get("contributed", 0)) for p in state["seats"]),
                [int(p.get("stack", 0)) for p in state["seats"]],
                float(state.get("rake_percent", 0)),
                int(state.get("rake_cap", 0)),
            )
        )

    fake = SimpleNamespace(_showdown=original_showdown, _award_uncontested=original_uncontested)
    fix._INSTALLED = False
    fix.install(fake)
    return fake, observations


def test_runtime_wrappers() -> None:
    fake, observations = _install_on_fake_engine()

    showdown_state = _state([1000, 500])
    showdown_state["hand"]["board"] = ["2c", "3d", "4h", "5s", "9c"]
    fake._showdown(showdown_state)
    assert observations[-1] == ("showdown", 1000, [500, 0], 0.05, 300)

    postflop_fold = _state([200, 100])
    postflop_fold["seats"][1]["folded"] = True
    postflop_fold["seats"][0]["stack"] = 800
    postflop_fold["seats"][1]["stack"] = 900
    fake._award_uncontested(postflop_fold, postflop_fold["seats"][0])
    assert observations[-1] == ("uncontested", 200, [900, 900], 0.05, 300)

    preflop_fold = _state([100, 50])
    preflop_fold["hand"]["board"] = []
    preflop_fold["seats"][0]["stack"] = 900
    preflop_fold["seats"][1]["stack"] = 950
    fake._award_uncontested(preflop_fold, preflop_fold["seats"][0])
    assert observations[-1] == ("uncontested", 100, [950, 950], 0.05, 300)


def test_production_runtime_policy_and_persistence() -> None:
    # The standalone engine above intentionally used the same integration module.
    # Reset only the install sentinel before importing the actual production
    # composition so its distinct runtime engine receives the wrapper as well.
    fix._INSTALLED = False
    import app

    engine = app.runtime_poker_engine
    db = app.db

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

    index = app._patched_index()
    js = app._patched_app_js()
    assert "rake 5%・3bb cap" in index
    assert "rake 10%・5bb cap" not in index
    assert "RAKE 5% · ${fmt(t.rake_cap_bb)}bb CAP" in js
    assert "rake 5% / 3bb cap" in js
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

    state = engine.blank_table_state(
        table_id="rake-persist-audit",
        name="Rake Persist Audit",
        max_seats=2,
        small_blind=50,
        big_blind=100,
        min_buyin=1000,
        max_buyin=1000,
    )
    state.update({"status": "playing", "button_seat": 0, "session_active": False, "hand_no": 1})
    state["seats"] = [
        _player(uid1, "Rake A", 0, 900, 100, ["As", "Kd"]),
        _player(uid2, "Rake B", 1, 950, 50, ["Qc", "Jh"], folded=True),
    ]
    state["hand"] = {
        "id": "rake-persist-preflop",
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
    engine._award_uncontested(state, state["seats"][0])
    result = state["last_result"]
    assert result["gross_pot"] == 100 and result["rake"] == 0

    with db.connect() as con:
        persisted = db._record_online_hand(con, state)
        assert persisted is not None
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
    by_uid = {int(row["user_id"]): (float(row["result_bb"]), float(row["points"])) for row in rows}
    assert by_uid[uid1] == (0.5, 1.5)
    assert by_uid[uid2] == (-0.5, -1.5)


def main() -> None:
    engine = _load_materialized_engine()
    fix._INSTALLED = False
    fix.install(engine)

    test_formula_exhaustive(engine)
    test_uncalled_refund_matrix(engine)
    test_sidepot_rake_allocation(engine)
    test_real_showdown_split_and_cap(engine)
    test_preflop_no_flop_no_drop_payload(engine)
    test_runtime_wrappers()
    test_production_runtime_policy_and_persistence()
    print("rake settlement comprehensive regression: ok")


if __name__ == "__main__":
    main()
