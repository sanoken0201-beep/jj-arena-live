"""Server-owned JST daily sets, atomic rewards and first-answer analytics."""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from quiz_bank import POOLS

JST = ZoneInfo("Asia/Tokyo")
DAILY_QUIZ_SIZE = 10
DAILY_QUIZ_REWARD = 10
BANK_VERSION = "2026-09-11-v1"
MIN_STAT_SAMPLES = 30


class DailyQuizAnswerIn(BaseModel):
    question_id: str = Field(min_length=8, max_length=120)
    answer: str = Field(min_length=1, max_length=80)


def utc_now():
    return datetime.now(timezone.utc)


def today_jst():
    return utc_now().astimezone(JST).date().isoformat()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_daily_questions(day):
    ordinal = date.fromisoformat(day).toordinal()
    questions = []
    for slot, (category, pool) in enumerate(POOLS.items(), 1):
        # A fixed permutation avoids immediate repeats across cycle boundaries.
        # Each category visits every item once before repeating it.
        ordered = sorted(pool, key=lambda q: hashlib.sha256((category + q["key"]).encode()).hexdigest())
        q = copy.deepcopy(ordered[ordinal % len(ordered)])
        q["revision"] = hashlib.sha256(_json(q).encode()).hexdigest()[:16]
        # Do not expose authoring labels (e.g. 'a') that could identify the key.
        values = {c['value']: hashlib.sha256(f'{day}:{q["key"]}:{c["value"]}'.encode()).hexdigest()[:12] for c in q['choices']}
        q['correct'] = values[q['correct']]
        for choice in q['choices']:
            choice['value'] = values[choice['value']]
        q["choices"].sort(key=lambda c: hashlib.sha256(f'{day}:{q["key"]}:{c["value"]}'.encode()).hexdigest())
        q["slot"] = slot
        questions.append(q)
    return questions


def _ensure_schema(db):
    uid = "BIGINT" if db.IS_POSTGRES else "INTEGER"
    with db.connect() as con:
        con.execute("CREATE TABLE IF NOT EXISTS quiz_daily_sets(quiz_date TEXT PRIMARY KEY, bank_version TEXT NOT NULL, questions_json TEXT NOT NULL)")
        con.execute(f"""CREATE TABLE IF NOT EXISTS quiz_daily_answers(
            id TEXT PRIMARY KEY, user_id {uid} NOT NULL REFERENCES users(id),
            quiz_date TEXT NOT NULL REFERENCES quiz_daily_sets(quiz_date),
            slot INTEGER NOT NULL CHECK(slot BETWEEN 1 AND 10),
            question_key TEXT NOT NULL, revision TEXT NOT NULL, question_json TEXT NOT NULL,
            answer TEXT, is_correct INTEGER CHECK(is_correct IN (0,1)),
            reward_awarded INTEGER NOT NULL DEFAULT 0 CHECK(reward_awarded IN (0,10)),
            created_at TEXT NOT NULL, answered_at TEXT,
            UNIQUE(user_id,quiz_date,slot), UNIQUE(user_id,quiz_date,question_key))""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_quiz_daily_stats ON quiz_daily_answers(question_key,revision)")


def _lock_user(con, db, uid):
    if not db.IS_POSTGRES:
        con.execute("BEGIN IMMEDIATE")
    suffix = " FOR UPDATE" if db.IS_POSTGRES else ""
    row = con.execute("SELECT id,disabled FROM users WHERE id=?" + suffix, (uid,)).fetchone()
    if not row or row["disabled"]:
        raise HTTPException(403, "このアカウントは利用できません")


def _daily_set(con, day):
    row = con.execute("SELECT questions_json FROM quiz_daily_sets WHERE quiz_date=?", (day,)).fetchone()
    if not row:
        con.execute("INSERT INTO quiz_daily_sets(quiz_date,bank_version,questions_json) VALUES (?,?,?) ON CONFLICT(quiz_date) DO NOTHING",
                    (day, BANK_VERSION, _json(build_daily_questions(day))))
        row = con.execute("SELECT questions_json FROM quiz_daily_sets WHERE quiz_date=?", (day,)).fetchone()
    return json.loads(row["questions_json"])


def _progress(con, uid, day):
    start = datetime.combine(date.fromisoformat(day), time(), JST).astimezone(timezone.utc)
    end = start + timedelta(days=1)
    # Include rewards issued by the old implementation on deployment day. Existing
    # points are never removed, but switching versions cannot open another 100pt.
    legacy = con.execute("""SELECT COALESCE(SUM(amount),0) earned FROM point_ledger
        WHERE user_id=? AND kind='quiz_reward' AND amount>0 AND id NOT LIKE ?
        AND effective_at>=? AND effective_at<?""", (uid, 'dq3-%', start.isoformat(), end.isoformat())).fetchone()
    carried = max(0, float(legacy["earned"]))
    row = con.execute("""SELECT COUNT(*) answered, COALESCE(SUM(is_correct),0) correct,
        COALESCE(SUM(reward_awarded),0) earned FROM quiz_daily_answers
        WHERE user_id=? AND quiz_date=? AND answer IS NOT NULL""", (uid, day)).fetchone()
    carried_answers = min(10, int((carried + 9) // 10))
    answered = min(10, carried_answers + int(row["answered"]))
    return dict(answered=answered, correct=int(row["correct"]), earned=carried + int(row["earned"]),
                remaining=max(0, 10-answered), total=10, max_daily_reward=100,
                carried_answers=carried_answers)


def _public(q, uid, day, progress):
    identifier = "dqa-" + hashlib.sha256(f'{uid}:{day}:{q["slot"]}'.encode()).hexdigest()[:32]
    return dict(id=identifier, date=day, slot=q["slot"], category=q["category"],
                category_label=q["category_label"], prompt=q["prompt"], choices=q["choices"],
                reward=10, progress=progress, done=False)


def _result(row, q, progress, duplicate):
    return dict(ok=True, already_answered=duplicate, correct=bool(row["is_correct"]),
                correct_answer=q["correct"], correct_label=next(c["label"] for c in q["choices"] if c["value"]==q["correct"]),
                explanation=q["explanation"], awarded=0 if duplicate else 10, progress=progress)


def question_statistics(con):
    rows = con.execute("""SELECT question_key,revision,question_json,COUNT(*) attempts,
        SUM(is_correct) correct FROM quiz_daily_answers WHERE answer IS NOT NULL
        GROUP BY question_key,revision,question_json ORDER BY question_key,revision""").fetchall()
    # Different choice permutations share the same content revision. Merge them.
    combined = {}
    for row in rows:
        q = json.loads(row["question_json"])
        key = (row["question_key"], row["revision"])
        item = combined.setdefault(key, dict(question_key=key[0],revision=key[1],category=q["category"],
                                            prompt=q["prompt"],attempts=0,correct=0))
        item["attempts"] += int(row["attempts"])
        item["correct"] += int(row["correct"])
    for item in combined.values():
        n = item["attempts"]
        rate = item["correct"] / n
        item["accuracy"] = round(rate, 4)
        item["assessment"] = ("insufficient_data" if n < MIN_STAT_SAMPLES else
                              "too_easy" if rate >= .9 else "too_hard" if rate <= .3 else "in_range")
    return dict(min_samples=MIN_STAT_SAMPLES, easy_threshold=.9, hard_threshold=.3,
                questions=list(combined.values()))


def install(app, server, db):
    if getattr(app.state, "jj_daily_quiz_installed", False):
        return
    _ensure_schema(db)
    retired = {"/api/quiz/question", "/api/quiz/answer"}
    app.router.routes[:] = [r for r in app.router.routes if getattr(r,"path",None) not in retired]

    @app.get("/api/quiz/question", include_in_schema=False)
    def question(user=Depends(server.current_user)):
        uid = int(user["id"])
        with db.connect() as con:
            _lock_user(con, db, uid)
            day = today_jst()  # Decide the day after any lock wait.
            questions = _daily_set(con, day)
            progress = _progress(con, uid, day)
            if not progress["remaining"] or progress["earned"] + 10 > 100:
                return dict(done=True,date=day,progress=progress,reward=10)
            rows = con.execute("SELECT slot,answer FROM quiz_daily_answers WHERE user_id=? AND quiz_date=?",(uid,day)).fetchall()
            answered = {int(r["slot"]) for r in rows if r["answer"] is not None}
            # Preserve an outstanding question when another tab refreshes.
            pending = [int(r["slot"]) for r in rows if r["answer"] is None]
            slot = min(pending) if pending else next(i for i in range(1,11) if i not in answered)
            q = questions[slot-1]
            public = _public(q,uid,day,progress)
            con.execute("""INSERT INTO quiz_daily_answers(id,user_id,quiz_date,slot,question_key,revision,question_json,created_at)
                VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(user_id,quiz_date,slot) DO NOTHING""",
                (public["id"],uid,day,slot,q["key"],q["revision"],_json(q),utc_now().isoformat()))
            return public

    @app.post("/api/quiz/answer", include_in_schema=False)
    def answer(payload: DailyQuizAnswerIn, user=Depends(server.current_user)):
        uid = int(user["id"])
        with db.connect() as con:
            _lock_user(con, db, uid)
            now = utc_now()
            day = now.astimezone(JST).date().isoformat()
            row = con.execute("SELECT * FROM quiz_daily_answers WHERE id=? AND user_id=?",(payload.question_id,uid)).fetchone()
            if not row:
                raise HTTPException(404,"この問題は開始されていません。今日の問題を読み直してください")
            if row["quiz_date"] != day:
                raise HTTPException(409,"日本時間の日付が変わりました。今日の問題を読み直してください")
            q = json.loads(row["question_json"])
            if payload.answer not in {c["value"] for c in q["choices"]}:
                raise HTTPException(400,"選択肢にない回答です")
            progress = _progress(con,uid,day)
            if row["answer"] is not None:
                return _result(row,q,progress,True)
            if not progress["remaining"] or progress["earned"] + 10 > 100:
                raise HTTPException(409,"本日の上限に達しました。今日の問題を読み直してください")
            # The user row lock serializes tabs/processes; constraints and a unique
            # ledger ID also protect against retries. Both writes commit together.
            con.execute("""INSERT INTO point_ledger(id,user_id,amount,kind,reason,effective_at,created_by,created_at,reversal_of)
                VALUES (?,?,?,?,?,?,?,?,NULL)""", ("dq3-"+row["id"],uid,10,"quiz_reward",f'今日のクイズ {day} #{row["slot"]}',now.isoformat(),uid,now.isoformat()))
            con.execute("""UPDATE quiz_daily_answers SET answer=?,is_correct=?,reward_awarded=10,answered_at=?
                WHERE id=? AND answer IS NULL""",(payload.answer,int(payload.answer==q["correct"]),now.isoformat(),row["id"]))
            updated = dict(row,answer=payload.answer,is_correct=int(payload.answer==q["correct"]))
            return _result(updated,q,_progress(con,uid,day),False)

    @app.get("/api/admin/console/quiz-stats", include_in_schema=False)
    def statistics(user=Depends(server.admin_user)):
        with db.connect() as con:
            return question_statistics(con)

    app.state.jj_daily_quiz_installed = True
