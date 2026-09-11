from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient

from smoke_test_learning_integration import isolated_production_app, json_response


def login(client: TestClient, name: str, pin: str) -> dict:
    response = client.post("/api/auth/pin", json={"name": name, "pin": pin})
    payload = json_response(response)
    cookie = response.headers.get("set-cookie", "").lower()
    assert "httponly" in cookie, cookie
    assert payload["user"]["name"] == name
    return payload


def rank_row(client: TestClient, name: str) -> dict | None:
    rows = json_response(client.get("/api/rankings", params={"season": "fall"}))
    return next((row for row in rows if row["name"] == name), None)


def run() -> None:
    with isolated_production_app() as production:
        app, db = production.app, production.db
        with (
            TestClient(app, base_url="https://testserver") as alice,
            TestClient(app, base_url="https://testserver") as bob,
            TestClient(app, base_url="https://testserver") as anonymous,
        ):
            # First visit: visible PIN login and authenticated APIs closed.
            root = anonymous.get("/")
            assert root.status_code == 200
            assert 'id="pinForm"' in root.text
            assert 'id="loginName"' in root.text
            assert 'id="loginPin"' in root.text
            assert "JJ Arenaへ入る" in root.text
            json_response(anonymous.get("/api/me"), 401)

            # First-time account creation and ordinary login state.
            alice_login = login(alice, "ユーザーテスト", "123456")
            assert alice_login["created"] is True
            alice_user = alice_login["user"]
            alice_id = int(alice_user["id"])
            assert json_response(alice.get("/api/me"))["id"] == alice_id

            bob_login = login(bob, "ユーザーベータ", "234567")
            assert bob_login["created"] is True
            bob_user = bob_login["user"]
            bob_id = int(bob_user["id"])
            assert bob_id != alice_id

            # Home-screen data sources available to a normal member.
            for path in ("/api/rankings", "/api/schedules", "/api/announcements", "/api/tables"):
                assert alice.get(path).status_code == 200, path
            tables = json_response(alice.get("/api/tables"))
            assert [t["id"] for t in tables] == ["jj-table-a", "jj-table-b"]
            assert all(int(t["max_seats"]) == 6 for t in tables)

            # Daily Quiz: exactly +10 once, reflected in ranking.
            ranking_name = alice_user["ranking_name"] or alice_user["name"]
            before_rank = rank_row(alice, ranking_name)
            before_points = float((before_rank or {}).get("points", 0))
            question = json_response(alice.get("/api/quiz/question"))
            assert question["reward"] == 10
            assert "correct_answer" not in question
            with db.connect() as con:
                attempt = dict(
                    con.execute(
                        "SELECT question_json FROM quiz_daily_answers WHERE id=? AND user_id=?",
                        (question["id"], alice_id),
                    ).fetchone()
                )
            correct = json.loads(attempt["question_json"])["correct"]
            answer = {"question_id": question["id"], "answer": correct}
            first = json_response(alice.post("/api/quiz/answer", json=answer))
            duplicate = json_response(alice.post("/api/quiz/answer", json=answer))
            assert first["awarded"] == 10 and first["already_answered"] is False
            assert duplicate["awarded"] == 0 and duplicate["already_answered"] is True
            after_rank = rank_row(alice, ranking_name)
            assert after_rank is not None
            assert float(after_rank["points"]) == before_points + 10

            # Strategy discussion: one member creates, another replies.
            thread = json_response(
                alice.post(
                    "/api/threads",
                    json={"title": "BTN vs BBの相談", "body": "このラインをどう考えますか？"},
                )
            )
            thread_id = int(thread["id"])
            json_response(
                bob.post(
                    f"/api/threads/{thread_id}/replies",
                    json={"body": "まずポットオッズから整理します。"},
                )
            )
            threads = json_response(alice.get("/api/threads"))
            created = next(row for row in threads if int(row["id"]) == thread_id)
            assert created["title"] == "BTN vs BBの相談"
            assert any(reply["author_name"] == bob_user["name"] for reply in created["replies"])

            # Real-time poker: seat, ready, start, private-card boundary, action,
            # idempotency receipt, chat, and sit-out-next-hand behavior.
            table_id = "jj-table-a"
            alice_seat = json_response(alice.post(f"/api/tables/{table_id}/seat", json={"seat": 0}))
            bob_seat = json_response(bob.post(f"/api/tables/{table_id}/seat", json={"seat": 1}))
            assert any(int(p["user_id"]) == alice_id for p in alice_seat["seats"])
            assert any(int(p["user_id"]) == bob_id for p in bob_seat["seats"])

            other_table = alice.post("/api/tables/jj-table-b/seat", json={"seat": 0})
            assert other_table.status_code == 400

            json_response(alice.post(f"/api/tables/{table_id}/start"))
            started = json_response(bob.post(f"/api/tables/{table_id}/start"))
            assert started["status"] == "playing"
            assert started["hand"] and started["hand"]["action_seat"] is not None

            alice_state = json_response(alice.get(f"/api/tables/{table_id}"))["state"]
            bob_state = json_response(bob.get(f"/api/tables/{table_id}"))["state"]
            for state, own_id, other_id in (
                (alice_state, alice_id, bob_id),
                (bob_state, bob_id, alice_id),
            ):
                own = next(p for p in state["seats"] if int(p["user_id"]) == own_id)
                other = next(p for p in state["seats"] if int(p["user_id"]) == other_id)
                assert len(own["cards"]) == 2 and own["cards"] != ["??", "??"]
                assert other["cards"] == ["??", "??"], other

            action_seat = int(alice_state["hand"]["action_seat"])
            actor_player = next(p for p in alice_state["seats"] if int(p["seat"]) == action_seat)
            actor = alice if int(actor_player["user_id"]) == alice_id else bob
            actor_state = json_response(actor.get(f"/api/tables/{table_id}"))["state"]
            legal = actor_state["legal"]
            assert legal["can_act"] is True
            if legal.get("can_call"):
                action_name = "call"
            elif legal.get("can_check"):
                action_name = "check"
            else:
                action_name = "fold"
            action_id = "journey-" + uuid.uuid4().hex[:16]
            acted = json_response(
                actor.post(
                    f"/api/tables/{table_id}/action",
                    json={"action": action_name, "action_id": action_id},
                )
            )
            repeated = json_response(
                actor.post(
                    f"/api/tables/{table_id}/action",
                    json={"action": action_name, "action_id": action_id},
                )
            )
            assert repeated["hand_no"] == acted["hand_no"]

            json_response(
                alice.post(
                    f"/api/tables/{table_id}/chat",
                    json={"body": "ナイスハンド、テストです"},
                )
            )
            bob_view = json_response(bob.get(f"/api/tables/{table_id}"))
            assert any(msg["body"] == "ナイスハンド、テストです" for msg in bob_view["messages"])

            sitout = json_response(
                alice.post(f"/api/tables/{table_id}/presence", json={"mode": "sitout"})
            )
            alice_row = next(p for p in sitout["seats"] if int(p["user_id"]) == alice_id)
            assert alice_row.get("sit_out_next") is True or alice_row.get("sitting_out") is True
            json_response(
                alice.post(f"/api/tables/{table_id}/presence", json={"mode": "cancel_sitout"})
            )

            # Logout and wrong-PIN recovery path.
            json_response(alice.post("/api/auth/logout"))
            json_response(alice.get("/api/me"), 401)
            wrong = alice.post("/api/auth/pin", json={"name": alice_user["name"], "pin": "999999"})
            assert wrong.status_code == 401
            relogin = login(alice, alice_user["name"], "123456")
            assert relogin["created"] is False

    print("JJ_MEMBER_USER_JOURNEY_OK")


if __name__ == "__main__":
    run()
