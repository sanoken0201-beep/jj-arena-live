"""Manual points: concurrent replay, lost response and audit-failure rollback."""
import os
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit
from unittest.mock import patch

if '--postgres' in __import__('sys').argv:
    url=urlsplit(os.environ.get('DATABASE_URL',''))
    assert url.hostname in {'localhost','127.0.0.1'} and url.path=='/jj_arena_ci'
else:
    os.environ.pop('DATABASE_URL',None)
    os.environ['JJ_DB_PATH']=tempfile.mkdtemp(prefix='jj-points-safety-')+'/test.db'
os.environ['JJ_ENABLE_DEMO_MEMBER']='0'
import app as production
import admin_console
from fastapi.testclient import TestClient

def main():
    db=production.db
    with db.connect() as con:
        ids=[]
        for role in ['admin','member']:
            uid=db.insert_returning_id(con,"""INSERT INTO users(name,email,password_hash,role,arena_chips,xp,approved,disabled,ranking_name,created_at)
                VALUES (?,?,?,?,0,0,1,0,?,?)""",('ポイントテスト',uuid.uuid4().hex,'unused',role,'ポイントテスト',db.utcnow()))
            ids.append(uid)
    token=db.create_session(ids[0])
    def client():
        c=TestClient(production.app,base_url='https://testserver',raise_server_exceptions=False)
        c.headers['Authorization']='Bearer '+token
        return c
    def send(body):
        # No lifespan: avoid background schedulers when racing independent requests.
        return client().post('/api/admin/console/points',json=body)
    body={'request_id':uuid.uuid4().hex,'user_id':ids[1],'direction':'credit','amount':100,'reason':'audit safety'}
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses=list(pool.map(send,[body]*4))
    assert all(r.status_code==200 for r in responses),[(r.status_code,r.text) for r in responses]
    original=responses[0].json()
    assert all(r.json()==original for r in responses)
    assert send(body).json()==original  # retry after the response was lost
    assert send({**body,'amount':200}).status_code==409
    assert send({k:v for k,v in body.items() if k!='request_id'}).status_code==422
    with db.connect() as con:
        assert con.execute('SELECT COUNT(*) n FROM point_ledger WHERE user_id=?',(ids[1],)).fetchone()['n']==1
        assert con.execute("SELECT COUNT(*) n FROM admin_audit_log WHERE target_user_id=? AND action='point.credit'",(ids[1],)).fetchone()['n']==1
    failed={**body,'request_id':uuid.uuid4().hex}
    with patch.object(admin_console,'_audit',side_effect=RuntimeError('injected audit failure')):
        assert send(failed).status_code==500
    with db.connect() as con:
        assert con.execute('SELECT COUNT(*) n FROM admin_point_requests WHERE actor_id=? AND request_id=?',(ids[0],failed['request_id'])).fetchone()['n']==0
        assert con.execute('SELECT COUNT(*) n FROM point_ledger WHERE user_id=?',(ids[1],)).fetchone()['n']==1
    assert send(failed).status_code==200
    assert send({**body,'request_id':uuid.uuid4().hex,'direction':'debit','amount':25}).json()['amount']==-25
    # A failure in reversal auditing must roll back both reversal and claim.
    url='/api/admin/console/points/'+original['id']+'/reverse'
    with patch.object(admin_console,'_audit',side_effect=RuntimeError('injected reversal audit failure')):
        assert client().post(url).status_code==500
    with db.connect() as con:
        assert con.execute('SELECT COUNT(*) n FROM point_ledger WHERE reversal_of=?',(original['id'],)).fetchone()['n']==0
        assert con.execute('SELECT COUNT(*) n FROM point_ledger_reversal_claims WHERE reversal_of=?',(original['id'],)).fetchone()['n']==0
    assert client().post(url).status_code==200
    assert client().post(url).status_code==409
    assert send(body).json()==original # replay does not undo a later reversal
    with db.connect() as con:
        assert float(con.execute('SELECT SUM(amount) n FROM point_ledger WHERE user_id=?',(ids[1],)).fetchone()['n'])==75
    print('JJ_ADMIN_POINT_SAFETY_OK concurrent=4 replay=exact audit_rollback=ok reversal_rollback=ok')

if __name__=='__main__':main()
