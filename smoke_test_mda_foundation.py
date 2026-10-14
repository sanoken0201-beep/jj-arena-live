"""Pure, fast MDA foundation regression: no app startup and no DB writes."""
from __future__ import annotations

import sqlite3

from mda_foundation import (
    coverage_report, derive_decisions, derive_opportunities, summarize, wilson_interval,
)


def _hand(hand_id="mda-1", *, partial=0, complete=True, board=None):
    return {
        "hand_id": hand_id, "completed_at": "2026-10-14T00:00:00+00:00" if complete else None,
        "partial_capture": partial, "big_blind": 100, "player_count": 3,
        "board": board if board is not None else [],
    }


def _players():
    return [
        {"user_id": 10, "position": "BTN", "effective_stack_bb": 150, "hole_cards_json": '["As","Ad"]'},
        {"user_id": 20, "position": "SB", "effective_stack_bb": 80, "hole_cards_json": '["Qs","Qd"]'},
        {"user_id": 30, "position": "BB", "effective_stack_bb": 90, "hole_cards_json": '["Kh","Kc"]'},
    ]


def _a(seq, uid, street, action, *, pot=150, amount=0, facing=0):
    return {
        "seq": seq, "user_id": uid, "street": street, "action": action,
        "pot_before": pot, "amount_chips": amount, "facing_chips": facing, "timed_out": 0,
    }


def _events(hand, actions):
    return derive_opportunities(derive_decisions(hand, _players(), actions))


def run():
    three = [
        _a(1, 10, "preflop", "raise", amount=300, facing=100),
        _a(2, 20, "preflop", "fold", facing=250),
        _a(3, 30, "preflop", "raise", amount=900, facing=200),
        _a(4, 10, "preflop", "fold", facing=600),
    ]
    rows = _events(_hand(), three)
    assert [(o.actor_id, o.chosen) for o in rows if o.metric == "rfi"] == [(10, True)]
    assert [(o.actor_id, o.chosen) for o in rows if o.metric == "three_bet"] == [
        (20, False), (30, True),
    ]
    assert [(o.actor_id, o.chosen) for o in rows if o.metric == "fold_to_three_bet"] == [(10, True)]
    assert next(o for o in rows if o.metric == "three_bet" and o.chosen).pot_type == "srp"
    assert len({o.hand_id for o in rows}) == 1
    assert not any(hasattr(o, "hole_cards_json") for o in rows)

    # Limp forfeits RFI, but first post-limp raise remains an opportunity to 3bet for next actor.
    limp = _events(_hand("limp"), [
        _a(1, 10, "preflop", "call", amount=100),
        _a(2, 20, "preflop", "raise", amount=400),
        _a(3, 30, "preflop", "fold"),
    ])
    assert [(o.actor_id, o.chosen) for o in limp if o.metric == "rfi"] == [(10, False)]
    assert [(o.actor_id, o.chosen) for o in limp if o.metric == "three_bet"] == [(30, False)]

    # Squeeze opportunity after an intervening caller cannot disappear.
    squeeze = _events(_hand("squeeze"), [
        _a(1, 10, "preflop", "raise", amount=300),
        _a(2, 20, "preflop", "call", amount=300),
        _a(3, 30, "preflop", "allin_raise", amount=9500, facing=200),
        _a(4, 10, "preflop", "call", amount=9200),
    ])
    assert [(o.actor_id, o.chosen) for o in squeeze if o.metric == "three_bet"] == [
        (20, False), (30, True),
    ]
    assert [(o.actor_id, o.chosen) for o in squeeze if o.metric == "fold_to_three_bet"] == [
        (10, False),
    ]

    # Second raise before opener's reply removes direct fold-to-3bet denominator.
    four = _events(_hand("4bet"), [
        _a(1, 10, "preflop", "raise", amount=300),
        _a(2, 20, "preflop", "raise", amount=900),
        _a(3, 30, "preflop", "raise", amount=2700),
        _a(4, 10, "preflop", "fold"),
    ])
    assert not [o for o in four if o.metric == "fold_to_three_bet"]

    board = ["2s", "8c", "Jh", "Qh", "Ad"]
    flop_actions = [
        _a(1, 10, "preflop", "raise", amount=300),
        _a(2, 20, "preflop", "fold"),
        _a(3, 30, "preflop", "call", amount=200),
        _a(4, 30, "flop", "check", pot=600),
        _a(5, 10, "flop", "raise", pot=600, amount=150),
        _a(6, 30, "flop", "fold", pot=750, facing=150),
    ]
    decisions = derive_decisions(_hand("cbet", board=board), _players(), flop_actions)
    cbet_decision = decisions[4]
    assert cbet_decision.bet_pct_pot == 25.0
    assert cbet_decision.pot_type == "srp"
    assert cbet_decision.board_texture == "unpaired:1max"
    assert cbet_decision.stack_bb_at_start == 150
    cbet = derive_opportunities(decisions)
    assert [(o.actor_id, o.chosen) for o in cbet if o.metric == "flop_cbet"] == [
        (10, True),
    ]
    assert [(o.actor_id, o.chosen) for o in cbet if o.metric == "fold_to_flop_cbet"] == [
        (30, True),
    ]

    # Raise versus donk is not a continuation bet; the raise has no first-bet %.
    donk = flop_actions[:3] + [
        _a(4, 30, "flop", "raise", pot=600, amount=150),
        _a(5, 10, "flop", "raise", pot=750, amount=450, facing=150),
    ]
    donk_decisions = derive_decisions(_hand("donk", board=board), _players(), donk)
    assert donk_decisions[-1].bet_pct_pot is None
    assert not [o for o in derive_opportunities(donk_decisions) if o.metric == "flop_cbet"]

    # Preflop-only, partial, active, unknown action, duplicate sequence all fail safe.
    assert not derive_decisions(_hand("partial", partial=1), _players(), three)
    assert not derive_decisions(_hand("live", complete=False), _players(), three)
    assert not derive_decisions(_hand("invalid"), _players(), [_a(1, 10, "preflop", "dance")])
    assert not derive_decisions(_hand("dup"), _players(), [three[0], dict(three[0])])

    # Small cohort is suppressed without reporting an exact n or identifiable metadata.
    hidden = summarize(rows, "rfi")
    assert hidden == {"metric": "rfi", "position": None, "status": "insufficient_sample"}
    visible = summarize(rows, "rfi", min_opportunities=1, min_players=1)
    assert visible["chosen"] == visible["opportunities"] == visible["unique_players"] == 1
    assert "actor_id" not in str(visible) and "hand_id" not in str(visible)
    assert wilson_interval(50, 100) == (40.38, 59.62)
    try:
        summarize(rows, "nonexistent", min_opportunities=1, min_players=1)
    except ValueError:
        pass
    else:
        raise AssertionError("unknown metric unexpectedly accepted")

    # Read-only coverage audit, including exclusion of partial/in-progress hands.
    con = sqlite3.connect(":memory:")
    try:
        con.execute("CREATE TABLE jj_hand_history(hand_id TEXT PRIMARY KEY,completed_at TEXT,partial_capture INTEGER)")
        con.execute("CREATE TABLE jj_hand_players(hand_id TEXT,user_id INTEGER)")
        con.execute("CREATE TABLE jj_hand_actions(hand_id TEXT,seq INTEGER)")
        con.executemany("INSERT INTO jj_hand_history VALUES(?,?,?)", [
            ("a", "2026-10-14", 0), ("b", "2026-10-14", 1), ("c", None, 0), ("d", "2026-10-15", 0),
        ])
        con.executemany("INSERT INTO jj_hand_players VALUES(?,?)", [("a", 10), ("a", 20), ("b", 30)])
        con.execute("INSERT INTO jj_hand_actions VALUES('a',1)")
        audit = coverage_report(con)
        assert audit == {
            "completed_full_hands": 2, "completed_partial_hands": 1, "incomplete_hands": 1,
            "full_hand_player_rows": 2, "full_hand_action_rows": 1,
            "full_hands_missing_actions": 1, "full_hand_distinct_players": 2,
        }, audit
    finally:
        con.close()
    print("smoke_test_mda_foundation: PASS")


if __name__ == "__main__":
    run()
