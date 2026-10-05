"""Dynamic ring config, JST re-entry limit and admin reset regression."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from smoke_test_learning_integration import isolated_production_app, json_response, login


def _request(client, cookies: dict, method: str, path: str, **kwargs):
    client.cookies.clear()
    client.cookies.update(cookies)
    return client.request(method, path, **kwargs)


def _bust(server, table_id: str, user_id: int) -> None:
    state = server.load_table(table_id)
    player = next(p for p in state["seats"] if int(p["user_id"]) == int(user_id))
    player["stack"] = 0
    player["in_hand"] = False
    player["folded"] = False
    player["all_in"] = False
    player["round_bet"] = 0
    player["contributed"] = 0
    player["cards"] = []
    server.save_table(state)


def _stack(server, table_id: str, user_id: int) -> int:
    state = server.load_table(table_id)
    player = next(p for p in state["seats"] if int(p["user_id"]) == int(user_id))
    return int(player["stack"])


def _insert_hand(db, hand_id: str, hand_no: int, rake_bb: float, *, voided: int = 0) -> None:
    with db.connect() as con:
        con.execute(
            """INSERT INTO online_hands(
                 hand_id,table_id,hand_no,gross_pot_bb,rake_bb,played_at,month,voided
               ) VALUES (?,?,?,?,?,?,?,?)""",
            (hand_id, "jj-table-a", hand_no, 20, rake_bb, db.utcnow(), "2026-10", voided),
        )


def run() -> None:
    with isolated_production_app() as production:
        import ring_admin_config as ring

        app, db, server = production.app, production.db, production.runtime_server
        with (
            patch.object(ring, "_now") as clock,
            TestClient(app, base_url="https://testserver") as client,
        ):
            clock.return_value = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)  # JST 21:00
            admin_user = login(client, "ケンイチロウ", "654321")
            admin_cookies = dict(client.cookies)
            client.cookies.clear()
            user = login(client, "リングテスト", "123456")
            member_cookies = dict(client.cookies)
            client.cookies.clear()
            uid = int(user["id"])
            table_id = "jj-table-a"

            json_response(_request(client, {}, "GET", "/api/admin/console/ring-config"), 401)
            json_response(_request(client, member_cookies, "GET", "/api/admin/console/ring-config"), 403)

            config = json_response(_request(
                client,
                admin_cookies,
                "PATCH",
                "/api/admin/console/ring-config",
                json={
                    "rake_percent": 7.5,
                    "rake_cap_bb": 4.25,
                    "daily_reentry_limit": 2,
                    "min_buyin_bb": 50,
                    "max_buyin_bb": 200,
                },
            ))
            assert config["rake_percent"] == 7.5
            assert config["rake_cap_bb"] == 4.25
            assert config["daily_reentry_limit"] == 2
            assert config["min_buyin_bb"] == 50
            assert config["max_buyin_bb"] == 200

            # Waiting tables immediately advertise the new policy.
            state = server.load_table(table_id)
            assert abs(float(state["rake_percent"]) - 0.075) < 1e-12
            assert int(state["rake_cap"]) == 425
            assert int(state["min_buyin"]) == 5000
            assert int(state["max_buyin"]) == 20000

            player_cfg = json_response(_request(client, member_cookies, "POST", "/api/poker-config"))
            assert player_cfg["rake_percent"] == 7.5
            assert player_cfg["rake_cap_bb"] == 4.25
            assert player_cfg["daily_reentry_limit"] == 2
            assert player_cfg["min_buyin_bb"] == 50
            assert player_cfg["max_buyin_bb"] == 200
            assert player_cfg["reentries"]["used"] == 0

            tables = json_response(_request(client, member_cookies, "GET", "/api/tables"))
            assert tables[0]["min_buyin_bb"] == 50
            assert tables[0]["max_buyin_bb"] == 200
            assert tables[0]["default_buyin_bb"] == 150

            too_low = _request(
                client, member_cookies, "POST", f"/api/tables/{table_id}/join",
                json={"buyin_bb": 40},
            )
            assert too_low.status_code == 400, too_low.text

            # First seating of the JST day is the initial buy-in, not a re-entry.
            joined = json_response(_request(
                client, member_cookies, "POST", f"/api/tables/{table_id}/join",
                json={"buyin_bb": 100},
            ))
            assert any(int(p["user_id"]) == uid for p in joined["seats"])
            assert _stack(server, table_id, uid) == 10000
            usage = ring.usage(db, uid)
            assert usage["date"] == "2026-10-05"
            assert usage["used"] == 0 and usage["total_buyins"] == 1

            # Two re-entries are allowed; the third is rejected server-side.
            _bust(server, table_id, uid)
            json_response(_request(
                client, member_cookies, "POST", f"/api/tables/{table_id}/rebuy",
                json={"buyin_bb": 180},
            ))
            assert _stack(server, table_id, uid) == 18000
            assert ring.usage(db, uid)["used"] == 1

            _bust(server, table_id, uid)
            json_response(_request(
                client,
                member_cookies,
                "POST",
                f"/api/tables/{table_id}/presence",
                json={"mode": "rebuy", "buyin_bb": 120},
            ))
            assert _stack(server, table_id, uid) == 12000
            assert ring.usage(db, uid)["used"] == 2

            # A policy change affects future buy-ins but never rewrites an existing stack.
            tightened = json_response(_request(
                client,
                admin_cookies,
                "PATCH",
                "/api/admin/console/ring-config",
                json={"min_buyin_bb": 80, "max_buyin_bb": 100},
            ))
            assert tightened["min_buyin_bb"] == 80 and tightened["max_buyin_bb"] == 100
            assert _stack(server, table_id, uid) == 12000

            _bust(server, table_id, uid)
            blocked = _request(client, member_cookies, "POST", f"/api/tables/{table_id}/rebuy")
            assert blocked.status_code == 409, blocked.text
            assert ring.usage(db, uid)["used"] == 2

            admin_usage = json_response(_request(
                client,
                admin_cookies,
                "GET",
                "/api/admin/console/ring-reentries",
            ))
            item = next(x for x in admin_usage["items"] if int(x["user_id"]) == uid)
            assert item["used"] == 2 and item["remaining"] == 0

            reset = json_response(_request(
                client,
                admin_cookies,
                "POST",
                f"/api/admin/console/ring-reentries/{uid}/reset",
                json={"reason": "smoke test reset"},
            ))
            assert reset["previous_count"] == 2 and reset["used"] == 0
            assert ring.usage(db, uid)["used"] == 0

            # Reset keeps history but starts a new counting window for the same date.
            json_response(_request(
                client,
                member_cookies,
                "POST",
                f"/api/tables/{table_id}/rebuy",
                json={"buyin_bb": 90},
            ))
            assert _stack(server, table_id, uid) == 9000
            assert ring.usage(db, uid)["used"] == 1
            with db.connect() as con:
                events = int(con.execute(
                    "SELECT COUNT(*) n FROM ring_buyin_events WHERE user_id=? AND jst_date=?",
                    (uid, "2026-10-05"),
                ).fetchone()["n"])
                resets = int(con.execute(
                    "SELECT COUNT(*) n FROM ring_reentry_resets WHERE user_id=? AND jst_date=?",
                    (uid, "2026-10-05"),
                ).fetchone()["n"])
                audits = int(con.execute(
                    "SELECT COUNT(*) n FROM ring_config_audit WHERE actor_id=?",
                    (int(admin_user["id"]),),
                ).fetchone()["n"])
            assert events == 4 and resets == 1 and audits >= 2

            # Rakeback settlement resets only the unsettled balance.
            json_response(_request(client, {}, "GET", "/api/admin/console/ring-rake"), 401)
            json_response(_request(client, member_cookies, "GET", "/api/admin/console/ring-rake"), 403)
            _insert_hand(db, "ring-rake-1", 9001, 1.25)
            _insert_hand(db, "ring-rake-2", 9002, 0.75)
            rake = json_response(_request(client, admin_cookies, "GET", "/api/admin/console/ring-rake"))
            assert rake["current"] == {"rake_bb": 2.0, "rake_points": 200.0, "hands": 2}
            assert rake["all_time"]["rake_points"] == 200.0

            settled = json_response(_request(
                client,
                admin_cookies,
                "POST",
                "/api/admin/console/ring-rake/reset",
                json={"note": "smoke rakeback"},
            ))
            assert settled["current"]["rake_points"] == 0.0
            assert settled["last_reset"]["settled_rake_points"] == 200.0
            assert settled["last_reset"]["hand_count"] == 2

            _insert_hand(db, "ring-rake-3", 9003, 0.50)
            _insert_hand(db, "ring-rake-void", 9004, 1.00, voided=1)
            rake = json_response(_request(client, admin_cookies, "GET", "/api/admin/console/ring-rake"))
            assert rake["current"]["rake_points"] == 50.0
            assert rake["current"]["hands"] == 1
            assert rake["all_time"]["rake_points"] == 250.0

            json_response(_request(
                client, admin_cookies, "POST", "/api/admin/console/ring-rake/reset", json={}
            ))
            empty_reset = _request(
                client, admin_cookies, "POST", "/api/admin/console/ring-rake/reset", json={}
            )
            assert empty_reset.status_code == 409, empty_reset.text
            with db.connect() as con:
                assert int(con.execute("SELECT COUNT(*) n FROM online_hands").fetchone()["n"]) == 4
                assert int(con.execute("SELECT COUNT(*) n FROM ring_rake_settlements").fetchone()["n"]) == 2
                assert int(con.execute(
                    "SELECT COUNT(*) n FROM ring_config_audit WHERE action='rake_settlement_reset'"
                ).fetchone()["n"]) == 2

            # JST calendar rollover starts a fresh daily counter without a cron reset.
            _bust(server, table_id, uid)
            clock.return_value = datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc)  # JST 2026-10-06 00:00
            assert ring.usage(db, uid)["date"] == "2026-10-06"
            assert ring.usage(db, uid)["used"] == 0
            json_response(_request(client, member_cookies, "POST", f"/api/tables/{table_id}/rebuy"))
            assert ring.usage(db, uid)["used"] == 1

    print("JJ_RING_ADMIN_CONFIG_OK")


if __name__ == "__main__":
    run()
