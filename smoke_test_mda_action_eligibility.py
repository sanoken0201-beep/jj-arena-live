"""Runtime legality, historical unknowns and unbiased aggression denominators."""
from materialized_v1244.poker_engine import legal_actions
from mda_action_eligibility import can_increase_wager
from mda_online_population_v2 import audit_online_population
from smoke_test_mda_all_players import _db, _seed

def run():
    for stack, closed, expected in [(1000,False,1),(250,False,1),(100,False,0),(1000,True,0)]:
        player = {"user_id":1,"seat":0,"stack":stack,"round_bet":100,
                  "in_hand":True,"folded":False,"all_in":False,"name":"test"}
        state = {"status":"playing","seats":[player],"hand":{
            "action_seat":0,"current_bet":300,"min_raise":200,
            "raise_closed_for":[1] if closed else []}}
        legal = legal_actions(state, 1)
        assert can_increase_wager(legal, 300) == expected, (stack, closed, legal)
        if stack == 250:
            assert not legal["can_raise"] and legal["can_all_in"]
    assert can_increase_wager({"can_act":False}, 300) is None

    con = _db()
    try:
        for i in range(120):
            _seed(con, i, 6)
        # No table: historic raises do not become success-only samples.
        old = audit_online_population(con)
        assert old["cohorts_by_players_dealt_in"]["6"]["metrics"]["rfi"]["overall"]["status"] == "insufficient_sample"
        assert old["coverage"]["aggressive_opportunities_unknown_excluded"] > 0
        con.execute("CREATE TABLE jj_hand_action_eligibility(hand_id TEXT,seq INTEGER,can_increase_wager INTEGER)")
        con.execute("INSERT INTO jj_hand_action_eligibility SELECT hand_id,seq,1 FROM jj_hand_actions")
        full = audit_online_population(con)
        assert full["cohorts_by_players_dealt_in"]["6"]["metrics"]["rfi"]["overall"]["opportunities"] == 480
        # Remove one prior folding decision per hand from the legal opportunities.
        con.execute("UPDATE jj_hand_action_eligibility SET can_increase_wager=0 WHERE seq=1")
        restricted = audit_online_population(con)
        rfi = restricted["cohorts_by_players_dealt_in"]["6"]["metrics"]["rfi"]["overall"]
        assert (rfi["chosen"], rfi["opportunities"]) == (120,360)
        assert restricted["coverage"]["aggressive_opportunities_unavailable_excluded"] == 120
        con.execute("UPDATE jj_hand_action_eligibility SET can_increase_wager=NULL WHERE seq=4")
        unknown = audit_online_population(con)
        rfi = unknown["cohorts_by_players_dealt_in"]["6"]["metrics"]["rfi"]["overall"]
        assert (rfi["chosen"],rfi["opportunities"]) == (0,240)
        assert rfi["wilson_95_percent"][1] > 0
        assert unknown["coverage"]["aggressive_opportunities_unknown_excluded"] == 120
    finally:
        con.close()
    print("smoke_test_mda_action_eligibility: PASS")

if __name__ == "__main__":
    run()
