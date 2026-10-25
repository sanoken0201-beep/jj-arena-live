"""Regression: administrator handover is an additive grant, never account retirement."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


def run() -> None:
    root = Path(tempfile.mkdtemp(prefix="jj-admin-delegation-"))
    os.environ.pop("DATABASE_URL", None)
    os.environ["JJ_DB_PATH"] = str(root / "roles.sqlite3")
    os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"
    os.environ["JJ_ADMIN_NAME"] = "カンリシャ"
    os.environ["JJ_ADMIN_PIN"] = "654321"
    os.environ["RENDER"] = "1"

    from build_served_assets import main as build_assets
    build_assets()
    import app as production

    base = "https://testserver"
    with (
        TestClient(production.app, base_url=base) as original,
        TestClient(production.app, base_url=base) as successor,
        TestClient(production.app, base_url=base) as candidate,
    ):
        def login(client, name, pin, expected_role):
            response = client.post("/api/auth/pin", json={"name": name, "pin": pin})
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["user"]["role"] == expected_role, data
            return int(data["user"]["id"])

        admin_id = login(original, "カンリシャ", "654321", "admin")
        next_id = login(successor, "ヒキツギ", "112233", "member")
        candidate_id = login(candidate, "ホカノカンリ", "223344", "member")
        endpoint = lambda uid: f"/api/admin/console/users/{uid}/role"

        # Create representative official history for the original and successor.
        # The grant must never replace an account, clear its points or edit its
        # prior activity, regardless of the source.
        with production.db.connect() as con:
            con.execute(
                "INSERT INTO entries(id,date,name,remaining,reentries,initial,points,"
                "game,game_type,source,created_by,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                ("succession-club", "2026-10-10", "カンリシャ",
                 120, 0, 100, 20, "test", "ring", "test", admin_id,
                 "2026-10-10T10:00:00+00:00"),
            )
            con.execute(
                "INSERT INTO point_ledger(id,user_id,amount,kind,reason,effective_at,"
                "created_by,created_at) VALUES (?,?,?,?,?,?,?,?)",
                ("succession-ledger", next_id, 42, "admin_credit", "handover regression",
                 "2026-10-10T10:00:00+00:00", admin_id,
                 "2026-10-10T10:00:00+00:00"),
            )
            con.execute(
                "INSERT INTO online_hands(hand_id,table_id,hand_no,gross_pot_bb,"
                "rake_bb,played_at,month) VALUES (?,?,?,?,?,?,?)",
                ("succession-hand", "1-3-3", 1, 10, 1,
                 "2026-10-10T10:00:00+00:00", "2026-10"),
            )
            con.execute(
                "INSERT INTO online_hand_results(id,hand_id,table_id,user_id,"
                "ranking_name,result_bb,points,month,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                ("succession-result", "succession-hand", "1-3-3", admin_id,
                 "カンリシャ", 5, 5, "2026-10",
                 "2026-10-10T10:00:00+00:00"),
            )

        def history_snapshot():
            with production.db.connect() as con:
                def record(table, key, row_id):
                    row = con.execute(
                        f"SELECT * FROM {table} WHERE {key}=?", (row_id,)
                    ).fetchone()
                    assert row is not None, (table, row_id)
                    return dict(row)

                return (
                    record("entries", "id", "succession-club"),
                    record("point_ledger", "id", "succession-ledger"),
                    record("online_hands", "hand_id", "succession-hand"),
                    record("online_hand_results", "id", "succession-result"),
                )

        before = history_snapshot()
        js = original.get("/admin-static/admin_role_delegation.js")
        assert js.status_code == 200
        assert "この会員を管理者に追加" in js.text
        assert "一般会員に変更" not in js.text
        assert successor.post(endpoint(candidate_id), json={
            "role": "admin", "current_pin": "112233"
        }).status_code == 403
        assert original.post(endpoint(next_id),
            headers={"Sec-Fetch-Site": "cross-site"},
            json={"role": "admin", "current_pin": "654321"}).status_code == 403
        assert original.post(endpoint(next_id), json={
            "role": "owner", "current_pin": "654321"
        }).status_code == 422
        assert original.post(endpoint(next_id), json={
            "role": "admin", "current_pin": "654321"
        }).status_code == 409  # Verification required.

        for uid in (next_id, candidate_id):
            verified = original.patch(
                f"/api/admin/console/users/{uid}",
                json={"club_verified": True},
            )
            assert verified.status_code == 200, verified.text

        wrong = original.post(endpoint(next_id), json={
            "role": "admin", "current_pin": "000000"
        })
        assert wrong.status_code == 403, wrong.text
        assert original.get("/api/admin/console/users").status_code == 200

        promoted = original.post(endpoint(next_id), json={
            "role": "admin", "current_pin": "654321"
        })
        assert promoted.status_code == 200 and promoted.json()["changed"], promoted.text
        # The original administrator stays logged in with unchanged powers.
        assert original.get("/api/admin/console/users").status_code == 200
        assert history_snapshot() == before, "An additive grant modified official history"
        # The newly elevated account must sign in again to gain admin authority.
        assert successor.get("/api/me").status_code == 401
        assert login(successor, "ヒキツギ", "112233", "admin") == next_id

        repeated = original.post(endpoint(next_id), json={
            "role": "admin", "current_pin": "654321"
        })
        assert repeated.status_code == 200 and not repeated.json()["changed"]
        assert successor.get("/api/admin/console/users").status_code == 200

        delegated = successor.post(endpoint(candidate_id), json={
            "role": "admin", "current_pin": "112233"
        })
        assert delegated.status_code == 200 and delegated.json()["changed"], delegated.text
        assert candidate.get("/api/me").status_code == 401
        assert login(candidate, "ホカノカンリ", "223344", "admin") == candidate_id

        # The former "handover" UI could demote a previous administrator.
        # Even an old cached client can no longer do that through this API.
        for actor, pin, uid in (
            (original, "654321", next_id),
            (successor, "112233", admin_id),
            (candidate, "223344", admin_id),
        ):
            denied = actor.post(endpoint(uid), json={
                "role": "member", "current_pin": pin
            })
            assert denied.status_code == 422, denied.text

        for client in (original, successor, candidate):
            assert client.get("/api/admin/console/users").status_code == 200
        assert history_snapshot() == before

        with production.db.connect() as con:
            admins = con.execute(
                "SELECT id FROM users WHERE role='admin' AND deleted_at IS NULL ORDER BY id"
            ).fetchall()
            assert {int(row["id"]) for row in admins} == {
                admin_id, next_id, candidate_id
            }
            audit = con.execute(
                "SELECT actor_id,target_user_id,detail_json FROM admin_audit_log "
                "WHERE action='user.role_change' ORDER BY id"
            ).fetchall()
            assert len(audit) == 2, audit
            assert [int(row["target_user_id"]) for row in audit] == [
                next_id, candidate_id
            ]
            assert all('"succession":"additive"' in row["detail_json"] for row in audit)
            assert all(
                "654321" not in row["detail_json"] and
                "112233" not in row["detail_json"] and
                "223344" not in row["detail_json"]
                for row in audit
            ), "A PIN appeared in role audit"

        # Render restarts may call both core initialization routines again.
        # All administrators, their sessions/PINs and official history survive.
        production.db.init_db()
        production.db.seed_if_needed()
        with production.db.connect() as con:
            roles = {
                int(row["id"]): row["role"]
                for row in con.execute(
                    "SELECT id,role FROM users WHERE id IN (?,?,?)",
                    (admin_id, next_id, candidate_id),
                ).fetchall()
            }
            assert roles == {
                admin_id: "admin", next_id: "admin", candidate_id: "admin"
            }, roles
        assert history_snapshot() == before
        for client in (original, successor, candidate):
            assert client.get("/api/admin/console/users").status_code == 200

    print("JJ_ADMIN_ADDITIVE_HANDOVER_RESTART_OK; JJ_ADMIN_ROLE_DELEGATION_OK")


if __name__ == "__main__":
    run()
