"""Transactional tournament escrow and awards, using integer hundredths."""
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import json
import uuid
from fastapi import HTTPException


def cents(value):
    return int((Decimal(str(value or 0))*100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def default_payouts():
    return {str(n): ([100] + [0]*(n-1) if n < 6 else [70,30,0,0,0,0]) for n in range(2,7)}


def validate_payouts(value):
    if set(value) != {str(n) for n in range(2,7)}:
        raise ValueError('2〜6人それぞれの配当率を設定してください')
    for n, rates in value.items():
        if len(rates) != int(n):raise ValueError('順位数が不正です')
        decimals=[Decimal(str(x)) for x in rates]
        if any(not x.is_finite() or x < 0 or x > 100 or x*100 != int(x*100) for x in decimals):
            raise ValueError('配当率は0〜100%、小数2桁までです')
        if sum(decimals) != 100:raise ValueError('配当率の合計を100%にしてください')
    return value


def prize_schedule(pool, entrants, payouts=None):
    if entrants < 2:return []
    rates=(payouts or default_payouts())[str(entrants)]
    units=[int(Decimal(str(x))*100) for x in rates]
    values=[pool*x//10000 for x in units]
    order=sorted(range(entrants),key=lambda i:(-(pool*units[i]%10000),i))
    for i in order[:pool-sum(values)]:values[i]+=1
    return values


class TournamentPoints:
    def __init__(self, service):
        self.service,self.db=service,service.db
        with self.db.connect() as con:
            con.execute('CREATE TABLE IF NOT EXISTS sitngo_payout_settings(event_id TEXT PRIMARY KEY REFERENCES sitngo_events(id), payouts_json TEXT NOT NULL)')
            con.execute('''CREATE TABLE IF NOT EXISTS sitngo_terms(event_id TEXT PRIMARY KEY REFERENCES sitngo_events(id), fee_cents BIGINT NOT NULL CHECK(fee_cents>=0))''')
            con.execute('''CREATE TABLE IF NOT EXISTS sitngo_payments(event_id TEXT NOT NULL REFERENCES sitngo_events(id), user_id BIGINT NOT NULL REFERENCES users(id), entry_tx TEXT NOT NULL REFERENCES point_ledger(id), fee_cents BIGINT NOT NULL, refunded INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(event_id,user_id))''')
            con.execute('''CREATE TABLE IF NOT EXISTS sitngo_settlements(event_id TEXT PRIMARY KEY REFERENCES sitngo_events(id), awards_json TEXT NOT NULL, created_at TEXT NOT NULL)''')

    def fee(self,con,eid):
        row=con.execute('SELECT fee_cents FROM sitngo_terms WHERE event_id=?',(eid,)).fetchone()
        return int(row['fee_cents']) if row else 0

    def payouts(self,con,eid):
        row=con.execute('SELECT payouts_json FROM sitngo_payout_settings WHERE event_id=?',(eid,)).fetchone()
        try:
            raw=json.loads(row['payouts_json']) if row else default_payouts()
            validated=validate_payouts(raw)
        except (ValueError,TypeError,json.JSONDecodeError,InvalidOperation) as exc:
            raise RuntimeError('Sit&Go payout configuration is invalid; tournament start/settlement refused') from exc
        return {str(n):[str(v) for v in rates] for n,rates in validated.items()}

    def configure(self,con,eid,fee,payouts):
        validate_payouts(payouts)
        rates={n:[str(v) for v in r] for n,r in payouts.items()}
        con.execute('INSERT INTO sitngo_terms(event_id,fee_cents) VALUES (?,?) ON CONFLICT(event_id) DO UPDATE SET fee_cents=excluded.fee_cents',(eid,cents(fee)))
        con.execute('INSERT INTO sitngo_payout_settings(event_id,payouts_json) VALUES (?,?) ON CONFLICT(event_id) DO UPDATE SET payouts_json=excluded.payouts_json',(eid,json.dumps(rates)))

    def assert_start_ready(self,con,eid,participants):
        # Validate locked payout terms before the first card is dealt. A corrupt
        # persisted configuration must never be discovered only at settlement.
        self.payouts(con,eid)
        fee=self.fee(con,eid)
        expected={int(uid) for uid in participants}
        rows=con.execute(
            'SELECT user_id,entry_tx,fee_cents,refunded FROM sitngo_payments WHERE event_id=?',
            (eid,),
        ).fetchall()
        active={int(r['user_id']):r for r in rows if not int(r['refunded'])}

        if fee==0:
            if active:
                raise RuntimeError('Free Sit&Go has unexpected active entry escrow; start refused')
            return

        if set(active)!=expected:
            raise RuntimeError('Tournament escrow is incomplete; start refused')
        for uid,row in active.items():
            if int(row['fee_cents'])!=fee:
                raise RuntimeError('Tournament escrow fee mismatch; start refused')
            ledger=con.execute(
                'SELECT user_id,amount,kind FROM point_ledger WHERE id=?',
                (row['entry_tx'],),
            ).fetchone()
            if (
                not ledger
                or int(ledger['user_id'])!=uid
                or str(ledger['kind'])!='sitngo_entry'
                or cents(ledger['amount'])!=-fee
            ):
                raise RuntimeError('Tournament escrow ledger mismatch; start refused')

    def describe(self,eid,count):
        with self.db.connect() as con:
            fee=self.fee(con,eid);rates=self.payouts(con,eid)
            locked=con.execute('SELECT 1 FROM sitngo_registrations WHERE event_id=? LIMIT 1',(eid,)).fetchone() is not None
        pool=fee*count
        return dict(entry_fee=fee/100,prize_points=pool/100,prizes=[v/100 for v in prize_schedule(pool,count,rates)],payout_percentages=rates,points_editable=not locked,reentry=False)

    def statement(self,eid,uid):
        """Return the viewer's ledger-backed Sit&Go accounting summary."""
        with self.db.connect() as con:
            payment=con.execute(
                'SELECT entry_tx,fee_cents,refunded FROM sitngo_payments WHERE event_id=? AND user_id=?',
                (eid,uid),
            ).fetchone()
            prize=con.execute(
                "SELECT amount FROM point_ledger WHERE id=? AND user_id=? AND kind='sitngo_prize'",
                (f'sng-prize-{eid}-{uid}',uid),
            ).fetchone()
            if not payment and not prize:
                return None
            entry=0
            refund=0
            fee=int(payment['fee_cents']) if payment else 0
            if payment:
                row=con.execute(
                    "SELECT amount FROM point_ledger WHERE id=? AND user_id=? AND kind='sitngo_entry'",
                    (payment['entry_tx'],uid),
                ).fetchone()
                if row:
                    entry=cents(row['amount'])
                row=con.execute(
                    "SELECT amount FROM point_ledger WHERE id=? AND user_id=? AND kind='sitngo_refund'",
                    ('sng-refund-'+str(payment['entry_tx']),uid),
                ).fetchone()
                if row:
                    refund=cents(row['amount'])
            award=cents(prize['amount']) if prize else 0
            settled=con.execute(
                'SELECT 1 FROM sitngo_settlements WHERE event_id=?',
                (eid,),
            ).fetchone() is not None
        return dict(
            entry_fee=fee/100,
            entry_points=entry/100,
            refund_points=refund/100,
            prize_points=award/100,
            net_points=(entry+refund+award)/100,
            refunded=bool(payment and int(payment['refunded'])),
            settled=settled,
        )

    def balance(self,con,uid):
        user=con.execute("SELECT COALESCE(NULLIF(ranking_name,''),name) name FROM users WHERE id=?",(uid,)).fetchone()
        if not user:raise HTTPException(404,'アカウントが見つかりません')
        name=user['name']
        if con.execute("SELECT COUNT(*) n FROM users WHERE COALESCE(NULLIF(ranking_name,''),name)=?",(name,)).fetchone()['n']!=1:
            raise HTTPException(409,'ランキング名が重複しています。管理者に確認してください')
        start=getattr(self.service.server,'FALL_SEASON_START','2026-09-01')
        end=getattr(self.service.server,'FALL_SEASON_END','2027-04-01')
        club=con.execute("SELECT COALESCE(SUM(points),0) n FROM entries WHERE name=? AND name<>'運営調整' AND date>=? AND date<?",(name,start,end)).fetchone()['n']
        online=con.execute('''SELECT COALESCE(SUM(r.points),0) n FROM online_hand_results r JOIN online_hands h ON h.hand_id=r.hand_id WHERE r.ranking_name=? AND COALESCE(h.voided,0)=0 AND h.played_at>=? AND h.played_at<?''',(name,start,end)).fetchone()['n']
        ledger=con.execute('SELECT COALESCE(SUM(amount),0) n FROM point_ledger WHERE user_id=? AND effective_at>=? AND effective_at<?',(uid,start,end)).fetchone()['n']
        return cents(club)+cents(online)+cents(ledger)

    def write(self,con,eid,uid,amount,kind,txid,reversal=None):
        event=con.execute('SELECT name,created_by FROM sitngo_events WHERE id=?',(eid,)).fetchone()
        stamp=self.db.utcnow()
        con.execute('''INSERT INTO point_ledger(id,user_id,amount,kind,reason,effective_at,created_by,created_at,reversal_of) VALUES (?,?,?,?,?,?,?,?,?)''',(txid,uid,str(Decimal(amount)/100),kind,f"Sit&Go {event['name']} ({eid})",stamp,event['created_by'],stamp,reversal))

    def charge(self,con,eid,uid):
        fee=self.fee(con,eid)
        if not fee:return
        # Entry is a commitment, not a balance-gated purchase. The official
        # ledger may therefore become negative; keep the account lock so
        # concurrent registration/account writes remain serialized.
        con.execute('UPDATE users SET id=id WHERE id=?',(uid,))
        tx='sng-entry-'+uuid.uuid4().hex
        self.write(con,eid,uid,-fee,'sitngo_entry',tx)
        con.execute('''INSERT INTO sitngo_payments(event_id,user_id,entry_tx,fee_cents,refunded) VALUES (?,?,?,?,0) ON CONFLICT(event_id,user_id) DO UPDATE SET entry_tx=excluded.entry_tx,fee_cents=excluded.fee_cents,refunded=0''',(eid,uid,tx,fee))

    def refund(self,con,eid,uid=None):
        query='SELECT * FROM sitngo_payments WHERE event_id=? AND refunded=0';args=[eid]
        if uid is not None:query+=' AND user_id=?';args.append(uid)
        for row in con.execute(query,args).fetchall():
            # Database-level claim: exactly-once refunds must not depend on a
            # process-local/event lock being the only serialization boundary.
            claimed=con.execute(
                'UPDATE sitngo_payments SET refunded=1 WHERE event_id=? AND user_id=? AND refunded=0',
                (eid,row['user_id']),
            )
            if int(getattr(claimed,'rowcount',0) or 0)!=1:
                continue
            self.write(con,eid,row['user_id'],int(row['fee_cents']),'sitngo_refund','sng-refund-'+row['entry_tx'],row['entry_tx'])

    def _verify_settlement(self,con,eid,awards):
        rows=con.execute('SELECT user_id,fee_cents FROM sitngo_payments WHERE event_id=? AND refunded=0',(eid,)).fetchall()
        pool=sum(int(r['fee_cents']) for r in rows)
        if sum(int(v) for v in awards.values())!=pool:
            raise RuntimeError('Persisted tournament settlement does not match escrow')
        ledger=con.execute(
            "SELECT user_id,amount FROM point_ledger WHERE kind='sitngo_prize' AND id LIKE ?",
            (f'sng-prize-{eid}-%',),
        ).fetchall()
        actual={str(r['user_id']):cents(r['amount']) for r in ledger}
        expected={str(uid):int(amount) for uid,amount in awards.items() if int(amount)}
        if actual!=expected:
            raise RuntimeError('Persisted tournament settlement does not match prize ledger')

    def settle(self,con,state):
        t=state['tournament'];eid=state['id']
        if t['status']!='finished':return
        prior=con.execute('SELECT awards_json FROM sitngo_settlements WHERE event_id=?',(eid,)).fetchone()
        if prior:
            awards=json.loads(prior['awards_json'])
            self._verify_settlement(con,eid,awards)
        else:
            fee=self.fee(con,eid)
            rows=con.execute('SELECT user_id,fee_cents FROM sitngo_payments WHERE event_id=? AND refunded=0',(eid,)).fetchall()
            results=t['results']
            if len(results)!=t['entrants'] or len({r['user_id'] for r in results})!=t['entrants']:
                raise RuntimeError('Incomplete tournament results; settlement refused')
            if fee and ({r['user_id'] for r in rows}!={r['user_id'] for r in results} or any(int(r['fee_cents'])!=fee for r in rows)):
                raise RuntimeError('Tournament escrow mismatch; settlement refused')
            pool=sum(int(r['fee_cents']) for r in rows);schedule=prize_schedule(pool,t['entrants'],self.payouts(con,eid))
            awards={str(r['user_id']):0 for r in results}
            seat_order={int(p['user_id']):int(p.get('seat',999)) for p in state.get('seats',[])}
            for place in sorted({r['place'] for r in results}):
                tied=sorted(
                    (r for r in results if r['place']==place),
                    key=lambda r:(seat_order.get(int(r['user_id']),999),int(r['user_id'])),
                )
                total=sum(schedule[place-1:place-1+len(tied)]);share,remainder=divmod(total,len(tied))
                for i,r in enumerate(tied):awards[str(r['user_id'])]=share+int(i<remainder)
            if sum(awards.values())!=pool:raise RuntimeError('Tournament awards do not conserve points')
            for uid,amount in awards.items():
                if amount:self.write(con,eid,int(uid),amount,'sitngo_prize',f'sng-prize-{eid}-{uid}')
            con.execute('INSERT INTO sitngo_settlements(event_id,awards_json,created_at) VALUES (?,?,?)',(eid,json.dumps(awards),self.db.utcnow()))
            self._verify_settlement(con,eid,awards)
        for result in t['results']:result['prize_points']=awards[str(result['user_id'])]/100
        t['prize_points']=sum(awards.values())/100;t['points_settled']=True
