"""Admin/GPT quiz-bank regression without external OpenAI traffic."""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

import daily_quiz as dq
from quiz_admin_ai import QuizQuestionIn
from smoke_test_learning_integration import isolated_production_app, json_response, login


def run() -> None:
    with isolated_production_app() as production:
        app, db = production.app, production.db
        import quiz_admin_ai as qa

        with (
            TestClient(app, base_url="https://testserver") as admin,
            TestClient(app, base_url="https://testserver") as member,
            TestClient(app, base_url="https://testserver") as anonymous,
        ):
            login(admin, "ケンイチロウ", "654321")
            login(member, "クイズツイカ", "123456")

            json_response(anonymous.get("/api/admin/console/quiz/questions"), 401)
            json_response(member.get("/api/admin/console/quiz/questions"), 403)

            payload = {
                "category": "hand_reasoning",
                "prompt": "リバーでブラフキャッチャーをコールする判断で、中心になる比較はどれですか？",
                "choices": [
                    "相手のブラフ比率と自分のポットオッズ",
                    "自分のハンドの絶対的な役名だけ",
                    "直前のハンドで勝ったかどうか",
                    "プリフロップの参加人数だけ",
                ],
                "correct_index": 0,
                "explanation": "ブラフキャッチャーは相手のバリューに負け、ブラフに勝つため、相手のブラフ比率とコールに必要な勝率を比較します。",
                "request_id": "quiz-admin-test-0001",
            }
            created = json_response(admin.post("/api/admin/console/quiz/questions", json=payload))
            assert created["source"] == "admin" and created["duplicate"] is False
            assert created["question"]["correct"] == "a"
            duplicate = json_response(admin.post("/api/admin/console/quiz/questions", json=payload))
            assert duplicate["id"] == created["id"] and duplicate["duplicate"] is True

            rows = json_response(admin.get("/api/admin/console/quiz/questions"))
            assert any(row["id"] == created["id"] for row in rows)

            with db.connect() as con:
                extras = dq._custom_questions(con)
            assert any(question["key"] == created["id"] for question in extras)

            # A custom question is eligible for future, not-yet-persisted daily sets.
            start = date(2026, 10, 6)
            seen = False
            for offset in range(40):
                questions = dq.build_daily_questions((start + timedelta(days=offset)).isoformat(), extras)
                if any(question["key"] == created["id"] for question in questions):
                    seen = True
                    break
            assert seen, "custom question never entered the daily rotation"

            generated = QuizQuestionIn(
                category="equity",
                prompt="必要勝率を考えるとき、最初に比較するべきものはどれですか？",
                choices=["コール額とコール後の総ポット", "カードの色", "前回の勝敗", "席番号"],
                correct_index=0,
                explanation="コールの採算は、支払うコール額とコール後に獲得できる総ポットから必要勝率を求めて評価します。",
                request_id="quiz-gpt-test-0001",
            )
            with patch.object(qa, "_generate_question", return_value=generated) as mocked:
                gpt = json_response(admin.post(
                    "/api/admin/console/quiz/gpt-add",
                    json={"topic": "ポットオッズの基礎", "category": "equity", "request_id": "quiz-gpt-test-0001"},
                ))
            mocked.assert_called_once()
            assert gpt["source"] == "gpt" and gpt["question"]["category"] == "equity"


            # Regression: the previous admin UI sent preflop, which previously returned HTTP 422.
            legacy_generated = QuizQuestionIn(
                category="range",
                prompt="プリフロップで3ベットにコールする場合、最初に検討すべき条件は何ですか？",
                choices=["レンジとポジションおよび実効スタック", "直前の勝敗のみ", "ハンド名の文字数", "席の番号だけ"],
                correct_index=0,
                explanation="コールの収益性は相手の3ベットレンジやポジション、実効スタックなどの条件によって変わります。",
                request_id="quiz-gpt-test-preflop",
            )
            with patch.object(qa, "_generate_question", return_value=legacy_generated) as mocked:
                legacy = json_response(admin.post(
                    "/api/admin/console/quiz/gpt-add",
                    json={"topic": "3ベットへのコールがダメな理由", "category": "preflop", "request_id": "quiz-gpt-test-preflop"},
                ))
            assert mocked.call_args.args[0].category == "range"
            assert legacy["question"]["category"] == "range" and legacy["source"] == "gpt"

            disabled = json_response(admin.patch(
                f"/api/admin/console/quiz/questions/{created['id']}",
                json={"enabled": False},
            ))
            assert disabled["enabled"] is False
            with db.connect() as con:
                active = dq._custom_questions(con)
            assert all(question["key"] != created["id"] for question in active)

    print("JJ_QUIZ_ADMIN_AI_OK")


if __name__ == "__main__":
    run()
