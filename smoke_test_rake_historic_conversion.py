"""Pure regression: rate changes must never reprice historical rake."""
from rake_reconciliation_log import compute


def test_reconciliation():
    hands = [
        dict(table_id="jj-table-a",hand_no=1,rake_bb=10,played_at="2026-09-20T00:00:00+00:00",month="2026-09",voided=0,points_per_bb=None),
        dict(table_id="jj-table-a",hand_no=2,rake_bb=20,played_at="2026-10-13T00:00:00+00:00",month="2026-10",voided=0,points_per_bb=5),
        dict(table_id="jj-table-a",hand_no=3,rake_bb=4,played_at="2026-10-13T00:10:00+00:00",month="2026-10",voided=1,points_per_bb=5),
        dict(table_id="jj-table-a",hand_no=4,rake_bb=2,played_at="2026-10-20T00:00:00+00:00",month="2026-10",voided=0,points_per_bb=2),
    ]
    settlement = [dict(id="rake-test",boundaries_json='{"jj-table-a":2}',
        settled_rake_bb=30,settled_rake_points=150,points_per_bb=5,
        hand_count=2,created_at="2026-10-15T00:00:00+00:00")]
    changes = [
        dict(id=1,created_at="2026-10-10T00:00:00+00:00",
            detail_json='{"changed":{"online_points_per_bb":5}}'),
        dict(id=2,created_at="2026-10-19T00:00:00+00:00",
            detail_json='{"changed":{"online_points_per_bb":2}}')
    ]
    d = compute(hands,settlement,changes,2)
    totals=d["totals"]
    assert totals["hands"]==3, totals
    assert totals["all_rake_bb"]=="32.00", totals
    assert totals["all_historic_rate_points"]=="134.00",totals
    assert totals["all_current_ui_points"]=="64.00",totals
    assert totals["all_ui_minus_historic"]=="-70.00",totals
    assert totals["unsettled_rake_bb"]=="2.00",totals
    assert totals["unsettled_historic_rate_points"]=="4.00",totals
    assert totals["void_hands_excluded"]==1,totals
    assert totals["settlement_point_mismatches"]==1,totals
    assert d["settlements"][0]["points_at_historic_hand_rates"]=="130.00",d
    assert d["settlements"][0]["points_difference_recorded_minus_history"]=="20.00",d


if __name__=="__main__":
    test_reconciliation()
    print("JJ_RAKE_HISTORICAL_RECALC_TEST_OK")
