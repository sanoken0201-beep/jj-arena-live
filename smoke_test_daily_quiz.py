from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from runtime_builder import build_runtime


def _find_route(app, path: str, method: str):
    matches = [
        route for route in app.router.routes
        if getattr(route, "path", None) == path and method.upper() in (getattr(route, "methods", None) or set())
    ]
    assert len(matches) == 1, (path, method, len(matches))
    return matches[0]


def run() -> None:
    work = Path(tempfile.mkdtemp(prefix="jj-daily-quiz-smoke-"))
    runtime = build_runtime(work / "runtime")
    previous = {k: os.environ.get(k) for k in (
        "DATABASE_URL", "JJ_DB_PATH", "JJ_ADMIN_NAME", "JJ_ADMIN_PIN", "JJ_ENABLE_DEMO_MEMBER"
    )}
    os.environ.pop("DATABASE_URL", None)
    os.environ["JJ_DB_PATH"] = str(work / "quiz.sqlite3")
    os.environ["JJ_ADMIN_NAME"] = "ケンイチロウ"
    os.environ["JJ_ADMIN_PIN"] = "654321"
    os.environ["JJ_ENABLE_DEMO_MEMBER"] = "0"

    old_modules = {}
    for name in ("db", "server", "poker_engine"):
        if name in sys.modules:
            old_modules[name] = sys.modules.pop(name)
    sys.path.insert(0, str(runtime))
    try:
        import db  # type: ignore
        import server  # type: ignore
        import daily_quiz

        # Ten distinct categories every day; every category advances to a new
        # variant on the following JST calendar day.
        day1 = "2026-09-10"
        day2 = "2026-09-11"
        set1 = daily_quiz.build_daily_questions(day1)
        set2 = daily_quiz.build_daily_questions(day2)
        assert len(set1) == 10 and len(set2) == 10
        assert len({q["category"] for q in set1}) == 10
        assert len({q["prompt"] for q in set1}) == 10
        assert [q["key"] for q in set1] != [q["key"] for q in set2]
        assert all(a["key"] != b["key"] for a, b in zip(set1, set2))
        assert all(len(q["choices"]) == 4 for q in set1)
        assert all(len({c["value"] for c in q["choices"]}) == 4 for q in set1)
        assert all(q["correct"] in {c["value"] for c in q["choices"]} for q in set1)

        # The user's concrete complaint is locked in: the 30% pot-odds item
        # uses conceptually different distractors, not 26/28/32-style noise.
        thirty = next(q for q in daily_quiz.POOLS["pot_odds"] if q["key"] == "pot-100-75")
        assert thirty["correct"] == "30"
        assert {c["value"] for c in thirty["choices"]} == {"30", "50", "70", "80"}

        daily_quiz.install(server.app, server, db)
        _find_route(server.app, "/api/quiz/question", "GET")
        _find_route(server.app, "/api/quiz/answer", "POST")

        original_today = daily_quiz.today_jst
        daily_quiz.today_jst = lambda: day1
        try:
            with TestClient(server.app, base_url="https://testserver") as client:
                login = client.post("/api/auth/pin", json={"name": "クイズテスト", "pin": "123456"})
                assert login.status_code == 200, login.text
                uid = int(login.json()["user"]["id"])

                first = client.get("/api/quiz/question")
                assert first.status_code == 200, first.text
                q = first.json()
                assert q["done"] is False
                assert q["date"] == day1
                assert q["progress"]["answered"] == 0
                assert q["progress"]["max_daily_reward"] == 100

                by_id = {item["id"]: item for item in set1}
                assert q["id"] in by_id
                answer = by_id[q["id"]]["correct"]
                r1 = client.post("/api/quiz/answer", json={"question_id": q["id"], "answer": answer})
                assert r1.status_code == 200, r1.text
                body1 = r1.json()
                assert body1["already_answered"] is False
                assert body1["correct"] is True
                assert body1["awarded"] == 10
                assert body1["progress"]["answered"] == 1
                assert body1["progress"]["earned"] == 10

                # Same question, same day: never award again.
                r2 = client.post("/api/quiz/answer", json={"question_id": q["id"], "answer": answer})
                assert r2.status_code == 200, r2.text
                body2 = r2.json()
                assert body2["already_answered"] is True
                assert body2["awarded"] == 0
                assert body2["progress"]["earned"] == 10

                # Finish today's unique ten-question set. Reward is per completed
                # unique question, preserving the existing +10/question rule.
                for _ in range(9):
                    nxt = client.get("/api/quiz/question")
                    assert nxt.status_code == 200, nxt.text
                    item = nxt.json()
                    assert item["done"] is False
                    source = by_id[item["id"]]
                    # Alternate correct and incorrect answers to prove reward and
                    # duplicate protection are independent of score.
                    if int(item["slot"]) % 2:
                        chosen = source["correct"]
                    else:
                        chosen = next(c["value"] for c in source["choices"] if c["value"] != source["correct"])
                    answered = client.post("/api/quiz/answer", json={"question_id": item["id"], "answer": chosen})
                    assert answered.status_code == 200, answered.text
                    assert answered.json()["awarded"] == 10

                done = client.get("/api/quiz/question")
                assert done.status_code == 200, done.text
                finished = done.json()
                assert finished["done"] is True
                assert finished["progress"]["answered"] == 10
                assert finished["progress"]["earned"] == 100
                assert finished["progress"]["remaining"] == 0

                # Refreshing after completion cannot mint an 11th question or
                # an 11th reward on the same JST date.
                done_again = client.get("/api/quiz/question").json()
                assert done_again["done"] is True
                assert done_again["progress"]["earned"] == 100
                with db.connect() as con:
                    attempts = con.execute(
                        "SELECT COUNT(*) AS c,SUM(reward_awarded) AS total FROM daily_quiz_attempts WHERE user_id=? AND quiz_date=?",
                        (uid, day1),
                    ).fetchone()
                    ledger = con.execute(
                        "SELECT COUNT(*) AS c,COALESCE(SUM(amount),0) AS total FROM point_ledger WHERE user_id=? AND kind='quiz_reward' AND id LIKE ?",
                        (uid, f"quiz-v2-{uid}-{day1}-%"),
                    ).fetchone()
                assert int(attempts["c"]) == 10 and int(attempts["total"]) == 100
                assert int(ledger["c"]) == 10 and int(ledger["total"]) == 100

                # At JST midnight the server switches to a different set and a
                # fresh daily reward allowance. Yesterday's question id is stale.
                daily_quiz.today_jst = lambda: day2
                tomorrow = client.get("/api/quiz/question")
                assert tomorrow.status_code == 200, tomorrow.text
                tq = tomorrow.json()
                assert tq["done"] is False and tq["date"] == day2
                assert tq["progress"]["answered"] == 0 and tq["progress"]["earned"] == 0
                stale = client.post("/api/quiz/answer", json={"question_id": q["id"], "answer": answer})
                assert stale.status_code == 409
        finally:
            daily_quiz.today_jst = original_today

        print("JJ_DAILY_QUIZ_SMOKE_OK")
    finally:
        if str(runtime) in sys.path:
            sys.path.remove(str(runtime))
        for name in ("db", "server", "poker_engine"):
            sys.modules.pop(name, None)
        sys.modules.update(old_modules)
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    run()
