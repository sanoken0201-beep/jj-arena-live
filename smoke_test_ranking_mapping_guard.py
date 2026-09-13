from __future__ import annotations

from fastapi.testclient import TestClient

from smoke_test_learning_integration import isolated_production_app, json_response


MAPPING = "ランキングキョウツウ"
UNIQUE_A = "ランキングエー"


def _login(client: TestClient, name: str, pin: str) -> dict:
    return json_response(client.post("/api/auth/pin", json={"name": name, "pin": pin}))["user"]


def _patch(client: TestClient, uid: int, payload: dict, status: int = 200):
    response = client.patch(f"/api/admin/console/users/{uid}", json=payload)
    if response.status_code != status:
        raise AssertionError(f"PATCH user expected {status}, got {response.status_code}: {response.text}")
    return response.json()


def main() -> None:
    with isolated_production_app() as production:
        with TestClient(production.app, base_url="https://testserver") as client:
            first = _login(client, "ランキングイチ", "111111")
            second = _login(client, "ランキングニ", "222222")
            first_id = int(first["id"])
            second_id = int(second["id"])
            _login(client, "ケンイチロウ", "654321")

            _patch(client, first_id, {"ranking_name": MAPPING})
            conflict = client.patch(
                f"/api/admin/console/users/{second_id}",
                json={"ranking_name": MAPPING},
            )
            assert conflict.status_code == 409, conflict.text
            assert MAPPING in conflict.text

            # A disabled mapping can be prepared without affecting the live
            # ranking; the conflict is enforced when it would become active.
            _patch(client, first_id, {"disabled": True})
            _patch(client, second_id, {"ranking_name": MAPPING})
            reenable = client.patch(
                f"/api/admin/console/users/{first_id}",
                json={"disabled": False},
            )
            assert reenable.status_code == 409, reenable.text

            _patch(client, first_id, {"ranking_name": UNIQUE_A})
            _patch(client, first_id, {"disabled": False})

            # Historical/pre-existing duplicates must remain administratively
            # recoverable. Unrelated edits and disabling one side are allowed.
            with production.db.connect() as con:
                con.execute("UPDATE users SET ranking_name=? WHERE id=?", (UNIQUE_A, second_id))
            overview = json_response(client.get("/api/admin/console/overview"))
            duplicates = {str(row["ranking_name"]): int(row["n"]) for row in overview["duplicate_mappings"]}
            assert duplicates.get(UNIQUE_A) == 2

            _patch(client, first_id, {"admin_note": "重複整理中"})
            _patch(client, first_id, {"disabled": True})
            overview = json_response(client.get("/api/admin/console/overview"))
            duplicates = {str(row["ranking_name"]): int(row["n"]) for row in overview["duplicate_mappings"]}
            assert UNIQUE_A not in duplicates

    print("JJ_RANKING_MAPPING_GUARD_OK")


if __name__ == "__main__":
    main()
