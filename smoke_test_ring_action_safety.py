"""Real Ring HTTP actions reject stale decisions and respect timebank races."""
import asyncio
import os
import tempfile
import time
import uuid
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace

os.environ.pop('DATABASE_URL',None)
os.environ['JJ_DB_PATH']=tempfile.mkdtemp(prefix='jj-ring-safety-')+'/test.db'
os.environ['JJ_ENABLE_DEMO_MEMBER']='0'
import app as production
import ring_action_safety as safety
from fastapi.testclient import TestClient

def main():
    s=production.runtime_server;e=production.runtime_poker_engine;db=production.db
    c=TestClient(production.app,base_url='https://testserver')
    users=[]
    for name in ['リングカンサア','リングカンサイ','リングカンサウ']:
        r=c.post('/api/auth/pin',json={'name':name,'pin':'123456'});assert r.status_code==200,r.text
        users.append(r.json()['user'])
    def setup():
        state=e.blank_table_state(table_id='jj-table-a',name='audit')
        for i,u in enumerate(users):e.seat_player(state,user_id=u['id'],name=u['name'],seat=i,stack=1500)
        e.start_hand(state);s.arm_action_deadline(state);s.save_table(state)
        return state
    def actor(state):return next(p for p in state['seats'] if p['seat']==state['hand']['action_seat'])
    def body(state,action='fold',receipt=None):
        return {'action':action,'action_id':receipt or uuid.uuid4().hex,'hand_id':state['hand']['id'],'turn_id':safety.turn_id(state)}
    def send(state,payload):
        uid=actor(state)['user_id'];c.headers['Authorization']='Bearer '+db.create_session(uid)
        return c.post('/api/tables/jj-table-a/action',json=payload)
    state=setup();old=body(state)
    assert 28<datetime.fromisoformat(state['hand']['action_deadline']).timestamp()-time.time()<=30
    public=s.public_state(state,users[0]['id']);assert public['turn_id']==state['hand']['turn_id']
    assert '_processed_action_ids' not in public
    for key in ('hand_id','turn_id','action_id'):
        missing={k:v for k,v in old.items() if k!=key}
        assert send(state,missing).status_code==409
    assert send(state,{**old,'turn_id':'obsolete-turn'}).status_code==409
    assert send(state,{**old,'hand_id':'obsolete-hand'}).status_code==409
    first=send(state,old);assert first.status_code==200,first.text
    repeat=send(state,old);assert repeat.status_code==200
    after=s.load_table(state['id']);assert safety.turn_id(after)!=old['turn_id']
    # A receipt belongs to its actor; a second player's coincident ID is not a replay.
    second=send(after,body(after,action='call',receipt=old['action_id']));assert second.status_code==200,second.text
    assert len(s.load_table(state['id'])['_processed_action_ids'])==2
    state=setup();state['hand']['action_deadline']=(datetime.now(timezone.utc)-timedelta(seconds=2)).isoformat();s.save_table(state)
    assert send(state,body(state,'call')).status_code==409
    assert not any(p['folded'] for p in s.load_table(state['id'])['seats'])
    # Persisted active hands from the previous release have an immediately usable token.
    state=setup();state['hand'].pop('turn_id');s.save_table(state)
    legacy=s.public_state(state,users[0]['id'])['turn_id'];assert legacy.startswith('ring-legacy-')
    assert send(state,body(state)).status_code==200
    # A request arriving before expiry remains legal while queued for the lock.
    async def race():
        state=setup();state['hand']['action_deadline']=(datetime.now(timezone.utc)+timedelta(seconds=.15)).isoformat();s.save_table(state)
        player=actor(state);payload=SimpleNamespace(**body(state,'call'),amount=None);key=(state['id'],safety.turn_id(state),player['user_id'])
        lock=s.get_table_lock(state['id']);await lock.acquire()
        task=asyncio.create_task(s.action(state['id'],payload,{'id':player['user_id']}))
        await asyncio.sleep(.01)
        assert key in s._jj_ring_pending_actions
        deadline=datetime.fromisoformat(state['hand']['action_deadline']).timestamp()
        assert safety.pending_before_deadline(s,state,deadline)
        wrong={**state,'seats':[{**p,'user_id':p['user_id']+10000} for p in state['seats']]}
        assert not safety.pending_before_deadline(s,wrong,deadline)
        await asyncio.sleep(.16)
        lock.release();await task
        assert not s._jj_ring_pending_actions
        assert actor(s.load_table(state['id']))['user_id']!=player['user_id']
    asyncio.run(race())
    async def timebank_boundary():
        state=setup();player=actor(state);token=safety.turn_id(state)
        state['hand']['action_deadline']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        s.save_table(state)
        deadline=datetime.fromisoformat(state['hand']['action_deadline']).timestamp()
        key=(state['id'],token,player['user_id']);s._jj_ring_pending_actions[key]=[deadline-.01]
        task=asyncio.create_task(s.timeout_loop())
        try:
            await asyncio.sleep(.6)
            now=s.load_table(state['id']);assert actor(now)['timebank_cards_remaining']==3
            s._jj_ring_pending_actions.pop(key)
            await asyncio.sleep(.6)
            now=s.load_table(state['id']);assert actor(now)['timebank_cards_remaining']==2
            assert safety.turn_id(now)==token # extension does not change the decision
            assert now['hand']['action_clock_source']=='timebank'
        finally:
            task.cancel()
            try:await task
            except asyncio.CancelledError:pass
    asyncio.run(timebank_boundary())
    js=production._patched_app_js()
    assert "const body={action,action_id:jjV121ActionId()};\n    body.hand_id=tableState.hand?.id;" in js
    print('JJ_RING_ACTION_SAFETY_OK stale/late/replay/legacy/queued/timebank')

if __name__=='__main__':main()
