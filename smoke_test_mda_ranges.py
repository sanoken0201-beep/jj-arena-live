"""Deterministic pure tests for offline 169-hand-class range estimation."""
from __future__ import annotations

from mda_ranges import (
    PrivateRfiEvidence, HAND_CLASSES, all_classes, combo_count,
    expand_plus, extract_rfi_evidence, hand_class, infer_plus_hypotheses,
    summarize_range,
)


def hand():
    return {
        "hand_id": "completed-1", "completed_at": "2026-10-15T00:00:00+00:00",
        "partial_capture": 0, "big_blind": 100, "player_count": 3, "board": [],
    }


def actors():
    return [
        {"user_id": 10, "position": "BTN", "effective_stack_bb": 150, "hole_cards_json": '["Kh","5d"]'},
        {"user_id": 20, "position": "SB", "effective_stack_bb": 150, "hole_cards_json": '["Ac","Ah"]'},
        {"user_id": 30, "position": "BB", "effective_stack_bb": 150, "hole_cards_json": '["7h","3h"]'},
    ]


def action(seq, actor, kind, amount=0):
    return {
        "seq": seq, "user_id": actor, "street": "preflop", "action": kind,
        "pot_before": 150, "facing_chips": 100, "amount_chips": amount,
    }


def ev(uid, holding, opened, *, hand_id="h", position="BTN"):
    return PrivateRfiEvidence(
        hand_id=hand_id, actor_id=uid, position=position, holding=holding, opened=opened
    )


def run():
    classes = all_classes()
    assert len(classes) == len(HAND_CLASSES) == 169
    assert len(set(classes)) == 169
    assert sum(combo_count(c) for c in classes) == 1326
    assert combo_count("AA") == 6
    assert combo_count("K5s") == 4
    assert combo_count("K5o") == 12
    assert hand_class(["Kh", "5d"]) == "K5o"
    assert hand_class(["5d", "Kh"]) == "K5o"
    assert hand_class(["Kh", "5h"]) == "K5s"
    assert hand_class(["Ah", "As"]) == "AA"
    assert hand_class(["10h", "Jh"]) == "JTs"
    assert hand_class(["As", "As"]) is None
    assert hand_class(["Ad", "Xd"]) is None
    assert hand_class(["Ad"]) is None
    assert hand_class(["Ad", "Kd", "Qd"]) is None
    assert expand_plus("K5o+") == (
        "K5o", "K6o", "K7o", "K8o", "K9o", "KTo", "KJo", "KQo",
    )
    assert expand_plus("K5s+") == (
        "K5s", "K6s", "K7s", "K8s", "K9s", "KTs", "KJs", "KQs",
    )
    assert expand_plus("TT+") == ("TT", "JJ", "QQ", "KK", "AA")
    for bad in ("AKx+", "K5o", "K5z+", "55s+", "KKo+"):
        try:
            expand_plus(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Accepted bad token: {bad}")

    # A BTN K5o open is an actual observed action. Stronger kickers are *not*
    # automatically marked as observed hands.
    events = extract_rfi_evidence(
        hand(), actors(),
        [action(1, 10, "raise", 300), action(2, 20, "fold"), action(3, 30, "fold")],
    )
    assert [(e.position, e.holding, e.opened) for e in events] == [
        ("BTN", "K5o", True),
    ]  # SB folded facing the BTN raise; SB was NOT in an RFI opportunity.
    guesses = infer_plus_hypotheses(events, position="BTN")
    k5 = next(h for h in guesses if h.notation == "K5o+")
    assert k5.seed == "K5o"
    assert k5.status == "tentative"
    assert k5.candidates == expand_plus("K5o+")
    assert k5.seed_open_count == 1
    assert not k5.contradiction_classes
    assert summarize_range(events, position="BTN") == {
        "status": "insufficient_sample", "position": "BTN",
    }
    assert infer_plus_hypotheses(events, position="CO") == ()

    # Limp from BTN means there is *no* observed BTN raise, so no K5o+.
    limped = extract_rfi_evidence(
        hand(), actors(),
        [action(1, 10, "call", 100), action(2, 20, "raise", 300), action(3, 30, "fold")],
    )
    assert limped[0].opened is False
    assert not infer_plus_hypotheses(limped, position="BTN")
    assert not extract_rfi_evidence(
        {**hand(), "partial_capture": 1}, actors(), [action(1, 10, "raise", 300)]
    )
    assert not extract_rfi_evidence(
        {**hand(), "completed_at": None}, actors(), [action(1, 10, "raise", 300)]
    )
    hidden_players = [{**p, "hole_cards_json": "[]"} for p in actors()]
    assert not extract_rfi_evidence(
        hand(), hidden_players, [action(1, 10, "raise", 300)]
    )

    # Explicit real folds on stronger kickers can challenge monotone guesses.
    noisy = [ev(10, "K5o", True)]
    noisy.extend(ev(i % 8, "K6o", False, hand_id=f"f{i}") for i in range(8))
    assert infer_plus_hypotheses(noisy, position="BTN")[0].contradiction_classes == ("K6o",)

    # Different positions and suitedness are intentionally not pooled.
    mixed = [ev(10, "K5o", True), ev(11, "K4s", True, position="CO")]
    assert len(infer_plus_hypotheses(mixed, position="BTN")) == 1
    assert infer_plus_hypotheses(mixed, position="CO")[0].notation == "K4s+"

    # A5s wheel effects are non-monotone: do not auto-create A5s+.
    assert not infer_plus_hypotheses([ev(10, "A5s", True)], position="BTN")

    # Publishing a class requires *both* whole-cohort and per-cell thresholds.
    records = [
        ev(i % 12, "K5o", bool(i % 3), hand_id=f"h{i}")
        for i in range(120)
    ]
    # A separate sparse cell remains UNKNOWN, not a guessed 100% open.
    records.extend(ev(12, "AA", True, hand_id=f"extra{i}") for i in range(2))
    summary = summarize_range(records, position="BTN")
    assert summary["status"] == "ok"
    assert len(summary["cells"]) == 169
    assert summary["cells"]["K5o"]["status"] == "observed"
    assert summary["cells"]["K5o"]["opportunities"] == 120
    assert summary["cells"]["K5o"]["opens"] == 80
    assert summary["cells"]["K5o"]["open_frequency"] == 66.67
    assert summary["cells"]["K6o"] == {"status": "unknown"}
    assert summary["cells"]["AA"] == {"status": "unknown"}
    assert "Kh" not in str(summary) and "actor_id" not in str(summary)
    assert "hand_id" not in str(summary)
    assert "K5o+" not in str(summary)   # hypotheses kept separate
    assert "K5s" in summary["cells"]
    assert "AKo" in summary["cells"]

    # Even 100 opportunities can be private if one player dominates.
    one_person = [ev(10, "K5o", True, hand_id=f"p{i}") for i in range(120)]
    assert summarize_range(one_person, position="BTN")["status"] == "insufficient_sample"

    # End-to-end audit: sensitive hole cards exist only in this isolated test DB;
    # public JSON must suppress the tiny pool and never expose them.
    import json
    import sqlite3
    from mda_range_offline_audit import report_rfi_range
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    try:
        con.execute(
            "CREATE TABLE jj_hand_history("
            "hand_id TEXT,table_id TEXT,big_blind INTEGER,board_json TEXT,"
            "player_count INTEGER,completed_at TEXT,partial_capture INTEGER)"
        )
        con.execute(
            "CREATE TABLE jj_hand_players("
            "hand_id TEXT,user_id INTEGER,position TEXT,"
            "effective_stack_bb REAL,hole_cards_json TEXT)"
        )
        con.execute(
            "CREATE TABLE jj_hand_actions("
            "hand_id TEXT,seq INTEGER,user_id INTEGER,street TEXT,action TEXT,"
            "pot_before INTEGER,amount_chips INTEGER,facing_chips INTEGER,timed_out INTEGER)"
        )
        con.execute(
            "INSERT INTO jj_hand_history VALUES(?,?,?,?,?,?,?)",
            ("secret-hand-A", "jj-table-a", 100, "[]", 3, "2026-10-15", 0),
        )
        con.executemany("INSERT INTO jj_hand_players VALUES(?,?,?,?,?)", [
            ("secret-hand-A", 10, "BTN", 150.0, '["Kh","5d"]'),
            ("secret-hand-A", 20, "SB", 150.0, '["As","Ac"]'),
            ("secret-hand-A", 30, "BB", 150.0, '["2c","3c"]'),
        ])
        con.executemany("INSERT INTO jj_hand_actions VALUES(?,?,?,?,?,?,?,?,?)", [
            ("secret-hand-A", 1, 10, "preflop", "raise", 150, 300, 100, 0),
            ("secret-hand-A", 2, 20, "preflop", "fold", 450, 0, 250, 0),
            ("secret-hand-A", 3, 30, "preflop", "fold", 450, 0, 200, 0),
        ])
        output = report_rfi_range(con, position="BTN", limit=5)
        assert output["range"]["status"] == "insufficient_sample"
        assert output["hypotheses"] == []
        serial = json.dumps(output)
        for secret in ("secret-hand-A", "Kh", "5d", "As", "Ac", '"actor_id"', '"user_id"', '"K5o"'):
            assert secret not in serial, secret
        # Incomplete and partially captured hands do not change range counts.
        con.execute("INSERT INTO jj_hand_history VALUES (?,?,?,?,?,?,?)",
                    ("unfinished", "jj-table-a", 100, "[]", 2, None, 0))
        con.execute("INSERT INTO jj_hand_history VALUES (?,?,?,?,?,?,?)",
                    ("partial", "jj-table-a", 100, "[]", 2, "2026-10-15", 1))
        assert report_rfi_range(con, limit=5)["hands_examined"] == 1
    finally:
        con.close()

    print("smoke_test_mda_ranges: PASS")


if __name__ == "__main__":
    run()
