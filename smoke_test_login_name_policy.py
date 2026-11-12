"""End-to-end PIN-registration regression for hiragana, katakana and Latin names."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient


def run() -> None:
    with tempfile.TemporaryDirectory(prefix="jj-script-names-") as temp:
        os.environ.pop("DATABASE_URL", None)
        os.environ["JJ_DB_PATH"] = str(Path(temp) / "names.db")
        os.environ["RENDER"] = "1"
        os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"
        os.environ.pop("JJ_ADMIN_PIN", None)

        import app

        def pin(client: TestClient, name: str, secret: str = "123456"):
            return client.post("/api/auth/pin", json={"name": name, "pin": secret})

        with TestClient(app.app, base_url="https://testserver") as client:
            # Existing katakana accounts must still accept hiragana at login.
            katakana = pin(client, "コバヤシ")
            assert katakana.status_code == 200, katakana.text
            assert katakana.json()["created"] is True
            old_id = katakana.json()["user"]["id"]
            alias = pin(client, "こばやし")
            assert alias.status_code == 200, alias.text
            assert alias.json()["user"]["id"] == old_id
            assert alias.json()["created"] is False

            # New hiragana spellings stay as entered in the account profile.
            hiragana = pin(client, "はるのかぜ")
            assert hiragana.status_code == 200, hiragana.text
            assert hiragana.json()["created"] is True
            assert hiragana.json()["user"]["name"] == "はるのかぜ"
            hiragana_id = hiragana.json()["user"]["id"]
            alias = pin(client, "ハルノカゼ")
            assert alias.status_code == 200, alias.text
            assert alias.json()["user"]["id"] == hiragana_id
            assert alias.json()["created"] is False

            # Latin names preserve their spelling but login ignores case.
            latin = pin(client, "TestPlayer")
            assert latin.status_code == 200, latin.text
            assert latin.json()["created"] is True
            assert latin.json()["user"]["name"] == "TestPlayer"
            latin_id = latin.json()["user"]["id"]
            for alternative in ("testplayer", "ＴｅｓｔＰｌａｙｅｒ"):
                alias = pin(client, alternative)
                assert alias.status_code == 200, alias.text
                assert alias.json()["user"]["id"] == latin_id
                assert alias.json()["created"] is False

            mixed = pin(client, "みかんAlpha")
            assert mixed.status_code == 200, mixed.text
            assert mixed.json()["user"]["name"] == "みかんAlpha"
            mixed_alias = pin(client, "ミカンalpha")
            assert mixed_alias.status_code == 200, mixed_alias.text
            assert mixed_alias.json()["user"]["id"] == mixed.json()["user"]["id"]

            # A variant with the wrong PIN must not create a second identity.
            bad_pin = pin(client, "テストプレイヤー", "234567")
            assert bad_pin.status_code == 200, bad_pin.text  # distinct name
            wrong = pin(client, "はるのかぜ", "999999")
            assert wrong.status_code == 401, wrong.text
            with app.db.connect() as con:
                rows = con.execute(
                    "SELECT name FROM users WHERE id IN (?, ?, ?)",
                    (old_id, hiragana_id, latin_id),
                ).fetchall()
            assert {row["name"] for row in rows} == {"コバヤシ", "はるのかぜ", "TestPlayer"}

            # Reject unsupported symbols, kanji, emoji and out-of-range names.
            for invalid in ("A", "山田", "🙂🙂", "John!", "a" * 21, "ab\u200b"):
                response = pin(client, invalid)
                assert response.status_code == 400, (invalid, response.text)

        html = app._patched_index()
        assert "名前（ひらがな・カタカナ・英字）" in html
        assert "カタカナへ自動統一されます" not in html

    print("JJ_MULTI_SCRIPT_LOGIN_OK")


if __name__ == "__main__":
    run()
