import asyncio
import os
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone

os.environ.pop('DATABASE_URL',None)
_tmp=tempfile.TemporaryDirectory(prefix='jj-sng-api-')
os.environ['JJ_DB_PATH']=str(Path(_tmp.name)/'api.sqlite3')
from smoke_test_sitngo_phase1 import add_member, production_app as prod, sitngo
from fastapi.testclient import TestClient


def main():
    service=prod.app.state.jj_sitngo
    rt=service.runtime
    with prod.db.connect() as con:
        admin=int(con.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()['id'])
    users=[add_member(300+i) for i in range(3)]
    event=service.create_event(sitngo.SitNGoCreateIn(starts_at=(datetime.now(timezone.utc)+timedelta(minutes=2)).isoformat()),admin)
    for uid in users[:2]: service.register(event['id'],uid)
    service.reconcile(datetime.now(timezone.utc)+timedelta(minutes=3))
    eid=event['id']
    client=TestClient(prod.app,base_url='https://testserver')
    assert client.get('/api/tables/'+eid).status_code==401
    def login(uid):
        token=prod.db.create_session(uid)
        client.headers['Authorization']='Bearer '+token
        client.cookies.set('jj_session',token)
    login(users[0])
    response=client.get('/api/tables/'+eid)
    assert response.status_code==200,response.text
    state=response.json()['state']
    assert state['tournament']['entry_fee']==0
    assert state['big_blind']==400 and state['tournament']['bb_ante']==400
    assert state['turn_id'] and state['hand']['turn_id']==state['turn_id']
    for operation,body in [('seat',{'seat':3}),('join',{}),('rebuy',{}),('presence',{'mode':'rebuy'}),('leave',{}),('leave-after-hand',{'enabled':True}),('start',{})]:
        assert client.post(f'/api/tables/{eid}/{operation}',json=body).status_code==409,operation
    assert client.post('/api/tables/jj-table-a/join',json={}).status_code==400
    assert client.post(f'/api/tables/{eid}/chat',json={'body':'大会チャット'}).status_code==200
    assert client.get('/api/tables/'+eid).json()['messages'][0]['body']=='大会チャット'
    login(users[2])
    assert client.post(f'/api/tables/{eid}/chat',json={'body':'観戦者書き込み'}).status_code==403
    actor=next(p for p in state['seats'] if p['seat']==state['hand']['action_seat'])['user_id']
    login(actor)
    body={'action':'fold','action_id':'sng-api-idempotent-1','hand_id':state['hand']['id'],'turn_id':state['turn_id']}
    assert client.post(f'/api/tables/{eid}/action',json={**body,'hand_id':'old-hand'}).status_code==409
    first=client.post(f'/api/tables/{eid}/action',json=body)
    assert first.status_code==200,first.text
    repeat=client.post(f'/api/tables/{eid}/action',json=body)
    assert repeat.status_code==200 and repeat.json()['hand']['id']==first.json()['hand']['id']
    assert [p['stack'] for p in repeat.json()['seats']]==[p['stack'] for p in first.json()['seats']]
    login(users[2])
    history=client.get(f'/api/sitngo/{eid}/history').json()['hands']
    assert len(history)==1
    assert all(p['cards']==[] for p in history[0]['seats']),history
    assert 'deck' not in history[0]['hand']
    with client.websocket_connect('/ws/tables/'+eid) as ws:
        frame=ws.receive_json()
        assert frame['type']=='state' and frame['state']['tournament']['event_id']==eid
    # A blind level changes only between hands. Simulate twelve completed hands
    # in the persisted counter; the following deal must be hand 13 at level 2.
    # Elapsed time is intentionally large but is not the progression source.
    state=rt.load(eid)
    state['tournament']['elapsed_seconds']=60_001
    state['hand_no']=12
    state['next_hand_at_epoch']=0
    rt.save(state)
    asyncio.run(rt.tick(eid))
    state=rt.load(eid)
    assert state['hand_no']==13
    assert state['tournament']['level']==2 and state['big_blind']==600
    assert state['tournament']['bb_ante']==600
    assert state['status']=='playing'
    assert state['hand']['turn_id']
    # A disconnected actor keeps their seat. The first missed deadline spends a
    # mandatory timebank card; only a later zero-card deadline forces fold.
    actor=next(p for p in state['seats'] if p['seat']==state['hand']['action_seat'])
    state['hand']['action_deadline']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    rt.save(state)
    asyncio.run(rt.tick(eid))
    extended=rt.load(eid)
    assert len(extended['seats'])==2
    actor=next(p for p in extended['seats'] if p['seat']==extended['hand']['action_seat'])
    assert actor['timebank_cards_remaining']==2
    assert extended['hand']['action_clock_source']=='timebank'
    assert not any('forced fold' in x.lower() for x in extended['hand']['log'])
    actor['timebank_cards_remaining']=0
    extended['hand']['action_deadline']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
    rt.save(extended)
    asyncio.run(rt.tick(eid))
    after=rt.load(eid)
    assert len(after['seats'])==2
    assert any('forced fold' in x.lower() for x in after['hand']['log'])
    # Equal starting stacks tie; unequal starting stacks rank higher.
    synthetic={'status':'waiting','hand_no':9,'hand':{'id':'tie','starting_stacks':{'1':100,'2':100,'3':200,'4':500}},
        'seats':[{'user_id':i,'name':str(i),'stack':900 if i==4 else 0} for i in range(1,5)],
        'tournament':{'status':'running','results':[]}}
    rt.finish(synthetic)
    ranks={r['user_id']:r['place'] for r in synthetic['tournament']['results']}
    assert ranks=={1:3,2:3,3:2,4:1},ranks
    print('JJ_SITNGO_API_OK')


if __name__=='__main__': main()
