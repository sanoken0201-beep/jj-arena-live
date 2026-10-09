from __future__ import annotations

import uuid
from unittest.mock import patch

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

            # Failure after the entry INSERT must roll back the entry and the
            # request claim together. A retry can then settle exactly once.
            failed_id = _request_id()
            atomic_payload = dict(payload, request_id=failed_id, chip_500=2)
            input_model = production._SafePointEntry(**atomic_payload)
            safety = production.club_entry_safety
            original_writer = safety._record_entry

            def abort_after_insert(con, db, core, actor):
                original_writer(con, db, core, actor)
                raise RuntimeError("simulated crash after entry write")

            with patch.object(safety, "_record_entry", side_effect=abort_after_insert):
                try:
                    safety.apply_entry(
                        production.db, production.runtime_server,
                        input_model, user, forced_name=own_name,
                    )
                except RuntimeError as exc:
                    assert "simulated crash" in str(exc)
                else:
                    raise AssertionError("injected entry write should fail")
            with production.db.connect() as con:
                count_after_failure = con.execute(
                    "SELECT COUNT(*) n FROM entries WHERE created_by=?", (uid,),
                ).fetchone()["n"]
                partial_receipt = con.execute(
                    "SELECT request_id FROM club_entry_requests WHERE actor_id=? AND request_id=?",
                    (uid, failed_id),
                ).fetchone()
            assert count_after_failure == 1, "failed atomic entry leaked into official results"
            assert partial_receipt is None, "failed entry stranded an idempotency receipt"
            settled_after_retry = json_response(client.post("/api/member/entries", json=atomic_payload))
            assert settled_after_retry["points"] == 550
            assert json_response(client.post("/api/member/entries", json=atomic_payload))["id"] == settled_after_retry["id"]
            with production.db.connect() as con:
                assert con.execute(
                    "SELECT COUNT(*) n FROM entries WHERE created_by=?", (uid,),
                ).fetchone()["n"] == 2

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
