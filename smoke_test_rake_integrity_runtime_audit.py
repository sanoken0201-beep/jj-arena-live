from __future__ import annotations

import json

import rake_integrity_runtime_audit as audit


def _table():
    return {
        "id": "jj-table-a",
        "name": "JJ Table A",
        "state_json": json.dumps({
            "big_blind": 100,
            "rake_percent": 0.05,
            "rake_cap": 300,
        }),
    }


def _hands():
    return [
        {
            "hand_id": "current-flop",
            "table_id": "jj-table-a",
            "gross_pot_bb": 10.00,
            "rake_bb": 0.50,
            "played_at": "2026-09-20T10:00:00+00:00",
            "month": "2026-09",
            "voided": 0,
        },
        {
            "hand_id": "current-preflop",
            "table_id": "jj-table-a",
            "gross_pot_bb": 1.00,
            "rake_bb": 0.00,
            "played_at": "2026-09-20T10:01:00+00:00",
            "month": "2026-09",
            "voided": 0,
        },
    ]


def _results():
    return [
        {
            "id": "current-flop:1",
            "hand_id": "current-flop",
            "table_id": "jj-table-a",
            "user_id": 1,
            "result_bb": 4.75,
            "points": 14.25,
            "month": "2026-09",
        },
        {
            "id": "current-flop:2",
            "hand_id": "current-flop",
            "table_id": "jj-table-a",
            "user_id": 2,
            "result_bb": -5.25,
            "points": -15.75,
            "month": "2026-09",
        },
        {
            "id": "current-preflop:1",
            "hand_id": "current-preflop",
            "table_id": "jj-table-a",
            "user_id": 1,
            "result_bb": 0.50,
            "points": 1.50,
            "month": "2026-09",
        },
        {
            "id": "current-preflop:2",
            "hand_id": "current-preflop",
            "table_id": "jj-table-a",
            "user_id": 2,
            "result_bb": -0.50,
            "points": -1.50,
            "month": "2026-09",
        },
    ]


def _history():
    return [
        {"hand_id": "current-flop", "reached_street": "flop", "player_count": 2},
        {"hand_id": "current-preflop", "reached_street": "preflop", "player_count": 2},
    ]


def main():
    class Pg:
        IS_POSTGRES = True

    class Sqlite:
        IS_POSTGRES = False

    assert audit.should_run(Pg(), {"RENDER": "true"})
    assert audit.should_run(Pg(), {"RENDER": "1"})
    assert audit.should_run(Pg(), {"RENDER": "YES"})
    assert not audit.should_run(Pg(), {"RENDER": "false"})
    assert not audit.should_run(Sqlite(), {"RENDER": "true"})

    report = audit.audit_rows([_table()], _hands(), _results(), _history())
    assert report["status"] == "ok"
    assert report["current_anomaly_total"] == 0
    assert report["checks"]["rake_formula_violation"] == 0
    assert report["checks"]["current_rake_bound_violation"] == 0
    assert report["checks"]["current_noflop_violation"] == 0
    assert report["checks"]["points_mismatch"] == 0
    assert report["policy_windows"] == {"current_5pct_3bb": 2}

    broken_hands = _hands()
    broken_hands[0] = dict(broken_hands[0], rake_bb=4.0)
    broken_results = _results()
    broken_results[0] = dict(broken_results[0], points=999)

    broken = audit.audit_rows([_table()], broken_hands, broken_results, _history())
    assert broken["status"] == "warning"
    assert broken["checks"]["rake_formula_violation"] == 1
    assert broken["checks"]["current_rake_bound_violation"] == 1
    assert broken["checks"]["points_mismatch"] == 1
    assert "current-flop" in broken["samples"]["rake_formula_violation"]

    bad_table = _table()
    bad_table["state_json"] = json.dumps({
        "big_blind": 100,
        "rake_percent": 0.10,
        "rake_cap": 500,
    })
    bad_policy = audit.audit_rows([bad_table], _hands(), _results(), _history())
    assert bad_policy["checks"]["fixed_table_policy_violation"] == 1

    print("runtime rake integrity audit regression: ok")


if __name__ == "__main__":
    main()
