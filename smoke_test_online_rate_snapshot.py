"""Online Ring rate changes preserve completed results and snapshot live hands."""
from __future__ import annotations

from fastapi.testclient import TestClient
from smoke_test_learning_integration import isolated_production_app, json_response, login


def main() -> None:
    with isolated_production_app() as production:
        app, db, server = production.app, production.db, production.runtime_server
        import poker_engine

        with TestClient(app, base_url="https://testserver") as client:
            admin = login(client, "ケンイチロウ", "654321")
            admin_cookie = dict(client.cookies)
            client.cookies.clear()
            player = login(client, "レートテスト", "123456")
            uid = int(player["id"])
            client.cookies.clear()
            client.cookies.update(admin_cookie)

            def rate(value):
                response = client.patch(
                    "/api/admin/console/settings",
                    json={"online_points_per_bb": value},
                )
                assert response.status_code == 200, response.text
                assert response.json()["online_points_per_bb"] == value

            def start_state():
                state = poker_engine.blank_table_state(
                    table_id="jj-table-a", name="Conversion Regression",
                    max_seats=6, small_blind=50, big_blind=100,
                    min_buyin=15000, max_buyin=15000,
                )
                poker_engine.seat_player(
                    state, user_id=uid, name="レートテスト", seat=0, stack=15000,
                )
                poker_engine.seat_player(
                    state, user_id=int(admin["id"]), name="ケンイチロウ",
                    seat=1, stack=15000,
                )
                server.start_hand(state)
                assert state["hand"]["phase"] == "preflop"
                return state

            def settle(state, amount=1000):
                state["hand"]["phase"] = "complete"
                state["last_result"] = {
                    "gross_pot": amount, "rake": 0, "net_results": [
                        {"user_id": uid, "name": "レートテスト", "amount": amount},
                    ],
                }
                with db.connect() as con:
                    result = db._record_online_hand(con, state)
                    hand_id = result["hand_id"]
                    hand = con.execute(
                        "SELECT points_per_bb FROM online_hands WHERE hand_id=?",
                        (hand_id,),
                    ).fetchone()
                    row = con.execute(
                        "SELECT result_bb,points FROM online_hand_results WHERE id=?",
                        (f"{hand_id}:{uid}",),
                    ).fetchone()
                return hand_id, float(hand["points_per_bb"]), float(row["result_bb"]), float(row["points"])

            rate(3.0)
            old = start_state()
            assert float(old["hand"]["points_per_bb_snapshot"]) == 3
            rate(5.0)  # while the hand is already in progress
            first = settle(old)
            assert first[1:] == (3, 10, 30), first

            new = start_state()
            assert float(new["hand"]["points_per_bb_snapshot"]) == 5
            rate(2.0)
            second = settle(new)
            assert second[1:] == (5, 10, 50), second

            # A duplicate settlement must never reprice recorded outcomes.
            assert settle(old) == first
            assert settle(new) == second
            db.init_db()  # Reopening production must not rewrite 30/50 to 3x.
            with db.connect() as con:
                points = [
                    float(r["points"]) for r in con.execute(
                        "SELECT points FROM online_hand_results WHERE user_id=? ORDER BY created_at,id",
                        (uid,),
                    ).fetchall()
                ]
            assert sorted(points) == [30, 50], points

            rows = json_response(client.get("/api/rankings?season=fall"))
            rank = next(row for row in rows if row["name"] == "レートテスト")
            assert rank["online_raw_points"] == 80
            assert rank["online_points"] == 80
            assert rank["points"] == 80
            config = json_response(client.post("/api/poker-config", json={}))
            assert config["ranking_points_per_bb"] == 2

            invalid = client.patch("/api/admin/console/settings", json={"online_points_per_bb": 0.001})
            assert invalid.status_code == 422, invalid.text

    print("JJ_ONLINE_RATE_SNAPSHOT_OK immutable-history hand-start-rate replay ranking api-validation")


if __name__ == "__main__":
    main()
