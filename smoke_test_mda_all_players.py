"""All participant roles, occupancy, streaming, privacy and recomputation regression."""
from __future__ import annotations

import json
import sqlite3

from mda_all_players_offline_audit import audit_all_players


def _db():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(
        """CREATE TABLE jj_hand_history(
          hand_id TEXT PRIMARY KEY, table_id TEXT, player_count INTEGER,
          big_blind INTEGER, board_json TEXT, completed_at TEXT, partial_capture INTEGER);
        CREATE TABLE jj_hand_players(
          hand_id TEXT, user_id INTEGER, position TEXT,
          effective_stack_bb REAL, hole_cards_json TEXT);
        CREATE TABLE jj_hand_actions(
          hand_id TEXT, seq INTEGER, user_id INTEGER, street TEXT, action TEXT,
          pot_before INTEGER, amount_chips INTEGER, facing_chips INTEGER, timed_out INTEGER);
        CREATE TABLE users(id INTEGER PRIMARY KEY, role TEXT);"""
    )
    con.executemany(
        "INSERT INTO users VALUES(?,?)",
        [(i, "admin" if i == 1 else "member") for i in range(1, 13)],
    )
    return con


def _seed(con, index, size, *, opened=True, status="ok", holding=None, table_id="jj-table-a"):
    seats = {
        2: ("BTN/SB", "BB"),
        3: ("BTN", "SB", "BB"),
        6: ("BTN", "SB", "BB", "UTG", "HJ", "CO"),
    }[size]
    identifier = f"ring:{size}:{index:05d}:{status}"
    con.execute(
        "INSERT INTO jj_hand_history VALUES(?,?,?,?,?,?,?)",
        (identifier, table_id, size, 100, "[]",
         None if status == "live" else "2026-10-15T10:00:00Z",
         int(status == "partial")),
    )
    # Every one of 12 accounts, including the administrator account #1,
    # rotates through each position with equal eligibility.
    players = {
        pos: (index + j) % 12 + 1
        for j, pos in enumerate(seats)
    }
    cards = holding or (["Kh", "5d"] if size == 6 else ["Ah", "2c"])
    con.executemany(
        "INSERT INTO jj_hand_players VALUES(?,?,?,?,?)",
        [(identifier, players[pos], pos, 120.0, json.dumps(cards)) for pos in seats],
    )
    order = {
        2: ("BTN/SB", "BB"),
        3: ("BTN", "SB", "BB"),
        6: ("UTG", "HJ", "CO", "BTN", "SB", "BB"),
    }[size]
    target = "BTN/SB" if size == 2 else "BTN"
    actions = []
    for seq, pos in enumerate(order, 1):
        kind = "raise" if pos == target and opened else "fold"
        actions.append(
            (identifier, seq, players[pos], "preflop", kind, 150,
             300 if kind == "raise" else 0, 100, 0)
        )
    con.executemany("INSERT INTO jj_hand_actions VALUES(?,?,?,?,?,?,?,?,?)", actions)


def run():
    con = _db()
    try:
        for i in range(120):
            _seed(con, i, 6)
            _seed(con, i, 2)
        _seed(con, 900, 3, status="partial")
        _seed(con, 901, 3, status="live")
        _seed(con, 902, 3, status="ok")
        for i in range(60):
            # Table B is a normal public ring table, NOT a separate population.
            # Its real hands must enter the same 6-handed BTN denominator.
            _seed(con, i + 3000, 6, opened=False, table_id="jj-table-b")

        # Run multiple keyset pages. Only full, completed hands from all users
        # count; no user role column is referenced by analysis queries.
        report = audit_all_players(con, batch_size=17)
        assert report["population"].startswith("all recorded")
        assert report["user_role_filter"] == "none"
        assert report["coverage"]["complete_scan"] is True
        assert report["coverage"]["hands_examined"] == 301, report["coverage"]
        assert report["coverage"]["hands_accepted"] == 301
        assert report["coverage"]["unique_players"] == 12
        assert report["coverage"]["participant_hand_rows_accepted"] == 1323
        assert report["coverage"]["action_rows_accepted"] == 1323
        sizes = report["cohorts_by_players_dealt_in"]
        assert set(sizes) == {"2", "3", "6"}
        assert sizes["2"]["completed_hands_used"] == 120
        assert sizes["6"]["completed_hands_used"] == 180
        six_btn = sizes["6"]["positions"]["BTN"]
        two_btn = sizes["2"]["positions"]["BTN/SB"]
        assert six_btn["contributing_players"] == 12
        assert two_btn["contributing_players"] == 12
        assert six_btn["metrics"]["rfi"]["opportunities"] == 180
        assert six_btn["metrics"]["rfi"]["percentage"] == 66.67
        assert two_btn["metrics"]["rfi"]["percentage"] == 100.0
        assert six_btn["rfi_range"]["cells"]["K5o"]["open_frequency"] == 66.67
        assert six_btn["rfi_range"]["cells"]["A2o"]["status"] == "unknown"
        assert two_btn["rfi_range"]["cells"]["A2o"]["open_frequency"] == 100
        assert two_btn["rfi_range"]["cells"]["K5o"]["status"] == "unknown"
        assert "K5o+" in [x["notation"] for x in six_btn["rfi_range"]["hypotheses"]]
        assert "A2o+" in [x["notation"] for x in two_btn["rfi_range"]["hypotheses"]]
        assert sizes["6"]["positions"]["BB"]["rfi_range"]["status"] == "not_applicable"
        assert sizes["3"]["positions"]["BTN"]["status"] == "insufficient_sample"
        assert report["coverage"]["hands_rejected"] == 0
        payload = json.dumps(report)
        for private in ('"user_id"', '"actor_id"', '"hand_id"', '"Kh"', '"5d"', "ring:6:"):
            assert private not in payload, private

        # Source corrections and new hands must change observed rates, even if
        # the earlier claim looked 'seed replicated'; no cached determination.
        for i in range(120, 240):
            _seed(con, i, 6, opened=False)
        revised = audit_all_players(con, batch_size=19)
        rate = revised["cohorts_by_players_dealt_in"]["6"]["positions"]["BTN"]["rfi_range"]["cells"]["K5o"]
        assert rate["opportunities"] == 300 and rate["opens"] == 120
        assert rate["open_frequency"] == 40.0

        # A bounded diagnostic run cannot falsely claim to have scanned all.
        small = audit_all_players(con, max_hands=50, batch_size=13)
        assert small["coverage"]["complete_scan"] is False
        assert small["coverage"]["scope"] == "bounded_partial_scan"
        assert small["coverage"]["hands_examined"] == 50
    finally:
        con.close()
    print("smoke_test_mda_all_players: PASS")


if __name__ == "__main__":
    run()
