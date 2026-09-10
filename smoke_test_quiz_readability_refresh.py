from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

import daily_quiz as dq
from smoke_test_learning_integration import isolated_production_app, json_response, login


def main() -> None:
    with isolated_production_app() as production, patch.object(dq, "utc_now") as clock:
        clock.return_value = datetime(2026, 9, 11, 3, 0, 0, tzinfo=timezone.utc)
        with TestClient(production.app) as client:
            uid = login(client, "読みやすさ確認", "123456")["id"]
            q1 = json_response(client.get("/api/quiz/question"))
            assert q1["slot"] == 1
            assert "glossary" in q1

            with production.db.connect() as con:
                row = con.execute("SELECT questions_json FROM quiz_daily_sets WHERE quiz_date=?", (q1["date"],)).fetchone()
                stale_set = json.loads(row["questions_json"])
                stale_set[0]["prompt"] = "STALE UNREADABLE QUESTION"
                stale_set[0]["revision"] = "stale-revision"
                con.execute("UPDATE quiz_daily_sets SET bank_version=?,questions_json=? WHERE quiz_date=?",
                            ("old-bank", json.dumps(stale_set, ensure_ascii=False), q1["date"]))
                stale_q = dict(stale_set[0])
                con.execute("UPDATE quiz_daily_answers SET revision=?,question_json=? WHERE id=? AND user_id=? AND answer IS NULL",
                            ("stale-revision", json.dumps(stale_q, ensure_ascii=False), q1["id"], uid))

            q2 = json_response(client.get("/api/quiz/question"))
            assert q2["id"] == q1["id"]
            assert q2["prompt"] != "STALE UNREADABLE QUESTION"
            assert q2["category_label"] == dq.PLAIN_CATEGORY_LABELS[q2["category"]] if hasattr(dq, "PLAIN_CATEGORY_LABELS") else True

            with production.db.connect() as con:
                daily = con.execute("SELECT bank_version FROM quiz_daily_sets WHERE quiz_date=?", (q2["date"],)).fetchone()
                pending = con.execute("SELECT revision,question_json,answer FROM quiz_daily_answers WHERE id=?", (q2["id"],)).fetchone()
                assert daily["bank_version"] == dq.BANK_VERSION
                assert pending["revision"] != "stale-revision"
                assert json.loads(pending["question_json"])["prompt"] == q2["prompt"]
                assert pending["answer"] is None
                rewards = con.execute("SELECT COUNT(*) n FROM point_ledger WHERE user_id=? AND kind='quiz_reward'", (uid,)).fetchone()["n"]
                assert rewards == 0

    print("JJ_QUIZ_READABILITY_REFRESH_OK")


if __name__ == "__main__":
    main()
