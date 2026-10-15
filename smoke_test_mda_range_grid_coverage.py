"""End-to-end 13x13 MDA disclosure contract and SQL coverage gate tests."""
from __future__ import annotations

from collections import defaultdict
import json
import sqlite3

from mda_coverage_gate import audit_coverage
from mda_offline_audit import QueryConnection
from mda_range_grid import range_matrix
from mda_ranges import HAND_CLASSES, POSITIONS_BY_SIZE, expand_plus


def _cells():
    return {cls: {"status": "unknown"} for cls in HAND_CLASSES}


def _observed(freq=25.0, n=20):
    return {
        "status": "observed", "opportunities": n,
        "opens": round(n * freq / 100), "open_frequency": freq,
        "smoothed_frequency": (freq + 10) / 2,
        "wilson_95_percent": [1.0, 80.0],
    }


def _report(game="Ring", size=6, position="BTN", fmt="mda-all-players-v1"):
    cells = _cells()
    cells["K5o"] = _observed()
    cells["K9o"] = _observed(freq=100)
    inner = {
        "status": "ok", "cells": cells,
        "hypotheses": [{
            "notation": "K5o+", "status": "seed_replicated",
            "candidate_classes": list(expand_plus("K5o+")),
            "has_counterevidence": False,
        }],
    }
    report = {
        "format_version": fmt, "game": game,
        "cohorts_by_players_dealt_in": {
            str(size): {"positions": {position: {"rfi_range": inner}}}
        },
    }
    if fmt == "rfi-range-v2":
        report = {
            "format_version": fmt, "game": game,
            "table_size": size, "position": position,
            "range": {**inner, "table_size": size, "position": position},
            "hypotheses": inner["hypotheses"],
        }
    return report


def _cell(matrix, label):
    return next(c for row in matrix["grid"] for c in row if c["class"] == label)


def _db():
    raw = sqlite3.connect(":memory:")
    raw.row_factory = sqlite3.Row
    con = QueryConnection(raw, postgres=False)
    raw.executescript(
        """CREATE TABLE jj_hand_history(
            hand_id TEXT PRIMARY KEY,table_id TEXT,player_count INTEGER,
            completed_at TEXT,partial_capture INTEGER);
        CREATE TABLE jj_hand_players(
            hand_id TEXT,user_id INTEGER,hole_cards_json TEXT);
        CREATE TABLE jj_hand_actions(
            hand_id TEXT,seq INTEGER,user_id INTEGER);
        CREATE TABLE sitngo_hands(
            hand_id TEXT,event_id TEXT,state_json TEXT,created_at TEXT);
        CREATE TABLE users(id INTEGER PRIMARY KEY,role TEXT);"""
    )
    raw.executemany(
        "INSERT INTO users VALUES (?,?)",
        [(i, "admin" if i == 1 else "member") for i in range(1, 13)],
    )
    for size, n in ((2, 15), (3, 3), (6, 120)):
        for i in range(n):
            hand_id = f"h:{size}:{i}"
            raw.execute(
                "INSERT INTO jj_hand_history VALUES (?,?,?,?,?)",
                (hand_id, "jj-table-a", size, "2026-10-15", 0),
            )
            for p in range(size):
                raw.execute(
                    "INSERT INTO jj_hand_players VALUES (?,?,?)",
                    (hand_id, (i+p) % 12 + 1, "[]" if i == 0 else '["As","Ah"]'),
                )
                raw.execute(
                    "INSERT INTO jj_hand_actions VALUES (?,?,?)",
                    (hand_id, p + 1, (i+p) % 12 + 1),
                )
    # Completed but partially captured: excluded from usable counts.
    raw.execute(
        "INSERT INTO jj_hand_history VALUES (?,?,?,?,?)",
        ("partial", "jj-table-a", 6, "2026-10-15", 1),
    )
    raw.execute(
        "INSERT INTO jj_hand_history VALUES (?,?,?,?,?)",
        ("active", "jj-table-a", 6, None, 0),
    )
    raw.execute(
        "INSERT INTO jj_hand_history VALUES (?,?,?,?,?)",
        ("another-table", "jj-table-b", 6, "2026-10-15", 0),
    )
    raw.execute(
        "INSERT INTO sitngo_hands VALUES(?,?,?,?)",
        ("secret-tourney", "event-1", '{"seats":[{"cards":["Kh","5d"]}]}', "2026-10-15"),
    )
    return con


def run():
    report = _report()
    grid = range_matrix(report, table_size=6, position="BTN")
    assert grid["status"] == "ok"
    assert len(grid["grid"]) == 13
    assert all(len(row) == 13 for row in grid["grid"])
    labels = [c["class"] for row in grid["grid"] for c in row]
    assert len(set(labels)) == 169
    assert set(labels) == set(HAND_CLASSES)
    assert [grid["grid"][i][i]["class"] for i in range(13)] == [r+r for r in "AKQJT98765432"]
    assert grid["grid"][0][1]["class"] == "AKs"
    assert grid["grid"][1][0]["class"] == "AKo"
    assert _cell(grid, "K5o")["status"] == "observed"
    assert _cell(grid, "K5o")["open_frequency"] == 25.0
    assert _cell(grid, "K9o")["status"] == "observed"
    assert _cell(grid, "K6o")["status"] == "hypothesis"
    assert _cell(grid, "K6o")["hypothesis"] == "K5o+"
    assert _cell(grid, "K6o")["open_frequency"] is None
    assert _cell(grid, "A2o")["status"] == "unknown"
    assert _cell(grid, "A2o")["open_frequency"] is None
    assert "Kh" not in json.dumps(grid) and '"actor_id"' not in json.dumps(grid)
    assert _cell(range_matrix(report, table_size=6, position="BTN",
                              include_hypotheses=False), "K6o")["status"] == "unknown"

    disputed = _report()
    disputed["cohorts_by_players_dealt_in"]["6"]["positions"]["BTN"]["rfi_range"]["hypotheses"][0]["has_counterevidence"] = True
    assert _cell(range_matrix(disputed, table_size=6, position="BTN"), "K6o")["status"] == "unknown"
    invalid_hints = _report()
    invalid_hints["cohorts_by_players_dealt_in"]["6"]["positions"]["BTN"]["rfi_range"]["hypotheses"][0]["candidate_classes"] = ["K5o", "K6o"]
    assert _cell(range_matrix(invalid_hints, table_size=6, position="BTN"), "K6o")["status"] == "unknown"

    sparse = _report()
    sparse["cohorts_by_players_dealt_in"]["6"]["positions"]["BTN"]["rfi_range"]["status"] = "insufficient_sample"
    assert all(c["status"] == "unknown" for r in range_matrix(sparse, table_size=6, position="BTN")["grid"] for c in r)
    # Old report with a formerly observed K5o can be replaced by a revised
    # report without freezing the old cell or hypothetical candidate.
    renewed = _report()
    inner = renewed["cohorts_by_players_dealt_in"]["6"]["positions"]["BTN"]["rfi_range"]
    inner["cells"]["K5o"] = {"status": "unknown"}
    assert _cell(range_matrix(renewed, table_size=6, position="BTN"), "K6o")["status"] == "unknown"
    for fmt in ("mda-sitngo-rfi-v1", "rfi-range-v2"):
        g = range_matrix(_report(game="Sit&Go", fmt=fmt), table_size=6, position="BTN")
        assert g["game"] == "Sit&Go"
        assert _cell(g, "K6o")["status"] == "hypothesis"
    bb = range_matrix({
        "format_version": "mda-all-players-v1", "game": "Ring",
        "cohorts_by_players_dealt_in": {"6": {"positions": {"BB": {"rfi_range": {"status": "not_applicable"}}}}},
    }, table_size=6, position="BB")
    assert bb["status"] == "not_applicable"
    assert all(c["status"] == "unknown" for r in bb["grid"] for c in r)
    hu = range_matrix({
        "format_version": "mda-sitngo-rfi-v1", "game": "Sit&Go",
        "cohorts_by_players_dealt_in": {},
    }, table_size=2, position="BTN/SB")
    assert hu["status"] == "insufficient_sample"

    # An absent but valid 3-handed cohort must return unknown, never leak
    # a six-handed BTN grid. Invalid position/size combinations must fail.
    other = range_matrix(report, table_size=3, position="BTN")
    assert other["status"] == "insufficient_sample"
    assert all(c["status"] == "unknown" for row in other["grid"] for c in row)
    for args in (
        {"table_size": 6, "position": "BTN/SB"},
        {"table_size": 1, "position": "BTN"},
    ):
        try:
            range_matrix(report, **args)
        except ValueError:
            pass
        else:
            raise AssertionError("accepted invalid or cross-cohort grid")

    con = _db()
    try:
        summary = audit_coverage(con)
        cohort = {c["table_size"]: c for c in summary["ring"]["cohorts_by_dealt_in_players"]}
        assert summary["all_player_roles_included"] and not summary["identifiable_rows_returned"]
        assert summary["source_tables_missing"] == []
        assert cohort[6]["completed_hands"] == 121
        assert cohort[6]["fully_captured_hands"] == 120
        assert cohort[6]["distinct_players_in_fully_captured_hands"] == 12
        assert cohort[6]["hands_with_recorded_actions"] == 120
        assert cohort[6]["missing_hole_card_rows"] == 6
        assert cohort[6]["preliminary_readiness"] == "possible_population_sample_requires_rfi_validation"
        assert cohort[2]["preliminary_readiness"] == "insufficient_or_incomplete"
        assert summary["sitngo"]["stored_snapshots"] == 1
        assert summary["sitngo"]["events"] == 1
        txt = json.dumps(summary)
        assert '"user_id"' not in txt and "secret-tourney" not in txt and '"As"' not in txt
        # Missing Sit&Go table is a non-fatal coverage signal.
        con.execute("DROP TABLE sitngo_hands")
        missing = audit_coverage(con)
        assert missing["sitngo"]["status"] == "source_table_missing"
        assert "sitngo_hands" in missing["source_tables_missing"]
    finally:
        con.raw.close()
    print("smoke_test_mda_range_grid_coverage: PASS")


if __name__ == "__main__":
    run()
