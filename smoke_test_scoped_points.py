"""Scoped corrections preserve raw results, totals, months and reversal scope."""
import os
import tempfile
import uuid
import sys
from urllib.parse import urlsplit
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

if '--postgres' in sys.argv:
    url = urlsplit(os.environ.get('DATABASE_URL', ''))
    assert url.hostname in {'localhost','127.0.0.1'} and url.path == '/jj_arena_ci'
else:
    os.environ.pop('DATABASE_URL', None)
    os.environ['JJ_DB_PATH'] = tempfile.mkdtemp(prefix='jj-scoped-') + '/test.db'
os.environ['JJ_ENABLE_DEMO_MEMBER'] = '0'
import app
import admin_console
from fastapi.testclient import TestClient

def main():
    db = app.db
    with db.connect() as con:
        ids = [db.insert_returning_id(con,
            'INSERT INTO users(name,email,password_hash,role,ranking_name,created_at) VALUES (?,?,?,?,?,?)',
            (name, uuid.uuid4().hex, 'unused', role, name, '2026-09-01T00:00:00'))
            for name, role in [('ScopeAdmin','admin'), ('ScopePlayer','member')]]
        con.execute('INSERT INTO entries(id,date,name,remaining,reentries,initial,points,game,game_type,source,created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            ('scope-entry','2026-09-05','ScopePlayer',500,0,450,50,'ring','ring','test',ids[0],'2026-09-05T12:00:00'))
        con.execute('INSERT INTO online_hands(hand_id,table_id,hand_no,gross_pot_bb,rake_bb,played_at,month,voided) VALUES (?,?,?,?,?,?,?,0)',
            ('scope-hand','jj-table-a',1,100,0,'2026-09-05T12:00:00','2026-09'))
        con.execute('INSERT INTO online_hand_results(id,hand_id,table_id,user_id,ranking_name,result_bb,points,month,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
            ('scope-result','scope-hand','jj-table-a',ids[1],'ScopePlayer',100/3,100,'2026-09','2026-09-05T12:00:00'))
    c = TestClient(app.app, base_url='https://testserver', raise_server_exceptions=False)
    c.headers['Authorization'] = 'Bearer ' + db.create_session(ids[0])
    endpoint = '/api/admin/console/points'
    body = dict(request_id=uuid.uuid4().hex,user_id=ids[1],scope='online',direction='debit',amount=100,reason='test correction',effective_at='2026-09-05T12:00')
    def row(month=None):
        rows = c.get('/api/rankings', params={'month':month} if month else {}).json()
        return next(r for r in rows if r['name']=='ScopePlayer')
    assert row()['points']==150
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: c.post(endpoint,json=body),range(4)))
    assert all(r.status_code==200 for r in results), [r.text for r in results]
    assert all(r.json()==results[0].json() for r in results)
    tx = results[0].json()['id']
    r = row('2026-09')
    assert (r['online_points'],r['club_points'],r['admin_points'],r['points'])==(0,50,0,50),r
    assert r['online_raw_points']==100 and r['online_hands']==1
    assert row()['points']==50
    assert c.post(endpoint,json={**body,'scope':'club'}).status_code==409
    assert c.post(endpoint,json={**body,'request_id':uuid.uuid4().hex,'scope':'invalid'}).status_code==422
    for date in [None,'2026-02-31T12:00','2028-01-01T12:00']:
        assert c.post(endpoint,json={**body,'request_id':uuid.uuid4().hex,'effective_at':date}).status_code==400
    assert next(r for r in c.get('/api/home/core').json()['rankings'] if r['name']=='ScopePlayer')['points']==50
    users=c.get('/api/admin/console/users').json()
    assert next(u for u in users if u['id']==ids[1])['online_points']==0
    assert next(x for x in c.get(endpoint).json() if x['id']==tx)['scope']=='online'
    # Failure rolls back scope-aware rows, request claims and audits together.
    failed={**body,'request_id':uuid.uuid4().hex}
    with patch.object(admin_console,'_audit',side_effect=RuntimeError('test')):
        assert c.post(endpoint,json=failed).status_code==500
    assert row()['points']==50
    assert c.post(endpoint+'/'+tx+'/reverse').status_code==200
    assert c.post(endpoint+'/'+tx+'/reverse').status_code==409
    assert row()['online_points']==100 and row()['points']==150
    # A different month's correction must not leak into September.
    assert c.post(endpoint,json={**body,'request_id':uuid.uuid4().hex,'scope':'club','amount':20,'effective_at':'2026-10-03T12:00'}).status_code==200
    assert row('2026-09')['club_points']==50
    assert row('2026-10')['club_points']==-20
    assert row()['club_points']==30 and row()['online_points']==100 and row()['points']==130
    # General remains separate and keeps legacy replay identities.
    general={**body,'request_id':uuid.uuid4().hex,'scope':'general','amount':10}
    assert c.post(endpoint,json=general).status_code==200
    assert c.post(endpoint,json={k:v for k,v in general.items() if k!='scope'}).status_code==200
    assert row()['admin_points']==-10 and row()['points']==120
    member=TestClient(app.app,base_url='https://testserver')
    member.headers['Authorization']='Bearer '+db.create_session(ids[1])
    assert member.post(endpoint,json={**body,'request_id':uuid.uuid4().hex}).status_code==403
    with db.connect() as con:
        assert float(con.execute("SELECT points FROM online_hand_results WHERE id='scope-result'").fetchone()['points'])==100
    print('JJ_SCOPED_POINTS_OK scopes months zero reversal replay rollback auth home')

if __name__=='__main__':
    main()
