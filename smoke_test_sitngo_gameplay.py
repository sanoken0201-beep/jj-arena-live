"""Full tournament regression on a disposable DB, never production accounts."""
import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from smoke_test_sitngo_phase1 import add_member, production_app, sitngo
from fastapi import HTTPException


def main(paid=False):
    db=production_app.db
    service=production_app.app.state.jj_sitngo
    rt=service.runtime
    with db.connect() as con:
        admin=con.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()['id']
    users=[add_member(i+100) for i in range(6)]
    if paid:
        with db.connect() as con:
            for uid in users:
                con.execute("INSERT INTO point_ledger(id,user_id,amount,kind,reason,effective_at,created_by,created_at) VALUES (?,?,?,?,?,?,?,?)",(f'fund-{uid}',uid,'1000.00','credit','test',db.utcnow(),admin,db.utcnow()))
    clock=time.time()
    def launch(count):
        nonlocal clock
        clock+=300
        with patch.object(sitngo,'_utcnow',return_value=datetime.fromtimestamp(clock,timezone.utc)):
            event=service.create_event(sitngo.SitNGoCreateIn(name='Gameplay',entry_fee='10.01' if paid else '0',starts_at=datetime.fromtimestamp(clock+120,timezone.utc).isoformat()),admin)
            for uid in users[:count]: service.register(event['id'],uid)
            clock+=121
            with patch('time.time',return_value=clock): service.reconcile(datetime.fromtimestamp(clock,timezone.utc))
        return event['id']
    for count in ((2,3,4,5,6) if paid else (2,4,6)):
        eid=launch(count)
        state=rt.load(eid)
        assert state['status']=='playing'
        assert state['_ante_paid']==400
        assert state['small_blind']==200 and state['big_blind']==400
        assert state['chip_unit']==100
        # Registration is the seating commitment. Nobody needs to reconnect or
        # open the tournament table before the server seats the full field and
        # posts forced bets for them.
        assert {int(p['user_id']) for p in state['seats']}==set(users[:count])
        assert all(not p.get('sitting_out',False) for p in state['seats'])
        sb=next(p for p in state['seats'] if p['seat']==state['hand']['small_blind_seat'])
        bb=next(p for p in state['seats'] if p['seat']==state['hand']['big_blind_seat'])
        assert sb['round_bet']==200 and sb['stack']==29800
        assert bb['round_bet']==400 and bb['stack']==29200
        assert sum(p['stack']+p['contributed'] for p in state['seats'])+state['_ante_paid']==count*30000
        pub=rt.public(state,users[0])
        assert pub['chip_unit']==100 and pub['tournament']['chip_unit']==100
        assert 'deck' not in pub['hand'] and '_revision' not in pub
        assert next(p for p in pub['seats'] if p['user_id']==users[1])['cards']==['??','??']
        snapshot=json.dumps(state,sort_keys=True)
        assert json.dumps(rt.load(eid),sort_keys=True)==snapshot
        # Preserve hand/cards/deadline across server downtime.
        before=datetime.fromisoformat(state['hand']['action_deadline']).timestamp()
        clock+=70
        with patch('time.time',return_value=clock): asyncio.run(rt.tick(eid,now=clock,recover=True))
        recovered=rt.load(eid)
        assert recovered['hand']['id']==state['hand']['id'] and recovered['hand']['deck']==state['hand']['deck']
        assert abs(datetime.fromisoformat(recovered['hand']['action_deadline']).timestamp()-before-70)<.01
        if count==2:
            # Simulate both registered players never returning to the table. The
            # scheduler times out the action, starts the next hand, rotates the
            # blinds, and posts them again without any connection/presence event.
            first_sb=recovered['hand']['small_blind_seat'];first_bb=recovered['hand']['big_blind_seat']
            clock=datetime.fromisoformat(recovered['hand']['action_deadline']).timestamp()+.1
            with patch('time.time',return_value=clock):asyncio.run(rt.tick(eid,now=clock))
            waiting=rt.load(eid)
            assert waiting['status']=='waiting' and waiting.get('next_hand_at_epoch')
            clock=float(waiting['next_hand_at_epoch'])+.1
            with patch('time.time',return_value=clock):asyncio.run(rt.tick(eid,now=clock))
            rotated=rt.load(eid)
            assert rotated['status']=='playing'
            assert rotated['hand']['small_blind_seat']==first_bb
            assert rotated['hand']['big_blind_seat']==first_sb
            assert all(not p.get('sitting_out',False) for p in rotated['seats'])
            new_sb=next(p for p in rotated['seats'] if p['seat']==rotated['hand']['small_blind_seat'])
            new_bb=next(p for p in rotated['seats'] if p['seat']==rotated['hand']['big_blind_seat'])
            assert new_sb['round_bet']==200 and new_bb['round_bet']==400
        # Complete an actual tournament through the engine and runtime scheduler.
        for _ in range(2000):
            state=rt.load(eid)
            if state['tournament']['status']=='finished': break
            hand=state['hand']
            with patch('time.time',return_value=clock):
                if state['status']=='playing' and hand.get('action_seat') is not None:
                    p=next(p for p in state['seats'] if p['seat']==hand['action_seat'])
                    legal=rt.engine.legal_actions(state,p['user_id'])
                    rt.engine.apply_action(state,p['user_id'],'allin' if legal.get('can_all_in') else 'call' if legal.get('can_call') else 'check')
                    production_app.runtime_server.arm_action_deadline(state)
                    rt.save(state)
                else:
                    clock+=5
                    asyncio.run(rt.tick(eid,now=clock))
        else: raise AssertionError('tournament did not finish')
        assert len(state['tournament']['results'])==count
        assert sum(p['stack'] for p in state['seats'])==count*30000
        assert all(p['stack'] % state['chip_unit'] == 0 for p in state['seats'])
        assert len([x for x in state['tournament']['results'] if x['place']==1])==1
        assert service._row(eid)['status']=='finished'
        if paid:
            from sitngo_points import cents
            results=state['tournament']['results']
            assert sum(cents(r['prize_points']) for r in results)==count*1001
            assert state['tournament'].get('points_settled') is True
            if count==6:
                winner=next(r for r in results if r['place']==1)
                second_place=[r for r in results if r['place']==2]
                assert second_place
                with db.connect() as con:
                    payments=con.execute(
                        'SELECT user_id,entry_tx,fee_cents,refunded FROM sitngo_payments WHERE event_id=? ORDER BY user_id',
                        (eid,),
                    ).fetchall()
                    assert len(payments)==6
                    assert all(int(row['fee_cents'])==1001 and int(row['refunded'])==0 for row in payments)
                    for row in payments:
                        entry=con.execute(
                            'SELECT user_id,amount,kind FROM point_ledger WHERE id=?',
                            (row['entry_tx'],),
                        ).fetchone()
                        assert entry and int(entry['user_id'])==int(row['user_id'])
                        assert entry['kind']=='sitngo_entry' and cents(entry['amount'])==-1001
                    prize_rows=con.execute(
                        "SELECT user_id,amount FROM point_ledger WHERE kind='sitngo_prize' AND id LIKE ? ORDER BY user_id",
                        (f'sng-prize-{eid}-%',),
                    ).fetchall()
                    prizes={int(row['user_id']):cents(row['amount']) for row in prize_rows}
                    second_ids={int(r['user_id']) for r in second_place}
                    assert prizes.get(int(winner['user_id']))==4204,prizes
                    assert sum(prizes.get(uid,0) for uid in second_ids)==1802,prizes
                    assert set(prizes)==({int(winner['user_id'])}|second_ids),prizes
                    settled=con.execute(
                        'SELECT awards_json FROM sitngo_settlements WHERE event_id=?',
                        (eid,),
                    ).fetchone()
                    assert settled
                    awards={int(uid):int(amount) for uid,amount in json.loads(settled['awards_json']).items()}
                    assert len(awards)==6 and sum(awards.values())==6006
                    assert awards[int(winner['user_id'])]==4204
                    assert sum(awards[int(r['user_id'])] for r in second_place)==1802
                    assert all(awards[int(r['user_id'])]==0 for r in results if r['place']>2)
                    ranking_names={
                        int(row['id']):str(row['ranking_name'] or row['name'])
                        for row in con.execute(
                            'SELECT id,name,ranking_name FROM users WHERE id IN (?,?,?,?,?,?)',
                            tuple(int(r['user_id']) for r in results),
                        ).fetchall()
                    }
                from admin_console import _rankings
                official={row['name']:row for row in _rankings(db,production_app.runtime_server,season='fall')}
                with db.connect() as con:
                    for uid,name in ranking_names.items():
                        assert name in official
                        assert cents(official[name]['points'])==service.points.balance(con,uid)
        old=list(state['tournament']['results'])
        rt.save(state)
        assert rt.load(eid)['tournament']['results']==old
        # Lost-update protection.
        stale=rt.load(eid); newer=rt.load(eid); rt.save(newer)
        try: rt.save(stale)
        except HTTPException as exc: assert exc.status_code==409
        else: raise AssertionError('stale write accepted')
    with db.connect() as con:
        assert con.execute('SELECT COUNT(*) n FROM online_hands').fetchone()['n']==0
        assert con.execute('SELECT COUNT(*) n FROM online_hand_results').fetchone()['n']==0
        if not paid:assert con.execute('SELECT COUNT(*) n FROM point_ledger').fetchone()['n']==0
        assert con.execute('SELECT COUNT(*) n FROM sitngo_hands').fetchone()['n']>0
    # Dead-ante short BB: blind first, then the remaining legal 100-point chip funds ante.
    e=rt.engine
    state=e.blank_table_state(table_id='test',name='short',max_seats=2,small_blind=100,big_blind=200,min_buyin=1,max_buyin=10000)
    e.seat_player(state,user_id=1,name='A',seat=0,stack=10000)
    e.seat_player(state,user_id=2,name='B',seat=1,stack=300)
    state['tournament']={'bb_ante':200}
    e.start_hand(state)
    bb=next(p for p in state['seats'] if p['seat']==state['hand']['big_blind_seat'])
    assert bb['round_bet']==200 and bb['stack']==0 and state['_ante_paid']==100
    assert e.legal_actions(state,1)['call_amount']==100
    print('JJ_SITNGO_GAMEPLAY_OK')


if __name__=='__main__': main()