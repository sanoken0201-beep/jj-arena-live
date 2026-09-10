"""Real HTTP, concurrent transactions, JST rollover and persisted-set regression.

Default: disposable SQLite. --postgres: only the explicitly named local CI DB.
Never connects to a Render/production database.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
import daily_quiz as dq
from smoke_test_learning_integration import isolated_production_app, login, json_response


def bank_checks():
    assert len(dq.POOLS) == 10
    start = datetime(2026, 9, 11)
    seen = {k: set() for k in dq.POOLS}
    for offset in range(16):
        day = (start + timedelta(days=offset)).date().isoformat()
        questions = dq.build_daily_questions(day)
        assert questions == dq.build_daily_questions(day)
        assert len(questions) == 10
        for q in questions:
            assert q['key'] not in seen[q['category']]
            seen[q['category']].add(q['key'])
            choices = q['choices']
            assert len(choices) == len({c['value'] for c in choices}) == 4
            assert len({c['label'] for c in choices}) == 4
            assert q['correct'] in {c['value'] for c in choices}
            assert len(q['explanation']) >= 15
            if all(c['label'].endswith('%') for c in choices):
                values = [float(c['label'][:-1]) for c in choices]
                correct = next(float(c['label'][:-1]) for c in choices if c['value'] == q['correct'])
                assert all(v == correct or abs(v-correct) >= 10 for v in values), q
    assert all(len(v) == 16 for v in seen.values())
    class StatRows:
        def execute(self, _): return self
        def fetchall(self):
            return [dict(question_key=str(n),revision='v1',question_json=json.dumps({'category':'range','prompt':'test'}),attempts=n,correct=c)
                    for n,c in ((29,29),(30,27),(31,9),(32,20))]
    assert [q['assessment'] for q in dq.question_statistics(StatRows())['questions']] == ['insufficient_data','too_easy','too_hard','in_range']


@contextmanager
def test_app(postgres):
    if not postgres:
        with isolated_production_app() as production:
            yield production.app, production.db
        return
    url = os.environ.get('DATABASE_URL', '')
    parsed = urlsplit(url)
    assert parsed.hostname in ('127.0.0.1', 'localhost') and parsed.path == '/jj_arena_ci', 'Only local disposable CI database allowed'
    # Reuse the ordinary runtime adapter, with no destructive database reset.
    import tempfile
    from pathlib import Path
    from runtime_builder import build_runtime
    with tempfile.TemporaryDirectory(prefix='jj-quiz-pg-') as directory:
        runtime = build_runtime(Path(directory)/'runtime')
        sys.path.insert(0, str(runtime))
        import server
        import db
        assert db.IS_POSTGRES
        dq.install(server.app, server, db)
        server.app.router.routes.sort(key=lambda r: not str(getattr(r, 'path', '')).startswith(('/api/quiz/', '/api/admin/console/quiz-stats')))
        yield server.app, db


def run(postgres=False):
    bank_checks()
    with test_app(postgres) as (app, db), patch.object(dq, 'utc_now') as clock:
        clock.return_value = datetime(2026, 9, 11, 14, 59, 59, tzinfo=timezone.utc)
        suffix = uuid.uuid4().hex[:8]
        name_suffix = ''.join('アイウエオカキクケコサシスセソタ'[int(c,16)] for c in suffix)
        with TestClient(app) as a, TestClient(app) as b, TestClient(app) as anon:
            uid = login(a, 'クイズア'+name_suffix, '123456')['id']
            other = login(b, 'クイズイ'+name_suffix, '234567')['id']
            json_response(anon.get('/api/quiz/question'), 401)
            json_response(a.get('/api/admin/console/quiz-stats'), 403)
            json_response(anon.get('/api/admin/console/quiz-stats'), 401)

            def get():
                with TestClient(app) as tab:
                    tab.cookies.update(a.cookies)
                    return json_response(tab.get('/api/quiz/question'))

            with ThreadPoolExecutor(max_workers=8) as pool:
                opened = list(pool.map(lambda _: get(), range(16)))
            q = opened[0]
            assert all(item == q for item in opened)
            assert q['date'] == '2026-09-11' and 'correct' not in q and 'explanation' not in q
            qb = json_response(b.get('/api/quiz/question'))
            assert qb['id'] != q['id'] and qb['prompt'] == q['prompt']
            payload = {'question_id': q['id'], 'answer': q['choices'][0]['value']}
            json_response(b.post('/api/quiz/answer', json=payload), 404)
            json_response(a.post('/api/quiz/answer', json={**payload, 'answer': 'INVALID'}), 400)
            json_response(a.post('/api/quiz/answer', json={**payload, 'question_id': 'dqa-unknown'}), 404)

            # Answer uses its persisted snapshot even after a bank/deployment change.
            def send(_):
                with TestClient(app) as tab:
                    tab.cookies.update(a.cookies)
                    return json_response(tab.post('/api/quiz/answer', json=payload))
            with patch.object(dq, 'build_daily_questions', side_effect=AssertionError('daily set must be persisted')):
                with ThreadPoolExecutor(max_workers=8) as pool:
                    results = list(pool.map(send, range(16)))
                assert sum(r['awarded'] for r in results) == 10
                assert sum(not r['already_answered'] for r in results) == 1
                assert len({r['correct'] for r in results}) == 1
                duplicate = json_response(a.post('/api/quiz/answer', json={**payload, 'answer': q['choices'][1]['value']}))
                assert duplicate['awarded'] == 0 and duplicate['correct'] == results[0]['correct']
                assert duplicate['explanation']
                for number in range(2, 11):
                    q = get()
                    assert q['slot'] == number
                    r = json_response(a.post('/api/quiz/answer', json={'question_id': q['id'], 'answer': q['choices'][0]['value']}))
                    assert r['awarded'] == 10 and r['progress']['earned'] == number*10
                for _ in range(12):
                    assert get()['done'] is True
            with db.connect() as con:
                rows = con.execute("SELECT * FROM point_ledger WHERE user_id=? AND kind='quiz_reward'", (uid,)).fetchall()
                assert len(rows) == 10 and sum(float(r['amount']) for r in rows) == 100
                stats = dq.question_statistics(con)
                assert sum(s['attempts'] for s in stats['questions']) >= 10
                count = con.execute('SELECT COUNT(*) n FROM quiz_daily_answers WHERE user_id=? AND answer IS NOT NULL', (uid,)).fetchone()['n']
                assert count == 10

            # Exact JST midnight: old outstanding answer rejected, new set allowed.
            clock.return_value += timedelta(seconds=1)
            json_response(b.post('/api/quiz/answer', json={'question_id': qb['id'], 'answer': qb['choices'][0]['value']}), 409)
            tomorrow = get()
            assert tomorrow['date'] == '2026-09-12' and tomorrow['progress']['earned'] == 0
            assert tomorrow['id'] != q['id']

            # Rewards earned in the old version count toward deployment-day cap.
            stamp = clock.return_value.isoformat()
            with db.connect() as con:
                con.execute('INSERT INTO point_ledger(id,user_id,amount,kind,reason,effective_at,created_by,created_at,reversal_of) VALUES (?,?,?,?,?,?,?,?,NULL)',
                            ('legacy-'+suffix, other, 80, 'quiz_reward', 'test', stamp, other, stamp))
            for expected in (90, 100):
                qb = json_response(b.get('/api/quiz/question'))
                rb = json_response(b.post('/api/quiz/answer', json={'question_id': qb['id'], 'answer': qb['choices'][0]['value']}))
                assert rb['progress']['earned'] == expected
            assert json_response(b.get('/api/quiz/question'))['done']

            # Fail after inserting the ledger: transaction must roll back both.
            original_connect = db.connect
            class BrokenConnection:
                def __init__(self, con): self.con = con
                def execute(self, sql, args=()):
                    if sql.startswith('UPDATE quiz_daily_answers SET answer='):
                        raise RuntimeError('injected failure')
                    return self.con.execute(sql, args)
            @contextmanager
            def broken():
                with original_connect() as con:
                    yield BrokenConnection(con)
            body = {'question_id': tomorrow['id'], 'answer': tomorrow['choices'][0]['value']}
            with patch.object(db, 'connect', broken):
                try:
                    a.post('/api/quiz/answer', json=body)
                except RuntimeError as exc:
                    assert 'injected failure' in str(exc)
                else:
                    raise AssertionError('failure injection did not run')
            with db.connect() as con:
                assert con.execute('SELECT answer FROM quiz_daily_answers WHERE id=?', (tomorrow['id'],)).fetchone()['answer'] is None
                assert con.execute('SELECT COUNT(*) n FROM point_ledger WHERE id=?', ('dq3-'+tomorrow['id'],)).fetchone()['n'] == 0
            assert json_response(a.post('/api/quiz/answer', json=body))['awarded'] == 10
            # Disable checked under the same lock as reward writes.
            with db.connect() as con:
                con.execute('UPDATE users SET disabled=1 WHERE id=?', (uid,))
            assert a.get('/api/quiz/question').status_code in (401, 403)
    print('JJ_DAILY_QUIZ_POSTGRES_OK' if postgres else 'JJ_DAILY_QUIZ_SQLITE_OK')


if __name__ == '__main__':
    run('--postgres' in sys.argv)
