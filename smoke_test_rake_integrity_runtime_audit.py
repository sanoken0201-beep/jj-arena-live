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
    assert report["checks"]["current_rake_formula_violation"] == 0
    assert report["checks"]["current_hand_conservation_or_completeness"] == 0
    assert report["checks"]["legacy_rake_formula_violation"] == 0
    assert report["checks"]["legacy_hand_conservation_or_completeness"] == 0
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
    assert broken["checks"]["current_rake_formula_violation"] == 1
    assert broken["checks"]["current_hand_conservation_or_completeness"] == 1
    assert broken["checks"]["current_rake_bound_violation"] == 1
    assert broken["checks"]["points_mismatch"] == 1
    assert "current-flop" in broken["samples"]["rake_formula_violation"]

    # Historical defects remain visible in the all-time/legacy counters but no
    # longer mark the corrected current period unhealthy.
    legacy_hand = {
        "hand_id": "legacy-formula",
        "table_id": "jj-table-a",
        "gross_pot_bb": 10.0,
        "rake_bb": 2.0,
        "played_at": "2026-09-14T15:00:00+00:00",
        "month": "2026-09",
        "voided": 0,
    }
    legacy_results = [
        {
            "id": "legacy-formula:1", "hand_id": "legacy-formula",
            "table_id": "jj-table-a", "user_id": 1,
            "result_bb": 3.0, "points": 9.0, "month": "2026-09",
        },
        {
            "id": "legacy-formula:2", "hand_id": "legacy-formula",
            "table_id": "jj-table-a", "user_id": 2,
            "result_bb": -5.0, "points": -15.0, "month": "2026-09",
        },
    ]
    legacy_history = [{"hand_id": "legacy-formula", "reached_street": "flop", "player_count": 2}]
    legacy = audit.audit_rows(
        [_table()],
        _hands() + [legacy_hand],
        _results() + legacy_results,
        _history() + legacy_history,
    )
    assert legacy["status"] == "ok"
    assert legacy["current_anomaly_total"] == 0
    assert legacy["checks"]["rake_formula_violation"] == 1
    assert legacy["checks"]["legacy_rake_formula_violation"] == 1
    assert legacy["checks"]["current_rake_formula_violation"] == 0
    assert legacy["checks"]["hand_conservation_or_completeness"] == 0
    assert legacy["checks"]["legacy_hand_conservation_or_completeness"] == 0

    # Read-only forensic categorization must distinguish a historically
    # non-conserved payout from an older policy's rake-formula difference.
    assert legacy["legacy_breakdown"]["rake_mismatch_streets"] == {"flop": 1}
    assert legacy["legacy_breakdown"]["completeness_causes"] == {}
    assert legacy["legacy_breakdown"]["by_policy_window"] == {
        "legacy_before_uncalled_fix": {"rake_formula": 1}
    }, legacy["legacy_breakdown"]

    incomplete_hand = {
        "hand_id": "legacy-incomplete",
        "table_id": "jj-table-a",
        "gross_pot_bb": 10.0,
        "rake_bb": 1.0,
        "played_at": "2026-09-14T15:05:00+00:00",
        "month": "2026-09",
        "voided": 0,
    }
    incomplete_result = {
        "id": "legacy-incomplete:1", "hand_id": "legacy-incomplete",
        "table_id": "jj-table-a", "user_id": 1,
        "result_bb": -2.0, "points": -6.0, "month": "2026-09",
    }
    incomplete_history = {
        "hand_id": "legacy-incomplete", "reached_street": "flop",
        "player_count": 2,
    }
    incomplete = audit.audit_rows(
        [_table()], [incomplete_hand], [incomplete_result], [incomplete_history],
    )
    assert incomplete["status"] == "ok"
    assert incomplete["checks"]["legacy_hand_conservation_or_completeness"] == 1
    assert incomplete["checks"]["legacy_rake_formula_violation"] == 0
    assert incomplete["legacy_breakdown"]["completeness_causes"] == {
        "net_not_conserved": 1, "player_result_count_mismatch": 1,
    }, incomplete["legacy_breakdown"]
    assert incomplete["legacy_breakdown"]["by_policy_window"] == {
        "legacy_before_uncalled_fix": {"completeness": 1}
    }, incomplete["legacy_breakdown"]

    dynamic_hand = {
        "hand_id": "configured-rake",
        "table_id": "jj-table-a",
        "gross_pot_bb": 10.0,
        "rake_bb": 0.75,
        "rake_percent": 0.075,
        "rake_cap_bb": 2.5,
        "played_at": "2026-10-05T10:00:00+00:00",
        "month": "2026-10",
        "voided": 0,
    }
    dynamic_results = [
        {"id":"configured-rake:1","hand_id":"configured-rake","table_id":"jj-table-a","user_id":1,"result_bb":4.625,"points":13.88,"month":"2026-10"},
        {"id":"configured-rake:2","hand_id":"configured-rake","table_id":"jj-table-a","user_id":2,"result_bb":-5.375,"points":-16.12,"month":"2026-10"},
    ]
    dynamic_history = [{"hand_id":"configured-rake","reached_street":"flop","player_count":2}]
    configured = audit.audit_rows([_table()], [dynamic_hand], dynamic_results, dynamic_history)
    assert configured["status"] == "ok", configured
    assert configured["policy_windows"] == {"configured_policy": 1}
    assert configured["checks"]["current_rake_formula_violation"] == 0
    assert configured["checks"]["current_rake_bound_violation"] == 0

    # The production integrity audit must not flag legitimately settled
    # results under administrator-selected 5pt/BB, nor silently accept tampering.
    rate_hand = dict(dynamic_hand, hand_id="rate-snapshot", points_per_bb=5)
    rate_rows = [
        {"id":"rate-snapshot:1","hand_id":"rate-snapshot","table_id":"jj-table-a",
         "user_id":1,"result_bb":4.75,"points":23.75,"month":"2026-10"},
        {"id":"rate-snapshot:2","hand_id":"rate-snapshot","table_id":"jj-table-a",
         "user_id":2,"result_bb":-5.50,"points":-27.50,"month":"2026-10"},
    ]
    rate_history = [{"hand_id":"rate-snapshot","reached_street":"flop","player_count":2}]
    variable_rate = audit.audit_rows([_table()], [rate_hand], rate_rows, rate_history)
    assert variable_rate["status"] == "ok", variable_rate
    assert variable_rate["checks"]["points_mismatch"] == 0
    corrupted = list(rate_rows)
    corrupted[0] = dict(corrupted[0], points=14.25)
    detected = audit.audit_rows([_table()], [rate_hand], corrupted, rate_history)
    assert detected["status"] == "warning"
    assert detected["checks"]["points_mismatch"] == 1

    bad_table = _table()
    bad_table["state_json"] = json.dumps({
        "big_blind": 100,
        "rake_percent": 1.50,
        "rake_cap": 500,
    })
    bad_policy = audit.audit_rows([bad_table], _hands(), _results(), _history())
    assert bad_policy["checks"]["fixed_table_policy_violation"] == 1

    print("runtime rake integrity audit regression: ok")


if __name__ == "__main__":
    main()
