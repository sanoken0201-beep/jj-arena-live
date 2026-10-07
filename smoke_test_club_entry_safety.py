from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from smoke_test_learning_integration import isolated_production_app, json_response


def _request_id() -> str:
    return "entry-" + uuid.uuid4().hex


def main() -> None:
    with isolated_production_app() as production:
        with TestClient(production.app, base_url="https://testserver") as client:
            login = json_response(
                client.post("/api/auth/pin", json={"name": "ポイントテスト", "pin": "123456"})
            )
            user = login["user"]
            uid = int(user["id"])
            own_name = str(user["ranking_name"] or user["name"])

            request_id = _request_id()
            payload = {
                "request_id": request_id,
                "name": "ホカノヒト",
                "date": "2026-10-07T18:30",
                "reentries": 0,
                "initial": 450,
                "game_type": "ring",
                "chip_500": 1,
            }
            first = json_response(client.post("/api/member/entries", json=payload))
            replay = json_response(client.post("/api/member/entries", json=payload))
            assert replay["id"] == first["id"]
            assert float(first["points"]) == 50

            with production.db.connect() as con:
                rows = con.execute(
                    "SELECT id,name,points FROM entries WHERE created_by=? ORDER BY created_at",
                    (uid,),
                ).fetchall()
                claims = con.execute(
                    "SELECT request_id,response_json FROM club_entry_requests WHERE actor_id=?",
                    (uid,),
                ).fetchall()
            assert len(rows) == 1
            assert rows[0]["name"] == own_name
            assert float(rows[0]["points"]) == 50
            assert len(claims) == 1 and claims[0]["response_json"]

            changed = dict(payload)
            changed["chip_500"] = 2
            conflict = client.post("/api/member/entries", json=changed)
            assert conflict.status_code == 409, conflict.text

            invalid = dict(payload, request_id=_request_id(), date="2026-09-31T18:30")
            response = client.post("/api/member/entries", json=invalid)
            assert response.status_code == 400, response.text
            assert "実在する日時" in response.text

            excessive = dict(payload, request_id=_request_id(), chip_500=100000)
            response = client.post("/api/member/entries", json=excessive)
            assert response.status_code == 400, response.text
            assert "以内" in response.text

            # The public /api/entries contract remains administrator-only even
            # though the safer replacement route now has precedence.
            forbidden = client.post("/api/entries", json=dict(payload, request_id=_request_id()))
            assert forbidden.status_code in {401, 403}, forbidden.text

            routes = [
                route
                for route in production.app.router.routes
                if getattr(route, "path", None) == "/api/entries"
                and "POST" in (getattr(route, "methods", None) or set())
            ]
            assert routes
            assert getattr(routes[0], "endpoint", None).__name__ == "_safe_admin_point_entry"

    print("JJ_CLUB_ENTRY_SAFETY_OK")


if __name__ == "__main__":
    main()
