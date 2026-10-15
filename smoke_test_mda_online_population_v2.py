"""Regress empirical online-table MDA, zero observation ≠ zero true probability."""
from __future__ import annotations

import json
from mda_online_population_v2 import audit_online_population, MIN_OPPORTUNITIES
from mda_online_review_v2 import prepare_review
from smoke_test_mda_all_players import _db, _seed


class ReadSpy:
    """Prove not even a SELECT of private dealt cards enters MDA v2."""
    def __init__(self, raw):
        self.raw = raw
        self.queries = []
    def execute(self, sql, params=()):
        self.queries.append(sql)
        if "hole_cards_json" in sql.lower() or "player_name" in sql.lower():
            raise AssertionError("Private cards/names accessed by MDA v2!")
        return self.raw.execute(sql, params)


def run():
    raw = _db()
    try:
        for i in range(120):
            _seed(raw, i, 6, opened=True, table_id="jj-table-a")
            _seed(raw, 1000+i, 6, opened=False, table_id="jj-table-b")
            _seed(raw, 2000+i, 2, opened=False, table_id="jj-table-a")
        _seed(raw, 8000, 3, table_id="jj-table-b")
        _seed(raw, 8001, 6, status="partial", table_id="jj-table-b")
        _seed(raw, 8002, 6, status="live", table_id="jj-table-a")
        _seed(raw, 8003, 6, table_id="jj-table-c")  # not an approved online table
        spy = ReadSpy(raw)
        report = audit_online_population(spy, batch_size=19)
        assert not any("hole_cards_json" in q for q in spy.queries)
        assert report["format_version"] == "mda-online-population-v2"
        assert report["source_ring_tables"] == ["jj-table-a", "jj-table-b"]
        assert report["coverage"]["complete_scan"]
        assert report["coverage"]["hands_examined"] == 361
        assert report["coverage"]["hands_accepted"] == 361
        assert report["coverage"]["unique_players"] == 12
        assert set(report["cohorts_by_players_dealt_in"]) == {"2", "3", "6"}
        assert "K5o" not in json.dumps(report)
        six = report["cohorts_by_players_dealt_in"]["6"]
        assert six["completed_hands_used"] == 240
        rfi = six["metrics"]["rfi"]["overall"]
        assert rfi["status"] == "observed", rfi
        assert rfi["opportunities"] == 240
        assert rfi["chosen"] == 120
        assert rfi["percentage"] == 50.0
        assert rfi["action_counts"]["raise"] == 120
        assert rfi["action_counts"]["fold"] == 120
        assert "position" in six["metrics"]["rfi"]["cuts"]
        sixbtn = six["metrics"]["rfi"]["cuts"]["position"]["BTN"]
        assert sixbtn["percentage"] == 50.0
        hu = report["cohorts_by_players_dealt_in"]["2"]
        unopened = hu["metrics"]["rfi"]["overall"]
        assert unopened["status"] == "observed"
        assert unopened["chosen"] == 0
        assert unopened["opportunities"] == 120
        assert unopened["percentage"] == 0.0
        # Statistical uncertainty: seeing 0 opens in 120 trials does not
        # imply zero probability, and nothing says any unplayed class is absent.
        assert unopened["wilson_95_percent"][1] > 0
        assert unopened["zero_note"] == "observed_zero_is_not_proof_of_structural_zero"
        assert report["cohorts_by_players_dealt_in"]["3"]["metrics"]["rfi"]["overall"]["status"] == "insufficient_sample"

        preview = prepare_review(report)
        assert preview["format_version"] == "mda-population-v2-review"
        assert preview["no_hand_class_inference"] is True
        assert preview["cohorts_by_players_dealt_in"]["2"]["metrics"]["rfi"]["chosen"] == 0
        sensitive = json.dumps(report)
        for secret in ('"user_id"', '"actor_id"', '"hand_id"', "hole_cards_json", '"Ks"', '"5d"', "Member_"):
            assert secret not in sensitive, secret

        part = audit_online_population(ReadSpy(raw), max_hands=40, batch_size=17)
        assert part["coverage"]["complete_scan"] is False
        assert part["coverage"]["hands_examined"] == 40
        assert part["coverage"]["scope"] == "bounded_partial_scan"
    finally:
        raw.close()
    print("smoke_test_mda_online_population_v2: PASS")


if __name__ == "__main__":
    run()
