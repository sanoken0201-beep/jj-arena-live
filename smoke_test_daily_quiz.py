"""Real HTTP, concurrent transactions, JST rollover and persisted-set regression.

Default: disposable SQLite. --postgres: only the explicitly named local CI DB.
Never connects to a Render/production database.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
import daily_quiz as dq
from quiz_readability import audit_questions, make_readable
from smoke_test_learning_integration import isolated_production_app, login, json_response


def bank_checks():
    # Keep the operator's read-only SQL audit in sync with both current
    # reward amounts and historical 10pt-only daily sets.
    audit_sql = (Path(__file__).resolve().parent / "ops" / "point_integrity_audit.sql").read_text(encoding="utf-8")
    assert "kind='quiz_reward' AND amount NOT IN (5,10)" in audit_sql
    assert "q.reward_awarded NOT IN (5,10)" in audit_sql
    assert "l.amount<>q.reward_awarded" in audit_sql
    assert len(dq.POOLS) == 10
    assert all(len(pool) == 30 for pool in dq.POOLS.values())
    assert len({q['key'] for pool in dq.POOLS.values() for q in pool}) == 300
    readability_errors = audit_questions(dq.POOLS)
    assert not readability_errors, readability_errors
    start = datetime(2026, 9, 11)
    seen = {k: set() for k in dq.POOLS}
    for offset in range(30):
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
    assert all(len(v) == 30 for v in seen.values())
    # Reference examples: regression on independently checked poker arithmetic.
    answer_labels = {
        "pot_odds-multiway-price": "14%",
        "pot_odds-tie-share": "30%",
        "equity-weighted-two-hands": "50%",
        "equity-flop-two-outs": "35%",
        "mdf-quarter-pot": "80%",
        "mdf-bluff-ev": "25",
        "spr-half-spr": "0.5",
        "spr-after-bet-call": "1.3",
        "combo-a5s-different-block": "2コンボ",
        "combo-a5s-same-block": "3コンボ",
        "icm-heads-up-payout": "55",
        "bet_sizing-bluff-break-even": "43%",
        "hand_reasoning-river-indifference": "フォールドと同じ0です",
    }
    questions = {q["key"]: q for pool in dq.POOLS.values() for q in pool}
    for key, expected in answer_labels.items():
        q = questions[key]
        assert next(c["label"] for c in q["choices"] if c["value"] == q["correct"]) == expected
        readable = make_readable(q)
        assert "ベット持ちうる手札の候補" not in readable["prompt"]
        assert "こと勝率" not in readable["prompt"]
        assert len(readable["prompt"]) < 250
    spr_numeric = make_readable(questions["spr-3600-1200"])["prompt"]
    assert "ポットは1,200" in spr_numeric and "残りチップは3,600" in spr_numeric
    for key, phrase in {
        "pot-100-75": "必要な最低勝率",
        "mdf-100-50": "最低ディフェンス頻度（MDF）",
        "spr-3600-1200": "残りチップ÷ポット（SPR）",
        "decision-30-35": "最も適切な判断はどれですか",
    }.items():
        assert phrase in make_readable(questions[key])["prompt"], key

    advanced = [q for pool in dq.POOLS.values() for q in pool if '-advanced-' in q['key']]
    assert len(advanced) == 30
    assert all(q['prompt'].startswith('【応用】') for q in advanced)
    assert all(q['source_url'].startswith('https://blog.gtowizard.com/') for q in advanced)
    assert len({q['key'] for q in advanced}) == len(advanced)
    for q in advanced:
        readable = make_readable(q)
        assert readable['source_url'] == q['source_url']
        assert len(readable['prompt']) <= 250, q['key']
        assert len(readable['choices']) == 4
        assert len({c['label'] for c in readable['choices']}) == 4
    # Protect source-derived numerical examples.
    known_answers = {
        'pot_odds-advanced-raise-pot-25': '25%',
        'equity-advanced-eqr-calc': '60',
        'mdf-advanced-mdf-overbet': '40%',
        'spr-advanced-geom-pot-pot': '毎回100%ポット',
        'spr-advanced-geom-ratio': '62%',
        'combo-advanced-weighted-groups': '75%',
        'icm-advanced-bf-ratio': '1.5',
        'icm-advanced-bf-equity': '60%',
        'bet_sizing-advanced-polar-river-bluffs': '6コンボ',
        'bet_sizing-advanced-triple-barrel-fold': '72%',
        'range-advanced-betting-weight': '67%',
    }
    for key, label in known_answers.items():
        q = next(q for q in advanced if q['key'] == key)
        assert next(c['label'] for c in q['choices'] if c['value'] == q['correct']) == label

    # 2026-10-12 curated 70-question expansion: 7 per category.
    from quiz_expansion_300 import ROWS as expansion_rows, validate as validate_expansion
    validate_expansion()
    expanded = [q for pool in dq.POOLS.values() for q in pool if '-curated300-' in q['key']]
    assert len(expanded) == 70
    assert all(sum('-curated300-' in q['key'] for q in pool) == 7 for pool in dq.POOLS.values())
    assert sum(q['difficulty'] == 'intermediate' for q in expanded) == 40
    assert sum(q['difficulty'] == 'standard' for q in expanded) == 30
    assert all(q['source_url'].startswith('https://blog.gtowizard.com/') for q in expanded)
    assert all(q['prompt'].startswith('【応用】') == (q['difficulty'] == 'intermediate') for q in expanded)
    expected300 = {
        'pot_odds-curated300-river-half-160': '25%',
        'pot_odds-curated300-river-double-150': '40%',
        'pot_odds-curated300-third-player-call': '20%',
        'pot_odds-curated300-raise-to-180': '26%',
        'pot_odds-curated300-rake-adjusted': '21%',
        'pot_odds-curated300-implied-guarantee': '＋10',
        'equity-curated300-turn-nine-clean': '20%',
        'equity-curated300-flop-eight-clean': '31%',
        'equity-curated300-win-tie-55': '55%',
        'equity-curated300-eqr-56': '56',
        'equity-curated300-eqr-inverse': '120%',
        'equity-curated300-equity-two-groups': '45%',
        'mdf-curated300-mdf-half-100': '67%',
        'mdf-curated300-mdf-double-100': '33%',
        'mdf-curated300-alpha-120-80': '40%',
        'mdf-curated300-bluff-ev-plus4': '＋4',
        'mdf-curated300-bluffcatcher-12': 'フォールドが有利です',
        'spr-curated300-spr-two': '2',
        'spr-curated300-spr-quarter': '0.25',
        'spr-curated300-spr-after-call': '0.75',
        'spr-curated300-geometry-one': '37%',
        'spr-curated300-geometry-three': '82%',
        'combo-curated300-blocked-ako-five': '5コンボ',
        'icm-curated300-icm-three-player-prize': '64',
        'vocabulary-curated300-vocab-monotone-board': 'モノトーンボード',
        'combo-curated300-offsuit-twelve': '12コンボ',
        'combo-curated300-suited-four': '4コンボ',
        'combo-curated300-one-ace-block': '3コンボ',
        'combo-curated300-same-suit-block': '3コンボ',
        'combo-curated300-two-queens-board': '1コンボ',
        'combo-curated300-weight-bluff-value': '33%',
        'icm-curated300-icm-bf-150': '60%',
        'icm-curated300-icm-bf-two': '67%',
        'icm-curated300-icm-win-70': '＋20',
        'bet_sizing-curated300-size-value-ratio-half': '3コンボ',
        'bet_sizing-curated300-size-value-ratio-over': '4コンボ',
        'bet_sizing-curated300-size-raise-call': '60',
        'bet_sizing-curated300-size-geometry-half': '毎回50%ポット',
        'bet_sizing-curated300-size-call-response': '50のベット',
        'bet_sizing-curated300-size-bluff-plus2': '＋2',
        'range-curated300-range-bet-posterior': '57%',
        'range-curated300-range-weight-20': '20%',
    }
    for key, expected in expected300.items():
        question = next((q for q in expanded if q['key'] == key), None)
        assert question is not None, key
        correct_label = next(c['label'] for c in question['choices'] if c['value'] == question['correct'])
        assert correct_label == expected, (key, correct_label)
        readable = make_readable(question)
        assert readable['source_url'] == question['source_url']
        assert len(readable['prompt']) <= 250
        assert len({c['label'] for c in readable['choices']}) == 4

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
    # Exercise the full production entrypoint, including point-ledger schema.
    with isolated_production_app(url) as production:
        yield production.app, production.db


def run(postgres=False):
    bank_checks()
    with test_app(postgres) as (app, db), patch.object(dq, 'utc_now') as clock:
        clock.return_value = datetime(2026, 9, 11, 14, 59, 59, tzinfo=timezone.utc)
        suffix = uuid.uuid4().hex[:8]
        name_suffix = ''.join('アイウエオカキクケコサシスセソタ'[int(c,16)] for c in suffix)
        with TestClient(app, base_url="https://testserver") as a, TestClient(app, base_url="https://testserver") as b, TestClient(app, base_url="https://testserver") as anon:
            uid = login(a, 'クイズア'+name_suffix, '123456')['id']
            other = login(b, 'ベツクイズイ'+name_suffix, '234567')['id']
            json_response(anon.get('/api/quiz/question'), 401)
            json_response(a.get('/api/admin/console/quiz-stats'), 403)
            json_response(anon.get('/api/admin/console/quiz-stats'), 401)

            def get():
                with TestClient(app, base_url="https://testserver") as tab:
                    tab.cookies.update(a.cookies)
                    return json_response(tab.get('/api/quiz/question'))

            def persisted_answer(question_id, *, correct=True):
                with db.connect() as con:
                    row = con.execute(
                        'SELECT question_json FROM quiz_daily_answers WHERE id=?',
                        (question_id,),
                    ).fetchone()
                snapshot = json.loads(row['question_json'])
                if correct:
                    return snapshot['correct']
                return next(choice['value'] for choice in snapshot['choices'] if choice['value'] != snapshot['correct'])

            with ThreadPoolExecutor(max_workers=8) as pool:
                opened = list(pool.map(lambda _: get(), range(16)))
            q = opened[0]
            assert all(item == q for item in opened)
            assert q['date'] == '2026-09-11' and 'correct' not in q and 'explanation' not in q and 'source_url' not in q
            qb = json_response(b.get('/api/quiz/question'))
            assert qb['id'] != q['id'] and qb['prompt'] == q['prompt']
            assert q['reward_correct'] == 10 and q['reward_incorrect'] == 5
            payload = {'question_id': q['id'], 'answer': persisted_answer(q['id'], correct=False)}
            json_response(b.post('/api/quiz/answer', json=payload), 404)
            json_response(a.post('/api/quiz/answer', json={**payload, 'answer': 'INVALID'}), 400)
            json_response(a.post('/api/quiz/answer', json={**payload, 'question_id': 'dqa-unknown'}), 404)

            # Answer uses its persisted snapshot even after a bank/deployment change.
            def send(_):
                with TestClient(app, base_url="https://testserver") as tab:
                    tab.cookies.update(a.cookies)
                    return json_response(tab.post('/api/quiz/answer', json=payload))
            with patch.object(dq, 'build_daily_questions', side_effect=AssertionError('daily set must be persisted')):
                with ThreadPoolExecutor(max_workers=8) as pool:
                    results = list(pool.map(send, range(16)))
                assert sum(r['awarded'] for r in results) == 5
                assert sum(not r['already_answered'] for r in results) == 1
                assert len({r['correct'] for r in results}) == 1
                duplicate = json_response(a.post('/api/quiz/answer', json={**payload, 'answer': q['choices'][1]['value']}))
                assert duplicate['awarded'] == 0 and duplicate['correct'] == results[0]['correct']
                assert duplicate['explanation']
                for number in range(2, 11):
                    q = get()
                    assert q['slot'] == number
                    r = json_response(a.post('/api/quiz/answer', json={'question_id': q['id'], 'answer': persisted_answer(q['id'])}))
                    assert r['awarded'] == 10 and r['progress']['earned'] == 5 + (number-1)*10
                for _ in range(12):
                    assert get()['done'] is True
            with db.connect() as con:
                rows = con.execute("SELECT * FROM point_ledger WHERE user_id=? AND kind='quiz_reward'", (uid,)).fetchall()
                assert len(rows) == 10 and sum(float(r['amount']) for r in rows) == 95
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
                rb = json_response(b.post('/api/quiz/answer', json={'question_id': qb['id'], 'answer': persisted_answer(qb['id'])}))
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
            body = {'question_id': tomorrow['id'], 'answer': persisted_answer(tomorrow['id'])}
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
