"""Paid tournament integration: real games, refunds, atomicity, exact awards."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from pydantic import ValidationError
from fastapi import HTTPException
from smoke_test_sitngo_phase1 import production_app, add_member, sitngo
from sitngo_points import cents, prize_schedule, default_payouts
import smoke_test_sitngo_gameplay as gameplay


def main():
    gameplay.main(paid=True)
    db=production_app.db; service=production_app.app.state.jj_sitngo
    with db.connect() as con:
        admin=con.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()['id']
    uid=add_member(999)
    def event(fee='10.01'):
        return service.create_event(sitngo.SitNGoCreateIn(name='Paid tests',entry_fee=fee,
            starts_at=(datetime.now(timezone.utc)+timedelta(minutes=20)).isoformat()),admin)['id']
    for invalid in ('-1','1.001','NaN','Infinity','1000000.01'):
        try: event(invalid)
        except ValidationError: pass
        else: raise AssertionError('Invalid fee accepted')
    eid=event()
    # Registration is allowed even with a zero/insufficient balance. The entry
    # debit is authoritative and may take the season point balance negative.
    def attempt(_):
        try:service.register(eid,uid);return True
        except HTTPException as e:assert e.status_code==409;return False
    with ThreadPoolExecutor(max_workers=4) as pool:assert sum(pool.map(attempt,range(4)))==1
    with db.connect() as con:
        assert con.execute('SELECT COUNT(*) n FROM sitngo_registrations WHERE event_id=?',(eid,)).fetchone()['n']==1
        assert service.points.balance(con,uid)==-1001
        assert con.execute("SELECT COUNT(*) n FROM point_ledger WHERE user_id=? AND kind='sitngo_entry'",(uid,)).fetchone()['n']==1
    service.cancel_registration(eid,uid)
    with db.connect() as con:assert service.points.balance(con,uid)==0
    service.register(eid,uid)
    with db.connect() as con:assert service.points.balance(con,uid)==-1001
    service.cancel_event(eid,'test',admin);service.cancel_event(eid,'duplicate',admin)
    with db.connect() as con:
        assert service.points.balance(con,uid)==0
        assert con.execute("SELECT COUNT(*) n FROM point_ledger WHERE user_id=? AND kind='sitngo_refund'",(uid,)).fetchone()['n']==2
    short=event();service.register(short,uid)
    with db.connect() as con:assert service.points.balance(con,uid)==-1001
    service.reconcile(datetime.now(timezone.utc)+timedelta(minutes=21))
    with db.connect() as con:assert service.points.balance(con,uid)==0
    # Transaction rollback after ledger insertion must also roll back registration.
    rollback=event(); original=service.points.write
    def failure(*a,**kw):original(*a,**kw);raise RuntimeError('injected write failure')
    with patch.object(service.points,'write',side_effect=failure):
        try:service.register(rollback,uid)
        except RuntimeError:pass
        else:raise AssertionError('failure not propagated')
    with db.connect() as con:
        assert service.points.balance(con,uid)==0
        assert con.execute('SELECT COUNT(*) n FROM sitngo_registrations WHERE event_id=?',(rollback,)).fetchone()['n']==0
    service.cancel_event(rollback,'test',admin)

    # Paid events fail closed before the first card if the registered field and
    # locked entry escrow do not match exactly.
    guard_users=[add_member(91200+i) for i in range(2)]
    guard_start=datetime.now(timezone.utc)+timedelta(minutes=2)
    guarded=service.create_event(sitngo.SitNGoCreateIn(
        name='Escrow guard',entry_fee='10.01',starts_at=guard_start.isoformat()),admin)['id']
    with db.connect() as con:
        for i,u in enumerate(guard_users):
            service.points.write(con,guarded,u,1001,'credit',f'guard-funding-{i}')
    for u in guard_users:service.register(guarded,u)
    with db.connect() as con:
        con.execute('UPDATE sitngo_payments SET fee_cents=1000 WHERE event_id=? AND user_id=?',(guarded,guard_users[1]))
    try:
        service.reconcile(guard_start+timedelta(seconds=1))
    except RuntimeError as exc:
        assert 'escrow' in str(exc).lower()
    else:
        raise AssertionError('tournament started with corrupt entry escrow')
    assert service._row(guarded)['status']!='running'
    with db.connect() as con:
        con.execute('UPDATE sitngo_payments SET fee_cents=1001 WHERE event_id=? AND user_id=?',(guarded,guard_users[1]))
    service.reconcile(guard_start+timedelta(seconds=2))
    assert service._row(guarded)['status']=='running'
    guard_state={'id':guarded,'tournament':{'status':'finished','entrants':2,'results':[
        {'user_id':guard_users[0],'place':1},{'user_id':guard_users[1],'place':2}]}}
    with db.connect() as con:service.points.settle(con,guard_state)
    with db.connect() as con:
        con.execute("UPDATE sitngo_events SET status='finished',updated_at=? WHERE id=?",(db.utcnow(),guarded))

    # Persisted payout terms are revalidated at read/start time. Corrupt JSON
    # cannot silently launch a tournament that would become unpayable later.
    config_users=[add_member(91300+i) for i in range(2)]
    config_start=datetime.now(timezone.utc)+timedelta(minutes=3)
    corrupt=service.create_event(sitngo.SitNGoCreateIn(
        name='Payout config guard',entry_fee='0',starts_at=config_start.isoformat()),admin)['id']
    for u in config_users:service.register(corrupt,u)
    with db.connect() as con:
        con.execute("UPDATE sitngo_payout_settings SET payouts_json=? WHERE event_id=?",('{"6":[70,30]}',corrupt))
    try:
        service.reconcile(config_start+timedelta(seconds=1))
    except RuntimeError as exc:
        assert 'payout configuration' in str(exc)
    else:
        raise AssertionError('tournament started with corrupt payout configuration')
    assert service._row(corrupt)['status']!='running'
    with db.connect() as con:
        service.points.configure(con,corrupt,0,default_payouts())
    service.cancel_event(corrupt,'test cleanup',admin)

    assert prize_schedule(6006,6)==[4204,1802,0,0,0,0]
    assert prize_schedule(5005,5)==[5005,0,0,0,0]
    # Equal-stack double elimination for second splits 2nd+3rd prizes.
    tied=event(); ids=[add_member(1100+i) for i in range(6)]
    with db.connect() as con:
        for i,u in enumerate(ids):
            service.points.write(con,tied,u,1001,'credit',f'tie-funding-{i}')
    for u in ids:service.register(tied,u)
    state={'id':tied,'tournament':{'status':'finished','entrants':6,'results':[
        {'user_id':u,'place':p} for u,p in zip(ids,[1,2,2,4,5,6])]}}
    with db.connect() as con:service.points.settle(con,state)
    assert [cents(r['prize_points']) for r in state['tournament']['results']]==[4204,901,901,0,0,0]
    # Replaying a persisted settlement must verify that the prize ledger still
    # matches escrow, not merely trust awards_json.
    with db.connect() as con:
        prize_id=f'sng-prize-{tied}-{ids[0]}'
        con.execute('UPDATE point_ledger SET amount=amount+0.01 WHERE id=?',(prize_id,))
        try:service.points.settle(con,state)
        except RuntimeError as exc:assert 'prize ledger' in str(exc)
        else:raise AssertionError('corrupt persisted settlement was trusted')
        con.execute('UPDATE point_ledger SET amount=amount-0.01 WHERE id=?',(prize_id,))
    with db.connect() as con:service.points.settle(con,state)
    with db.connect() as con:
        total=con.execute("SELECT SUM(amount) n FROM point_ledger WHERE kind IN ('sitngo_entry','sitngo_refund','sitngo_prize')").fetchone()['n']
        assert cents(total)==0
    # When a tied prize cannot be split to an exact cent, the extra 0.01pt is
    # assigned by the tournament's randomized seat order, never by account id.
    tiny=event('0.05'); tiny_ids=[add_member(9800+i) for i in range(6)]
    with db.connect() as con:
        for i,u in enumerate(tiny_ids):service.points.write(con,tiny,u,5,'credit',f'tiny-funding-{i}')
    for u in tiny_ids:service.register(tiny,u)
    tiny_state={
        'id':tiny,
        'seats':[{'user_id':u,'seat':seat} for u,seat in zip(tiny_ids,[0,5,4,1,2,3])],
        'tournament':{'status':'finished','entrants':6,'results':[
            {'user_id':u,'place':p} for u,p in zip(tiny_ids,[1,2,2,4,5,6])
        ]},
    }
    with db.connect() as con:service.points.settle(con,tiny_state)
    tiny_awards={r['user_id']:cents(r['prize_points']) for r in tiny_state['tournament']['results']}
    assert tiny_awards[tiny_ids[2]]==5 and tiny_awards[tiny_ids[1]]==4,tiny_awards

    rates=default_payouts();rates['6']=[0,0,0,0,0,100]
    eid=event('0')
    service.update_event(eid,sitngo.SitNGoUpdateIn(entry_fee='10.01',payout_percentages=rates),admin)
    assert service._event_payload(service._row(eid))['payout_percentages']['6']==['0','0','0','0','0','100']
    for bad in ([70,20,0,0,0,0],[-1,101,0,0,0,0],[100,0],[99.999,0.001,0,0,0,0]):
        invalid=default_payouts();invalid['6']=bad
        try:sitngo.SitNGoCreateIn(starts_at='2026-10-01T00:00:00Z',payout_percentages=invalid)
        except ValidationError:pass
        else:raise AssertionError('Invalid payouts accepted')
    assert prize_schedule(6006,6,rates)==[0,0,0,0,0,6006]
    service.register(eid,uid)
    try:service.update_event(eid,sitngo.SitNGoUpdateIn(entry_fee='1'),admin)
    except HTTPException as exc:assert exc.status_code==409
    else:raise AssertionError('Terms changed after registration')
    service.cancel_event(eid,'test',admin)
    # Persisted custom rates, including a zero first prize, reach the ledger.
    custom=service.create_event(sitngo.SitNGoCreateIn(entry_fee='10.01',payout_percentages=rates,
        starts_at=(datetime.now(timezone.utc)+timedelta(minutes=20)).isoformat()),admin)['id']
    with db.connect() as con:
        for i,u in enumerate(ids):service.points.write(con,custom,u,1001,'credit',f'custom-funding-{i}')
    for u in ids:service.register(custom,u)
    final={'id':custom,'tournament':{'status':'finished','entrants':6,'results':[{'user_id':u,'place':i+1} for i,u in enumerate(ids)]}}
    with db.connect() as con:service.points.settle(con,final)
    with db.connect() as con:service.points.settle(con,final)
    assert [cents(r['prize_points']) for r in final['tournament']['results']]==[0,0,0,0,0,6006]
    with db.connect() as con:
        assert cents(con.execute("SELECT SUM(amount) n FROM point_ledger WHERE kind IN ('sitngo_entry','sitngo_refund','sitngo_prize')").fetchone()['n'])==0
    from fastapi.testclient import TestClient
    client=TestClient(production_app.app,base_url='https://testserver')
    body={'starts_at':(datetime.now(timezone.utc)+timedelta(minutes=20)).isoformat(),'entry_fee':'20.50','payout_percentages':rates}
    assert client.post('/api/admin/sitngo',json=body).status_code==401
    token=db.create_session(uid);client.headers['Authorization']='Bearer '+token
    assert client.post('/api/admin/sitngo',json=body).status_code==403
    token=db.create_session(admin);client.headers['Authorization']='Bearer '+token
    response=client.post('/api/admin/sitngo',json=body)
    assert response.status_code==200,response.text
    assert response.json()['entry_fee']==20.5 and response.json()['payout_percentages']['6'][-1]=='100'
    print('JJ_SITNGO_POINTS_OK')

if __name__=='__main__':main()
