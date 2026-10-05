"""Dynamic ring config, JST re-entry limit and admin reset regression."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from smoke_test_learning_integration import isolated_production_app, json_response, login


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


def run() -> None:
    with isolated_production_app() as production:
        import ring_admin_config as ring

        app, db, server = production.app, production.db, production.runtime_server
        with (
            patch.object(ring, "_now") as clock,
            TestClient(app, base_url="https://testserver") as admin,
            TestClient(app, base_url="https://testserver") as member,
            TestClient(app, base_url="https://testserver") as anonymous,
        ):
            clock.return_value = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)  # JST 21:00
            admin_user = login(admin, "ケンイチロウ", "654321")
            user = login(member, "リングテスト", "123456")
            uid = int(user["id"])
            table_id = "jj-table-a"

            json_response(anonymous.get("/api/admin/console/ring-config"), 401)
            json_response(member.get("/api/admin/console/ring-config"), 403)

            config = json_response(admin.patch(
                "/api/admin/console/ring-config",
                json={"rake_percent": 7.5, "rake_cap_bb": 4.25, "daily_reentry_limit": 2},
            ))
            assert config["rake_percent"] == 7.5
            assert config["rake_cap_bb"] == 4.25
            assert config["daily_reentry_limit"] == 2

            # Waiting tables immediately advertise the new policy.
            state = server.load_table(table_id)
            assert abs(float(state["rake_percent"]) - 0.075) < 1e-12
            assert int(state["rake_cap"]) == 425

            player_cfg = json_response(member.post("/api/poker-config"))
            assert player_cfg["rake_percent"] == 7.5
            assert player_cfg["rake_cap_bb"] == 4.25
            assert player_cfg["daily_reentry_limit"] == 2
            assert player_cfg["reentries"]["used"] == 0

            # First seating of the JST day is the initial buy-in, not a re-entry.
            joined = json_response(member.post(f"/api/tables/{table_id}/join"))
            assert any(int(p["user_id"]) == uid for p in joined["seats"])
            usage = ring.usage(db, uid)
            assert usage["date"] == "2026-10-05"
            assert usage["used"] == 0 and usage["total_buyins"] == 1

            # Two re-entries are allowed; the third is rejected server-side.
            _bust(server, table_id, uid)
            json_response(member.post(f"/api/tables/{table_id}/rebuy"))
            assert ring.usage(db, uid)["used"] == 1

            _bust(server, table_id, uid)
            json_response(member.post(
                f"/api/tables/{table_id}/presence",
                json={"mode": "rebuy"},
            ))
            assert ring.usage(db, uid)["used"] == 2

            _bust(server, table_id, uid)
            blocked = member.post(f"/api/tables/{table_id}/rebuy")
            assert blocked.status_code == 409, blocked.text
            assert ring.usage(db, uid)["used"] == 2

            admin_usage = json_response(admin.get("/api/admin/console/ring-reentries"))
            item = next(x for x in admin_usage["items"] if int(x["user_id"]) == uid)
            assert item["used"] == 2 and item["remaining"] == 0

            reset = json_response(admin.post(
                f"/api/admin/console/ring-reentries/{uid}/reset",
                json={"reason": "smoke test reset"},
            ))
            assert reset["previous_count"] == 2 and reset["used"] == 0
            assert ring.usage(db, uid)["used"] == 0

            # Reset keeps history but starts a new counting window for the same date.
            json_response(member.post(f"/api/tables/{table_id}/rebuy"))
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

            # JST calendar rollover starts a fresh daily counter without a cron reset.
            _bust(server, table_id, uid)
            clock.return_value = datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc)  # JST 2026-10-06 00:00
            assert ring.usage(db, uid)["date"] == "2026-10-06"
            assert ring.usage(db, uid)["used"] == 0
            json_response(member.post(f"/api/tables/{table_id}/rebuy"))
            assert ring.usage(db, uid)["used"] == 1

    print("JJ_RING_ADMIN_CONFIG_OK")


if __name__ == "__main__":
    run()
