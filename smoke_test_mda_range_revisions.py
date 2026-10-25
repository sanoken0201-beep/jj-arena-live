"""Offline regression for mandatory 2–6 dealt-in cohorts and revisable guesses."""
from __future__ import annotations

import sqlite3

from mda_ranges import PrivateRfiEvidence, extract_rfi_evidence, infer_plus_hypotheses, summarize_range
from mda_range_offline_audit import report_rfi_range
from mda_range_revisions import compare_range_reports


def event(n: int, holding: str, opened: bool, size: int = 6, position: str = "BTN"):
    return PrivateRfiEvidence(
        hand_id=f"h{size}:{n}", actor_id=n % 12 + 1,
        position=position, table_size=size, holding=holding, opened=opened,
    )


def snapshot(events, table_size=6, position="BTN"):
    from mda_ranges import infer_plus_hypotheses, summarize_range
    data = summarize_range(events, position=position, table_size=table_size)
    proposals = []
    if data["status"] == "ok":
        for h in infer_plus_hypotheses(events, position=position, table_size=table_size):
            if data["cells"][h.seed]["status"] == "observed":
                proposals.append({
                    "notation": h.notation,
                    "status": h.status,
                    "has_counterevidence": bool(h.contradiction_classes),
                    "candidate_classes": h.candidates,
                })
    return {
        "format_version": "rfi-range-v2", "game": "Ring", "table": "jj-table-a",
        "table_size": table_size, "position": position,
        "sample_policy": "latest_completed_full_hands_per_table_size",
        "requested_hand_limit": 5000, "range": data, "hypotheses": proposals,
    }


def _db():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
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
    return con


def _seed(con, hand_id, table_size, *, partial=0, completed=True, table_id="jj-table-a"):
    positions = {
        2: ("BTN/SB", "BB"),
        3: ("BTN", "SB", "BB"),
        4: ("BTN", "SB", "BB", "CO"),
        5: ("BTN", "SB", "BB", "UTG", "CO"),
        6: ("BTN", "SB", "BB", "UTG", "HJ", "CO"),
    }[table_size]
    con.execute(
        "INSERT INTO jj_hand_history VALUES(?,?,?,?,?,?,?)",
        (hand_id, table_id, 100, "[]", table_size, "2026-10-15" if completed else None, partial),
    )
    con.executemany(
        "INSERT INTO jj_hand_players VALUES(?,?,?,?,?)",
        [(hand_id, i + 1, pos, 100, '["Ks","5d"]') for i, pos in enumerate(positions)],
    )
    con.executemany(
        "INSERT INTO jj_hand_actions VALUES(?,?,?,?,?,?,?,?,?)",
        [(hand_id, i + 1, i + 1, "preflop", "raise" if i == 0 else "fold", 150, 300 if i == 0 else 0, 100, 0)
         for i in range(table_size)],
    )


def run():
    # Two tables of different occupancy cannot contaminate one another, even
    # if position names and cards coincide.
    six = [event(i, "K5o", True) for i in range(120)]
    six.extend(event(1000+i, "K6o", False) for i in range(60))
    three = [event(i, "K5o", False, 3) for i in range(120)]
    pooled = six + three
    six_summary = summarize_range(pooled, position="BTN", table_size=6)
    three_summary = summarize_range(pooled, position="BTN", table_size=3)
    assert six_summary["cells"]["K5o"]["open_frequency"] == 100.0
    assert three_summary["cells"]["K5o"]["open_frequency"] == 0.0
    assert six_summary["opportunities"] == 180
    assert three_summary["opportunities"] == 120
    six_plus = infer_plus_hypotheses(pooled, table_size=6, position="BTN")
    assert six_plus[0].notation == "K5o+"
    assert "K6o" in six_plus[0].contradiction_classes
    assert not infer_plus_hypotheses(three, table_size=3, position="BTN")

    # Cohort excluded if its claimed size disagrees with stored participants.
    with sqlite3.connect(":memory:") as con:
        _seed_db = _db()  # separate connection; only used to manufacture records
        try:
            _seed(_seed_db, "valid2", 2)
            h = dict(_seed_db.execute("SELECT * FROM jj_hand_history").fetchone())
            h["board"] = []
            players = [dict(r) for r in _seed_db.execute("SELECT * FROM jj_hand_players").fetchall()]
            acts = [dict(r) for r in _seed_db.execute("SELECT * FROM jj_hand_actions").fetchall()]
            assert extract_rfi_evidence(h, players, acts)[0].table_size == 2
            assert not extract_rfi_evidence({**h, "player_count": 3}, players, acts)
            assert not extract_rfi_evidence({**h, "player_count": None}, players, acts)
            assert not extract_rfi_evidence(h, players + [players[0]], acts)
        finally:
            _seed_db.close()

    con = _db()
    try:
        _seed(con, "two", 2)
        _seed(con, "three", 3)
        _seed(con, "six", 6)
        _seed(con, "six-b", 6, table_id="jj-table-b")
        _seed(con, "unfinished", 2, completed=False)
        _seed(con, "partial", 6, partial=1)
        two = report_rfi_range(con, table_size=2, position="BTN/SB", limit=10)
        trio = report_rfi_range(con, table_size=3, position="BTN", limit=10)
        six_report = report_rfi_range(con, table_size=6, position="BTN", limit=10)
        assert two["hands_examined"] == trio["hands_examined"] == 1
        assert six_report["hands_examined"] == 2  # Table A and Table B included
        assert two["table_size"] == two["range"]["table_size"] == 2
        assert trio["table_size"] == trio["range"]["table_size"] == 3
        assert six_report["table_size"] == six_report["range"]["table_size"] == 6
        assert all(r["hypotheses"] == [] for r in (two, trio, six_report))
        for size, position in ((2, "BTN"), (2, "SB"), (3, "BTN/SB"), (4, "HJ"), (6, "BB")):
            try:
                report_rfi_range(con, table_size=size, position=position)
            except ValueError:
                pass
            else:
                raise AssertionError(f"invalid table-size/position accepted: {size} {position}")
    finally:
        con.close()

    # The same class that was previously measured at 100% can be *revised*.
    old = snapshot([event(i, "K5o", True) for i in range(120)])
    current = snapshot([event(i, "K5o", i % 3 != 0) for i in range(120)])
    delta = compare_range_reports(old, current)
    assert delta["status"] == "updated"
    k5 = next(d for d in delta["changed_cells"] if d["class"] == "K5o")
    assert k5["change"] == "observed_frequency_revised"
    assert (k5["previous_frequency"], k5["current_frequency"]) == (100.0, 66.67)
    assert compare_range_reports(current, current)["status"] == "unchanged"

    # A previous high-confidence seed is not frozen: it can disappear after
    # a corrected history, deletion, rolling-window exit or evidence cleanup.
    removed = snapshot([event(i, "K6o", True) for i in range(120)])
    revoke = compare_range_reports(old, removed)
    assert any(d["change"] == "observation_withdrawn" and d["class"] == "K5o" for d in revoke["changed_cells"])
    assert any(x["notation"] == "K5o+" and x["change"] == "withdrawn" for x in revoke["hypothesis_revisions"])
    assert any(x["notation"] == "K6o+" and x["change"] == "added" for x in revoke["hypothesis_revisions"])

    # Sample eligibility can itself be lost on revision; we do not preserve
    # a stale inferred range if a corrected source has too few participants.
    tiny = snapshot([event(i, "K5o", True) for i in range(20)])
    shrunk = compare_range_reports(old, tiny)
    assert shrunk["current_cohort_status"] == "insufficient_sample"
    assert any(x["change"] == "withdrawn" for x in shrunk["hypothesis_revisions"])

    # Never compare incompatible cohorts/window semantics.
    for mismatch in (
        {**current, "table_size": 3},
        {**current, "position": "CO"},
        {**current, "requested_hand_limit": 1000},
        {**current, "format_version": "rfi-range-v1"},
    ):
        try:
            compare_range_reports(old, mismatch)
        except ValueError:
            pass
        else:
            raise AssertionError("compared incompatible snapshots")
    print("smoke_test_mda_range_revisions: PASS")


if __name__ == "__main__":
    run()
