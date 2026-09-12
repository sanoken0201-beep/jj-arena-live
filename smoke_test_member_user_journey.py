from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient

from smoke_test_learning_integration import isolated_production_app, json_response


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login(client: TestClient, name: str, pin: str) -> tuple[dict, str]:
    response = client.post("/api/auth/pin", json={"name": name, "pin": pin})
    payload = json_response(response)
    cookie = response.headers.get("set-cookie", "").lower()
    assert "httponly" in cookie, cookie
    assert payload["user"]["name"] == name
    token = response.cookies.get("jj_session") or client.cookies.get("jj_session")
    assert token, "PIN login did not issue a session token"
    return payload, str(token)


def rank_row(client: TestClient, token: str, name: str) -> dict | None:
    rows = json_response(client.get("/api/rankings", params={"season": "fall"}, headers=auth(token)))
    return next((row for row in rows if row["name"] == name), None)


def run() -> None:
    with isolated_production_app() as production:
        app, db = production.app, production.db
        # A single TestClient gives the production app one lifespan/event loop,
        # matching the runtime model used by one Uvicorn worker. Alice/Bob switch
        # identity through their real bearer session tokens.
        with TestClient(app, base_url="https://testserver") as client:
            root = client.get("/")
            assert root.status_code == 200
            assert 'id="pinForm"' in root.text
            assert 'id="loginName"' in root.text
            assert 'id="loginPin"' in root.text
            assert "JJ Arenaへ入る" in root.text
            json_response(client.get("/api/me"), 401)

            alice_login, alice_token = login(client, "ユーザーテスト", "123456")
            assert alice_login["created"] is True
            alice_user = alice_login["user"]
            alice_id = int(alice_user["id"])
            assert json_response(client.get("/api/me", headers=auth(alice_token)))["id"] == alice_id

            bob_login, bob_token = login(client, "ユーザーベータ", "234567")
            assert bob_login["created"] is True
            bob_user = bob_login["user"]
            bob_id = int(bob_user["id"])
            assert bob_id != alice_id

            for path in ("/api/rankings", "/api/schedules", "/api/announcements", "/api/tables"):
                assert client.get(path, headers=auth(alice_token)).status_code == 200, path
            tables = json_response(client.get("/api/tables", headers=auth(alice_token)))
            assert [t["id"] for t in tables] == ["jj-table-a", "jj-table-b"]
            assert all(int(t["max_seats"]) == 6 for t in tables)

            ranking_name = alice_user["ranking_name"] or alice_user["name"]
            before_rank = rank_row(client, alice_token, ranking_name)
            before_points = float((before_rank or {}).get("points", 0))
            question = json_response(client.get("/api/quiz/question", headers=auth(alice_token)))
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
            first = json_response(client.post("/api/quiz/answer", json=answer, headers=auth(alice_token)))
            duplicate = json_response(client.post("/api/quiz/answer", json=answer, headers=auth(alice_token)))
            assert first["awarded"] == 10 and first["already_answered"] is False
            assert duplicate["awarded"] == 0 and duplicate["already_answered"] is True
            after_rank = rank_row(client, alice_token, ranking_name)
            assert after_rank is not None
            assert float(after_rank["points"]) == before_points + 10

            thread = json_response(
                client.post(
                    "/api/threads",
                    json={"title": "BTN vs BBの相談", "body": "このラインをどう考えますか？"},
                    headers=auth(alice_token),
                )
            )
            thread_id = int(thread["id"])
            json_response(
                client.post(
                    f"/api/threads/{thread_id}/replies",
                    json={"body": "まずポットオッズから整理します。"},
                    headers=auth(bob_token),
                )
            )
            threads = json_response(client.get("/api/threads", headers=auth(alice_token)))
            created = next(row for row in threads if int(row["id"]) == thread_id)
            assert created["title"] == "BTN vs BBの相談"
            assert any(reply["author_name"] == bob_user["name"] for reply in created["replies"])

            table_id = "jj-table-a"
            alice_seat = json_response(
                client.post(f"/api/tables/{table_id}/seat", json={"seat": 0}, headers=auth(alice_token))
            )
            bob_seat = json_response(
                client.post(f"/api/tables/{table_id}/seat", json={"seat": 1}, headers=auth(bob_token))
            )
            assert any(int(p["user_id"]) == alice_id for p in alice_seat["seats"])
            assert any(int(p["user_id"]) == bob_id for p in bob_seat["seats"])

            other_table = client.post("/api/tables/jj-table-b/seat", json={"seat": 0}, headers=auth(alice_token))
            assert other_table.status_code == 400

            json_response(client.post(f"/api/tables/{table_id}/start", headers=auth(alice_token)))
            started = json_response(client.post(f"/api/tables/{table_id}/start", headers=auth(bob_token)))
            assert started["status"] == "playing"
            assert started["hand"] and started["hand"]["action_seat"] is not None

            alice_state = json_response(client.get(f"/api/tables/{table_id}", headers=auth(alice_token)))["state"]
            bob_state = json_response(client.get(f"/api/tables/{table_id}", headers=auth(bob_token)))["state"]
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
            actor_token = alice_token if int(actor_player["user_id"]) == alice_id else bob_token
            actor_state = json_response(client.get(f"/api/tables/{table_id}", headers=auth(actor_token)))["state"]
            legal = actor_state["legal"]
            assert legal["can_act"] is True
            action_name = "call" if legal.get("can_call") else "check" if legal.get("can_check") else "fold"
            action_id = "journey-" + uuid.uuid4().hex[:16]
            payload = {"action": action_name, "action_id": action_id}
            acted = json_response(
                client.post(f"/api/tables/{table_id}/action", json=payload, headers=auth(actor_token))
            )
            repeated = json_response(
                client.post(f"/api/tables/{table_id}/action", json=payload, headers=auth(actor_token))
            )
            assert repeated["hand_no"] == acted["hand_no"]

            json_response(
                client.post(
                    f"/api/tables/{table_id}/chat",
                    json={"body": "ナイスハンド、テストです"},
                    headers=auth(alice_token),
                )
            )
            bob_view = json_response(client.get(f"/api/tables/{table_id}", headers=auth(bob_token)))
            assert any(msg["body"] == "ナイスハンド、テストです" for msg in bob_view["messages"])

            sitout = json_response(
                client.post(
                    f"/api/tables/{table_id}/presence",
                    json={"mode": "sitout"},
                    headers=auth(alice_token),
                )
            )
            alice_row = next(p for p in sitout["seats"] if int(p["user_id"]) == alice_id)
            assert alice_row.get("sit_out_next") is True or alice_row.get("sitting_out") is True
            json_response(
                client.post(
                    f"/api/tables/{table_id}/presence",
                    json={"mode": "cancel_sitout"},
                    headers=auth(alice_token),
                )
            )

            json_response(client.post("/api/auth/logout", headers=auth(alice_token)))
            json_response(client.get("/api/me", headers=auth(alice_token)), 401)
            wrong = client.post("/api/auth/pin", json={"name": alice_user["name"], "pin": "999999"})
            assert wrong.status_code == 401
            relogin, _ = login(client, alice_user["name"], "123456")
            assert relogin["created"] is False

    print("JJ_MEMBER_USER_JOURNEY_OK")


if __name__ == "__main__":
    run()
