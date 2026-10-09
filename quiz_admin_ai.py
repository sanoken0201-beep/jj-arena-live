"""Admin-managed daily-quiz question bank with optional OpenAI generation."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from urllib import error as urlerror
from urllib import request as urlrequest

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from quiz_bank import CATEGORY_LABELS, POOLS

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_QUIZ_MODEL = "gpt-6-luna"

# Older admin pages exposed focus labels that are not among the 10 daily quiz buckets.
# Normalize them to existing buckets without changing daily quiz size or rotation.
LEGACY_GPT_CATEGORY_ALIASES = {
    "preflop": "range",
    "board_texture": "hand_reasoning",
    "position": "range",
    "tournament": "icm",
    "rules": "vocabulary",
}


class QuizQuestionIn(BaseModel):
    category: str
    prompt: str = Field(min_length=8, max_length=600)
    choices: list[str] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)
    explanation: str = Field(min_length=15, max_length=1200)
    request_id: str | None = Field(default=None, min_length=8, max_length=120)

    @field_validator("category")
    @classmethod
    def valid_category(cls, value: str) -> str:
        value = value.strip()
        if value not in POOLS:
            raise ValueError("未知のクイズカテゴリです")
        return value

    @field_validator("choices")
    @classmethod
    def valid_choices(cls, values: list[str]) -> list[str]:
        cleaned = [str(value).strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("選択肢を空欄にはできません")
        if len(set(cleaned)) != 4:
            raise ValueError("4つの選択肢は重複できません")
        if any(len(value) > 220 for value in cleaned):
            raise ValueError("選択肢が長すぎます")
        return cleaned


class QuizGPTAddIn(BaseModel):
    topic: str = Field(min_length=3, max_length=500)
    category: str | None = None
    request_id: str | None = Field(default=None, min_length=8, max_length=120)

    @field_validator("category")
    @classmethod
    def valid_category(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = LEGACY_GPT_CATEGORY_ALIASES.get(value.strip(), value.strip())
        if value not in POOLS:
            raise ValueError("未知のクイズカテゴリです")
        return value


class QuizQuestionStatusIn(BaseModel):
    enabled: bool


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_schema(db) -> None:
    uid = "BIGINT" if db.IS_POSTGRES else "INTEGER"
    with db.connect() as con:
        con.execute(f"""CREATE TABLE IF NOT EXISTS quiz_custom_questions(
            id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            question_json TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
            source TEXT NOT NULL,
            source_detail TEXT,
            idempotency_key TEXT UNIQUE,
            created_by {uid} NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL)""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_quiz_custom_enabled ON quiz_custom_questions(enabled,category,created_at)")


def _question_json(question_id: str, payload: QuizQuestionIn) -> dict:
    values = ("a", "b", "c", "d")
    return {
        "key": question_id,
        "category": payload.category,
        "category_label": CATEGORY_LABELS[payload.category],
        "prompt": payload.prompt.strip(),
        "choices": [
            {"value": values[index], "label": label}
            for index, label in enumerate(payload.choices)
        ],
        "correct": values[payload.correct_index],
        "explanation": payload.explanation.strip(),
        "glossary": [],
    }


def _insert_question(con, payload: QuizQuestionIn, uid: int, *, source: str, source_detail: str | None = None) -> dict:
    request_id = payload.request_id or str(uuid.uuid4())
    existing = con.execute(
        "SELECT id,question_json,enabled,source,source_detail,created_at,updated_at FROM quiz_custom_questions WHERE idempotency_key=?",
        (request_id,),
    ).fetchone()
    if existing:
        item = dict(existing)
        item["question"] = json.loads(item.pop("question_json"))
        item["duplicate"] = True
        return item

    question_id = "custom-" + uuid.uuid4().hex
    question = _question_json(question_id, payload)
    stamp = _now()
    con.execute(
        """INSERT INTO quiz_custom_questions(
            id,category,question_json,enabled,source,source_detail,idempotency_key,created_by,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            question_id,
            payload.category,
            json.dumps(question, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            1,
            source,
            source_detail,
            request_id,
            uid,
            stamp,
            stamp,
        ),
    )
    return {
        "id": question_id,
        "question": question,
        "enabled": 1,
        "source": source,
        "source_detail": source_detail,
        "created_at": stamp,
        "updated_at": stamp,
        "duplicate": False,
    }


def _extract_output_text(response: dict) -> str:
    for item in response.get("output") or []:
        if item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if part.get("type") == "output_text" and part.get("text"):
                return str(part["text"])
    raise HTTPException(502, "GPTから問題データを取得できませんでした")


def _generate_question(payload: QuizGPTAddIn) -> QuizQuestionIn:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(503, "OPENAI_API_KEY が設定されていません")
    model = os.getenv("OPENAI_QUIZ_MODEL", DEFAULT_QUIZ_MODEL).strip() or DEFAULT_QUIZ_MODEL
    categories = list(POOLS.keys())
    category_rule = (
        f"カテゴリは必ず {payload.category} にしてください。"
        if payload.category
        else "カテゴリは次のいずれかから最適なものを1つ選んでください: " + ", ".join(categories)
    )
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "category": {"type": "string", "enum": categories},
            "prompt": {"type": "string"},
            "choices": {
                "type": "array",
                "minItems": 4,
                "maxItems": 4,
                "items": {"type": "string"},
            },
            "correct_index": {"type": "integer", "minimum": 0, "maximum": 3},
            "explanation": {"type": "string"},
        },
        "required": ["category", "prompt", "choices", "correct_index", "explanation"],
    }
    body = {
        "model": model,
        "store": False,
        "input": [
            {
                "role": "developer",
                "content": [{
                    "type": "input_text",
                    "text": (
                        "JJ学生ポーカーサークルの今日のクイズ用に、日本語の4択問題を1問作成してください。"
                        "正解は1つだけにし、誤答も同じ領域のもっともらしい選択肢にしてください。"
                        "説明は正解理由が分かる簡潔な内容にしてください。"
                        "曖昧な頻度・GTO値・最新ルールなど、前提なしでは一意に決まらない問題は避けてください。"
                        + category_rule
                    ),
                }],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": payload.topic}],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "jj_daily_quiz_question",
                "strict": True,
                "schema": schema,
            }
        },
        "max_output_tokens": 900,
    }
    req = urlrequest.Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise HTTPException(502, f"GPT問題生成に失敗しました: HTTP {exc.code} {detail}") from exc
    except (urlerror.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HTTPException(502, "GPT問題生成に失敗しました") from exc

    try:
        generated = json.loads(_extract_output_text(result))
        generated["request_id"] = payload.request_id
        return QuizQuestionIn(**generated)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, "GPTが返した問題形式を検証できませんでした") from exc


def install(app, server, db) -> None:
    if getattr(app.state, "jj_quiz_admin_ai_installed", False):
        return
    _ensure_schema(db)

    @app.get("/api/admin/console/quiz/questions", include_in_schema=False)
    def list_questions(user=Depends(server.admin_user)):
        with db.connect() as con:
            rows = con.execute(
                """SELECT id,category,question_json,enabled,source,source_detail,created_by,created_at,updated_at
                   FROM quiz_custom_questions ORDER BY created_at DESC LIMIT 300"""
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["question"] = json.loads(item.pop("question_json"))
            result.append(item)
        return result

    @app.post("/api/admin/console/quiz/questions", include_in_schema=False)
    def add_question(payload: QuizQuestionIn, user=Depends(server.admin_user)):
        with db.connect() as con:
            return _insert_question(con, payload, int(user["id"]), source="admin")

    @app.post("/api/admin/console/quiz/gpt-add", include_in_schema=False)
    def gpt_add_question(payload: QuizGPTAddIn, user=Depends(server.admin_user)):
        generated = _generate_question(payload)
        with db.connect() as con:
            return _insert_question(
                con,
                generated,
                int(user["id"]),
                source="gpt",
                source_detail=os.getenv("OPENAI_QUIZ_MODEL", DEFAULT_QUIZ_MODEL),
            )

    @app.patch("/api/admin/console/quiz/questions/{question_id}", include_in_schema=False)
    def set_question_status(question_id: str, payload: QuizQuestionStatusIn, user=Depends(server.admin_user)):
        stamp = _now()
        with db.connect() as con:
            row = con.execute("SELECT id FROM quiz_custom_questions WHERE id=?", (question_id,)).fetchone()
            if not row:
                raise HTTPException(404, "追加問題が見つかりません")
            con.execute(
                "UPDATE quiz_custom_questions SET enabled=?,updated_at=? WHERE id=?",
                (1 if payload.enabled else 0, stamp, question_id),
            )
        return {"ok": True, "id": question_id, "enabled": bool(payload.enabled), "updated_at": stamp}

    app.state.jj_quiz_admin_ai_installed = True
