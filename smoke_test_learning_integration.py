"""Exercise Japanese article sharing through the complete production entrypoint.

All users, sessions, points and runtime files belong to a temporary SQLite app.
External article/video requests are blocked; no production credentials are used.
"""
from __future__ import annotations

import copy
import importlib
import os
import re
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import admin_copy_patch
import runtime_builder


ROOT = Path(__file__).resolve().parent


@contextmanager
def isolated_production_app():
    modules = (
        "app", "server", "db", "poker_engine", "admin_console", "admin_delete",
        "admin_pin_verification", "admin_ledger_stabilization", "learning_content",
        "online_results_cleanup", "hand_analytics", "hand_analytics_hardening",
    )
    previous_modules = {name: sys.modules.pop(name) for name in modules if name in sys.modules}
    previous_path = list(sys.path)
    try:
        with tempfile.TemporaryDirectory(prefix="jj-learning-integration-") as directory:
            work = Path(directory)
            # app.py also normalizes admin copy at startup. Exercise that operation
            # on a copy so a smoke test never edits the repository's static files.
            admin_assets = work / "admin_static"
            shutil.copytree(ROOT / "admin_static", admin_assets)
            apply_admin_copy = admin_copy_patch.apply
            with (
                patch.dict(os.environ, {
                    "DATABASE_URL": "",
                    "JJ_DB_PATH": str(work / "learning.sqlite3"),
                    "JJ_ADMIN_NAME": "ケンイチロウ",
                    "JJ_ADMIN_PIN": "654321",
                    "JJ_ENABLE_DEMO_MEMBER": "0",
                }),
                patch.object(runtime_builder, "DEFAULT_DEST", work / "runtime"),
                patch.object(admin_copy_patch, "apply", side_effect=lambda _: apply_admin_copy(admin_assets)),
            ):
                production = importlib.import_module("app")
                assert production.DEST == work / "runtime"
                assert production.db.DB_PATH == work / "learning.sqlite3"
                assert not production.db.IS_POSTGRES
                yield production
    finally:
        sys.path[:] = previous_path
        for name in modules:
            sys.modules.pop(name, None)
        sys.modules.update(previous_modules)


def json_response(response, status=200):
    assert response.status_code == status, response.text
    assert response.headers.get("content-type", "").startswith("application/json"), response.text
    return response.json()


def login(client, name, pin):
    response = client.post("/api/auth/pin", json={"name": name, "pin": pin})
    payload = json_response(response)
    assert "httponly" in response.headers.get("set-cookie", "").lower()
    assert client.cookies
    return payload["user"]


def ledger_snapshot(db):
    with db.connect() as con:
        return [dict(row) for row in con.execute("SELECT * FROM point_ledger ORDER BY id").fetchall()]


def rankings(client):
    return json_response(client.get("/api/rankings", params={"season": "fall"}))


def assert_japanese_articles(payload):
    assert payload["policy"]["articles"] == "ja-only"
    assert payload["articles"], "Japanese fallback articles must remain available offline"
    for article in payload["articles"]:
        assert article["language"] == "ja", article
        assert re.search(r"[\u3041-\u3096\u30a1-\u30fa]", article["title"]), article
        parsed = urlsplit(article["url"])
        assert parsed.scheme == "https" and parsed.hostname == "japan.gtowizard.com", article
        assert article["title"] != "English poker strategy article", article


def assert_websocket_denied(client, expected_code):
    try:
        with client.websocket_connect(
            "/ws/tables/jj-table-a", headers={"origin": "https://testserver"}
        ) as connection:
            connection.receive_json()
    except WebSocketDisconnect as exc:
        assert exc.code == expected_code, exc
    else:
        raise AssertionError("unauthorized WebSocket was accepted")


def run() -> None:
    with isolated_production_app() as production:
        app, db, content = production.app, production.db, production.learning_content
        # A permanently fresh cache avoids a background worker escaping the test's
        # network mock. Mixed cache data exercises the final API language boundary.
        fallback = content._fallback_payload()
        content._cache = copy.deepcopy(fallback)
        content._expires_at = float("inf")
        content._refreshing = False
        with (
            patch.object(content, "_fetch_bytes", side_effect=AssertionError("external network forbidden")) as fetch,
            TestClient(app, base_url="https://testserver") as member,
            TestClient(app, base_url="https://testserver") as other,
            TestClient(app, base_url="https://testserver") as admin,
            TestClient(app, base_url="https://testserver") as anonymous,
        ):
            # This goes through app.py route ordering and normal cookie auth,
            # catching both missing extension installation and SPA catch-all bugs.
            assert json_response(anonymous.get("/api/health"))["ok"] is True
            json_response(anonymous.get("/api/learning-content"), 401)
            json_response(anonymous.get("/api/quiz/question"), 401)
            assert_websocket_denied(anonymous, 4401)

            user = login(member, "ガクシュウテスト", "123456")
            second = login(other, "ガクシュウベツ", "234567")
            login(admin, "ケンイチロウ", "654321")
            uid = int(user["id"])
            assert uid != int(second["id"])
            json_response(member.get("/api/admin/console/users"), 403)

            before_ledger = ledger_snapshot(db)
            before_rankings = rankings(member)
            before_user = json_response(member.get("/api/me"))
            for _ in range(3):
                assert_japanese_articles(json_response(member.get("/api/learning-content")))

            poisoned = copy.deepcopy(fallback["articles"][0])
            poisoned.update(title="English poker strategy article", language="ja",
                            url="https://japan.gtowizard.com/blog/english-cache/")
            content._cache["articles"].insert(0, poisoned)
            assert_japanese_articles(json_response(member.get("/api/learning-content")))
            assert ledger_snapshot(db) == before_ledger
            assert rankings(member) == before_rankings
            assert json_response(member.get("/api/me")) == before_user

            question = json_response(member.get("/api/quiz/question"))
            assert question == json_response(member.get("/api/quiz/question")), "refresh changed an open question"
            assert question["reward"] == 10
            assert "correct_answer" not in question
            with db.connect() as con:
                attempt = dict(con.execute("SELECT * FROM quiz_attempts WHERE id=?", (question["id"],)).fetchone())
            assert int(attempt["user_id"]) == uid and attempt["answer"] is None
            correct = int(attempt["correct_answer"])
            assert correct in question["choices"]
            answer = {"question_id": question["id"], "answer": correct}

            json_response(other.post("/api/quiz/answer", json=answer), 404)
            invalid = next(value for value in range(101) if value not in question["choices"])
            json_response(member.post("/api/quiz/answer", json={**answer, "answer": invalid}), 400)
            assert ledger_snapshot(db) == before_ledger

            # Keep ranking assertions valid when this test runs after the fixed
            # 2026 fall season; only the ephemeral reward timestamp is pinned.
            with patch.object(db, "utcnow", return_value="2026-09-10T12:00:00+00:00"):
                first = json_response(member.post("/api/quiz/answer", json=answer))
                duplicate = json_response(member.post("/api/quiz/answer", json=answer))
            assert first["correct"] is True and first["awarded"] == 10
            assert first["already_answered"] is False
            assert duplicate["already_answered"] is True and duplicate["awarded"] == 0
            after_ledger = ledger_snapshot(db)
            added = [row for row in after_ledger if row not in before_ledger]
            assert len(added) == 1, added
            assert int(added[0]["user_id"]) == uid
            assert added[0]["kind"] == "quiz_reward" and float(added[0]["amount"]) == 10
            after_rankings = rankings(member)
            ranking_name = user.get("ranking_name") or user["name"]
            prior = next((row for row in before_rankings if row["name"] == ranking_name), {})
            current = next(row for row in after_rankings if row["name"] == ranking_name)
            assert float(current["points"]) == float(prior.get("points", 0)) + 10
            assert float(current["quiz_points"]) == float(prior.get("quiz_points", 0)) + 10
            assert float(current["admin_points"]) == float(prior.get("admin_points", 0))
            assert_japanese_articles(json_response(member.get("/api/learning-content")))
            assert ledger_snapshot(db) == after_ledger
            assert rankings(member) == after_rankings

            # The fully installed article/analytics/admin extensions must preserve
            # the cookie-authenticated WebSocket path and normal account lifecycle.
            with member.websocket_connect(
                "/ws/tables/jj-table-a", headers={"origin": "https://testserver"}
            ) as connection:
                state = connection.receive_json()
                assert state["type"] == "state" and state["state"]["id"] == "jj-table-a"
                connection.send_text("ping")
            json_response(admin.patch(f"/api/admin/console/users/{uid}", json={"disabled": True}))
            with db.connect() as con:
                row = con.execute("SELECT disabled FROM users WHERE id=?", (uid,)).fetchone()
                sessions = con.execute("SELECT COUNT(*) n FROM sessions WHERE user_id=?", (uid,)).fetchone()
            assert int(row["disabled"]) == 1 and int(sessions["n"]) == 0
            json_response(member.get("/api/learning-content"), 401)
            json_response(member.get("/api/quiz/question"), 401)
            assert_websocket_denied(member, 4401)
            json_response(member.post("/api/auth/pin", json={"name": user["name"], "pin": "123456"}), 403)
            assert_japanese_articles(json_response(other.get("/api/learning-content")))
            assert ledger_snapshot(db) == after_ledger
            fetch.assert_not_called()

            # All three wrappers used installer-local request models. Verify
            # actual JSON binding, field validation and tombstone protection.
            second_uid = int(second["id"])
            reset_url = f"/api/admin/console/users/{second_uid}/reset-pin"
            invalid_pin = json_response(admin.post(reset_url, json={"pin": "123"}), 422)
            assert invalid_pin["detail"][0]["loc"][:1] == ["body"]
            json_response(admin.post(reset_url, json={"pin": "345678"}))
            json_response(other.get("/api/me"), 401)
            login(other, second["name"], "345678")
            credit = {"user_id": second_uid, "direction": "credit", "amount": 5,
                      "reason": "回帰テスト", "effective_at": "2026-09-10T12:00:00+00:00"}
            json_response(other.post("/api/admin/console/points", json=credit), 403)
            invalid_credit = json_response(admin.post("/api/admin/console/points", json={**credit, "amount": -1}), 422)
            assert invalid_credit["detail"][0]["loc"][:1] == ["body"]
            transaction = json_response(admin.post("/api/admin/console/points", json=credit))
            assert transaction["amount"] == 5
            reversal = json_response(admin.post(f'/api/admin/console/points/{transaction["id"]}/reverse'))
            assert reversal["amount"] == -5
            json_response(admin.delete(f"/api/admin/console/users/{second_uid}"))
            json_response(admin.patch(f"/api/admin/console/users/{second_uid}", json={"disabled": False}), 404)
            json_response(admin.post(reset_url, json={"pin": "456789"}), 404)
            json_response(admin.post("/api/admin/console/points", json=credit), 404)

    print("JJ_LEARNING_PRODUCTION_INTEGRATION_OK")


if __name__ == "__main__":
    run()
