"""Single-table tournaments using an isolated instance of the canonical engine.

No tournament state is written through cash-game settlement. The shared client
and authenticated table transport remain the same as the ring game.
"""
from __future__ import annotations

import asyncio
import contextvars
import importlib.util
import json
import time
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, HTTPException
from starlette.responses import JSONResponse

from rake_settlement_fix import refund_uncalled_contribution


def make_engine():
    spec = importlib.util.spec_from_file_location(
        'jj_sitngo_engine', Path(__file__).parent / 'materialized_v1244/poker_engine.py')
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    # Separate module globals prevent a tournament's zero rake / dead ante from
    # affecting ring settlement, including simultaneous requests in other threads.
    current = contextvars.ContextVar('sitngo_dealing', default=None)
    post_blind, start = engine._post_blind, engine.start_hand
    pots, showdown, award = engine._build_side_pots, engine._showdown, engine._award_uncontested
    engine._rake_amount = lambda state, amount: 0

    def blind(player, amount):
        paid = post_blind(player, amount)
        state = current.get()
        if state is not None and amount == state['big_blind']:
            ante = min(player['stack'], state['tournament']['bb_ante'])
            player['stack'] -= ante
            player['all_in'] = player['stack'] == 0
            state['_ante_paid'] = ante
        return paid

    def deal(state):
        state['_ante_paid'] = 0
        for p in state['seats']:
            p.update(sitting_out=False, sit_out_next=False, leave_after_hand=False)
        token = current.set(state)
        try:
            return start(state)
        finally:
            current.reset(token)

    def side_pots(state):
        result = pots(state)
        ante = state.get('_ante_paid', 0)
        if ante:
            # Ante is dead money, not a call credit or an unmatched contribution.
            result.insert(0, {'amount': ante, 'eligible': engine._in_hand_players(state)})
        return result

    def settle(state):
        refund_uncalled_contribution(state)
        showdown(state)
        state['_ante_paid'] = 0
        engine._attach_net_results(state)

    def uncontested(state, *args, **kwargs):
        refund_uncalled_contribution(state)
        ante = state.get('_ante_paid', 0)
        gross = sum(p.get('contributed', 0) for p in state['seats']) + ante
        winner = engine._in_hand_players(state)[0]
        award(state, *args, **kwargs)
        winner['stack'] += ante
        state['_ante_paid'] = 0
        result = state['last_result']
        result['winners'][0]['amount'] += ante
        result.update(gross_pot=gross, rake=0)
        engine._attach_net_results(state)

    engine._post_blind, engine.start_hand = blind, deal
    engine._build_side_pots, engine._showdown, engine._award_uncontested = side_pots, settle, uncontested
    return engine


class TournamentRuntime:
    def __init__(self, service, ring_engine):
        self.service, self.db, self.server = service, service.db, service.server
        self.engine = make_engine()
        self.event = None
        self.loop = None
        self._runner_guard = threading.Lock()
        with self.db.connect() as con:
            con.execute('''CREATE TABLE IF NOT EXISTS sitngo_games(
                event_id TEXT PRIMARY KEY REFERENCES sitngo_events(id),
                state_json TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL)''')
            con.execute('''CREATE TABLE IF NOT EXISTS sitngo_hands(
                hand_id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES sitngo_events(id),
                state_json TEXT NOT NULL, created_at TEXT NOT NULL)''')
            con.execute("""CREATE TABLE IF NOT EXISTS sitngo_messages(
                id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES sitngo_events(id),
                user_id INTEGER NOT NULL, author_name TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL)""")
        self.install_dispatch(ring_engine)
        self.install_routes()

    def signal(self):
        loop, event = self.loop, self.event
        if loop is not None and event is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(event.set)
            except RuntimeError:
                if not loop.is_closed():
                    raise

    def create(self, con, event, participants, now):
        eid = event['id']
        if con.execute('SELECT event_id FROM sitngo_games WHERE event_id=?', (eid,)).fetchone():
            return
        e = self.engine
        state = e.blank_table_state(table_id=eid, name=event['name'], max_seats=6,
            small_blind=100, big_blind=200, min_buyin=event['starting_stack'],
            max_buyin=event['starting_stack'])
        for uid, seat in participants:
            user = con.execute('SELECT name FROM users WHERE id=?', (uid,)).fetchone()
            e.seat_player(state, user_id=uid, name=user['name'], seat=seat, stack=event['starting_stack'])
        state.update(session_active=True, rake_percent=0, rake_cap=0, _revision=0,
            tournament={'event_id': eid, 'status': 'running', 'entry_fee': 0, 'prize_points': 0,
                'started_at_epoch': now.timestamp(), 'clock_at_epoch': now.timestamp(),
                'elapsed_seconds': 0, 'level': 1, 'bb_ante': 200,
                'structure': json.loads(event['structure_json']), 'results': [],
                'entrants': len(participants), 'total_chips': len(participants)*event['starting_stack']})
        e.start_hand(state)
        self.server.arm_action_deadline(state)
        con.execute('INSERT INTO sitngo_games(event_id,state_json,revision,updated_at) VALUES (?,?,0,?)',
            (eid, json.dumps(state, ensure_ascii=False), self.db.utcnow()))
        self.signal()

    def load(self, eid):
        with self.db.connect() as con:
            row = con.execute('SELECT state_json FROM sitngo_games WHERE event_id=?', (eid,)).fetchone()
        if not row:
            raise HTTPException(404, '大会テーブルの準備中です')
        return json.loads(row['state_json'])

    def finish(self, state):
        t = state['tournament']
        if state['status'] == 'playing' or t['status'] == 'finished':
            return
        hand_id = (state.get('hand') or {}).get('id')
        if state.get('_ranked_hand') == hand_id:
            return
        state['_ranked_hand'] = hand_id
        existing = {x['user_id'] for x in t['results']}
        busted = [p for p in state['seats'] if p['stack'] == 0 and p['user_id'] not in existing]
        starts = (state.get('hand') or {}).get('starting_stacks', {})
        alive = [p for p in state['seats'] if p['stack'] > 0]
        for p in busted:
            stack = starts.get(str(p['user_id']), 0)
            place = len(alive) + 1 + sum(starts.get(str(q['user_id']), 0) > stack for q in busted)
            t['results'].append({'user_id': p['user_id'], 'name': p['name'], 'place': place,
                'hand_no': state['hand_no'], 'starting_stack': stack, 'prize_points': 0})
        if len(alive) == 1:
            p = alive[0]
            t['results'].append({'user_id': p['user_id'], 'name': p['name'], 'place': 1,
                'hand_no': state['hand_no'], 'starting_stack': p['stack'], 'prize_points': 0})
            t.update(status='finished', finished_at=self.db.utcnow())
            state.update(session_active=False, next_hand_at_epoch=None)
        elif len(alive) >= 2:
            state['session_active'] = True
            state['next_hand_at_epoch'] = max(time.time()+1.6, float(state.get('showdown_hold_until_epoch') or 0))

    def save(self, state, *, notify=True):
        self.finish(state)
        t, hand = state['tournament'], state.get('hand') or {}
        chips = sum(p['stack'] + p.get('contributed', 0) for p in state['seats']) + state.get('_ante_paid', 0)
        if chips != t['total_chips'] or any(p['stack'] < 0 for p in state['seats']):
            raise RuntimeError('Sit&Go chip conservation failed')
        revision = state['_revision']
        state['_revision'] += 1
        with self.db.connect() as con:
            updated = con.execute('UPDATE sitngo_games SET state_json=?,revision=?,updated_at=? WHERE event_id=? AND revision=?',
                (json.dumps(state, ensure_ascii=False), state['_revision'], self.db.utcnow(), state['id'], revision))
            if updated.rowcount != 1:
                raise HTTPException(409, '大会の状態が更新されました。再接続してください')
            self.service.points.settle(con, state)
            if t['status'] == 'finished':
                con.execute('UPDATE sitngo_games SET state_json=? WHERE event_id=?',
                    (json.dumps(state, ensure_ascii=False), state['id']))
            if hand.get('phase') == 'complete':
                # Private history is never returned without viewer-specific redaction.
                con.execute('INSERT OR IGNORE INTO sitngo_hands(hand_id,event_id,state_json,created_at) VALUES (?,?,?,?)',
                    (hand['id'], state['id'], json.dumps(state, ensure_ascii=False), self.db.utcnow()))
            if t['status'] == 'finished':
                con.execute("UPDATE sitngo_events SET status='finished',updated_at=? WHERE id=?",
                    (self.db.utcnow(), state['id']))
            for result in t['results']:
                con.execute("UPDATE sitngo_registrations SET status='finished' WHERE event_id=? AND user_id=?",
                    (state['id'], result['user_id']))
        if notify:
            self.signal()

    def public(self, state, viewer=None):
        value = self.engine.public_state(state, viewer)
        for key in list(value):
            if key.startswith('_'):
                value.pop(key)
        t = dict(state['tournament'])
        now = time.time()
        elapsed = t['elapsed_seconds'] + max(0, now-t['clock_at_epoch']) if t['status']=='running' else t['elapsed_seconds']
        levels = t['structure']
        boundary = sum(x['minutes']*60 for x in levels[:t['level']])
        t['next_level_at'] = datetime.fromtimestamp(now+max(0,boundary-elapsed), timezone.utc).isoformat() if t['level'] < len(levels) else None
        t['remaining'] = sum(p['stack'] > 0 or p.get('in_hand',False) and not p.get('folded',False) for p in state['seats'])
        t['results'] = sorted(t['results'], key=lambda x:(x['place'], x['user_id']))
        t['ante_paid'] = state.get('_ante_paid', 0)
        if t['status'] == 'finished' and viewer is not None:
            t['point_statement'] = self.service.points.statement(state['id'], int(viewer))
        value['tournament'] = t
        if t['status'] == 'finished':
            value['legal'] = {'can_act':False}
        return value

    def install_dispatch(self, ring):
        s = self.server
        load, save, public, action = s.load_table, s.save_table, s.public_state, s.apply_action
        ring_public = ring.public_state
        s.load_table = lambda tid: self.load(tid) if tid.startswith('sng-') else load(tid)
        s.save_table = lambda state: self.save(state) if state.get('tournament') else save(state)
        s.public_state = lambda state, viewer=None: self.public(state, viewer) if state.get('tournament') else public(state, viewer)
        ring.public_state = lambda state, viewer=None: self.public(state, viewer) if state.get('tournament') else ring_public(state, viewer)
        s.apply_action = lambda state, uid, kind, amount=None: self.engine.apply_action(state, uid, kind, amount) if state.get('tournament') else action(state, uid, kind, amount)
        messages = s.get_messages
        s.get_messages = lambda tid: self.messages(tid) if tid.startswith('sng-') else messages(tid)
        seated = s.seated_table_for_user
        self.ring_seated = seated
        def membership(uid, exclude=None):
            ring_id = seated(uid, exclude=exclude)
            if ring_id: return ring_id
            with self.db.connect() as con:
                row = con.execute("SELECT r.event_id FROM sitngo_registrations r JOIN sitngo_events e ON e.id=r.event_id WHERE r.user_id=? AND r.status IN ('registered','active') AND e.status IN ('scheduled','registration_open','starting','running') AND e.id<>? LIMIT 1", (uid, exclude or '')).fetchone()
            return row['event_id'] if row else None
        s.seated_table_for_user = membership
        # Ring endpoints remain registered. Tournament-specific management actions
        # must never reach their cash-game implementation, even from stale clients.
        @self.service.app.middleware('http')
        async def guard(request, call_next):
            parts = request.url.path.strip('/').split('/')
            if len(parts) == 4 and parts[:2] == ['api','tables'] and parts[2].startswith('sng-') and request.method == 'POST':
                if parts[3] not in {'action','chat'}:
                    return JSONResponse({'detail':'大会では席の変更・リバイ・途中退席はできません。ロビーへ戻っても参加は継続します。'}, status_code=409)
            return await call_next(request)

    def messages(self, eid):
        with self.db.connect() as con:
            rows=con.execute('SELECT id,author_name,body,created_at FROM sitngo_messages WHERE event_id=? ORDER BY created_at DESC,id DESC LIMIT 50',(eid,)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def install_routes(self):
        from pydantic import BaseModel, Field
        import uuid
        s=self.server
        app=self.service.app
        # Reuse the same chat endpoint and UI, with separate tournament storage.
        async def chat(table_id: str, payload: s.ChatIn, user=Depends(s.current_user)):
            if not table_id.startswith('sng-'):
                return await s.table_chat(table_id,payload,user)
            self.load(table_id)
            body=payload.body.strip()
            if not body: raise HTTPException(400,'メッセージを入力してください')
            with self.db.connect() as con:
                participant=con.execute(
                    "SELECT status FROM sitngo_registrations WHERE event_id=? AND user_id=? AND status IN ('active','finished')",
                    (table_id,user['id']),
                ).fetchone()
                if not participant and str(user.get('role') or '') != 'admin':
                    raise HTTPException(403,'大会チャットは参加者のみ送信できます')
                con.execute('INSERT INTO sitngo_messages(id,event_id,user_id,author_name,body,created_at) VALUES (?,?,?,?,?,?)',
                    (uuid.uuid4().hex,table_id,user['id'],user['name'],body,self.db.utcnow()))
            await s.hub.broadcast(table_id)
            return {'ok':True}
        from pydantic import create_model
        action_model=create_model('SitNGoActionIn', __base__=s.ActionIn, hand_id=(str | None,None))
        async def action(table_id, payload, user=Depends(s.current_user)):
            if not table_id.startswith('sng-'):
                return await s.action(table_id,payload,user)
            async with s.get_table_lock(table_id):
                state=self.load(table_id)
                receipt=str(payload.action_id or '').strip()
                if not receipt or not payload.hand_id:
                    raise HTTPException(409,'画面を再読み込みしてから操作してください')
                key=f"{user['id']}:{receipt}"
                processed=state.get('_processed_action_ids',[])
                if key in processed:
                    return self.public(state,user['id'])
                if payload.hand_id != (state.get('hand') or {}).get('id'):
                    raise HTTPException(409,'次のハンドに進みました。現在の手札を確認してください')
                try:
                    self.engine.apply_action(state,user['id'],payload.action,payload.amount)
                except ValueError as exc:
                    raise HTTPException(400,str(exc)) from exc
                state['_processed_action_ids']=(processed+[key])[-120:]
                s.arm_action_deadline(state)
                self.save(state)
            await s.hub.broadcast(table_id)
            return self.public(state,user['id'])
        action.__annotations__={'table_id':str,'payload':action_model}
        app.post('/api/tables/{table_id}/action')(action)
        action_route=app.router.routes.pop()
        action_index=next(i for i,r in enumerate(app.router.routes) if getattr(r,'path','')=='/api/tables/{table_id}/action')
        app.router.routes.insert(action_index,action_route)
        # Future annotations cannot resolve function-local `s` in FastAPI.
        chat.__annotations__={'table_id':str,'payload':s.ChatIn}
        app.post('/api/tables/{table_id}/chat')(chat)
        route=app.router.routes.pop()
        index=next(i for i,r in enumerate(app.router.routes) if getattr(r,'path','')=='/api/tables/{table_id}/chat')
        app.router.routes.insert(index,route)

        @app.get('/api/sitngo/{event_id}/history')
        def history(event_id: str,user=Depends(s.current_user)):
            self.load(event_id)
            with self.db.connect() as con:
                rows=con.execute('SELECT state_json FROM sitngo_hands WHERE event_id=? ORDER BY created_at DESC,hand_id DESC LIMIT 30',(event_id,)).fetchall()
            return {'hands':[self.public(json.loads(r['state_json']),int(user['id'])) for r in rows]}

    def recover_legacy(self):
        # Phase 1 marked events running without creating a poker hand. Build
        # their first real table once, retaining their assigned seats.
        with self.service._lock, self.db.connect() as con:
            rows=con.execute("SELECT e.* FROM sitngo_events e LEFT JOIN sitngo_games g ON g.event_id=e.id WHERE e.status='running' AND g.event_id IS NULL ORDER BY e.starts_at").fetchall()
            for row in rows:
                event=dict(row)
                regs=con.execute("SELECT user_id,seat FROM sitngo_registrations WHERE event_id=? AND status='active'",(event['id'],)).fetchall()
                if len(regs)>=2:
                    self.create(con,event,[(r['user_id'],r['seat']) for r in regs],datetime.now(timezone.utc))

    async def tick(self, eid, *, now=None, recover=False):
        s = self.server
        now = time.time() if now is None else now
        async with s.get_table_lock(eid):
            state = self.load(eid)
            t = state['tournament']
            if t['status'] != 'running':
                return None
            previous = t['clock_at_epoch']
            # On process restart do not consume server downtime as player time.
            if recover:
                delta = max(0, now-previous)
                h = state.get('hand') or {}
                if h.get('action_deadline'):
                    deadline = datetime.fromisoformat(h['action_deadline']).timestamp()+delta
                    h['action_deadline'] = datetime.fromtimestamp(deadline,timezone.utc).isoformat()
                for obj,key in ((h,'runout_due_at_epoch'),(state,'next_hand_at_epoch'),(state,'showdown_hold_until_epoch')):
                    if obj.get(key): obj[key] += delta
            else:
                t['elapsed_seconds'] += max(0,now-previous)
            t['clock_at_epoch'] = now
            hand = state.get('hand') or {}
            if not recover and state['status'] == 'playing':
                if hand.get('forced_runout') and float(hand.get('runout_due_at_epoch') or 0) <= now:
                    self.engine.advance_forced_runout(state)
                elif hand.get('action_deadline') and datetime.fromisoformat(hand['action_deadline']).timestamp() <= now:
                    p = next((p for p in state['seats'] if p['seat']==hand.get('action_seat')),None)
                    if p:
                        legal = self.engine.legal_actions(state,p['user_id'])
                        self.engine.apply_action(state,p['user_id'],'check' if legal.get('can_check') else 'fold')
                        s.arm_action_deadline(state)
            elif not recover and state['status'] == 'waiting' and float(state.get('next_hand_at_epoch') or 0) <= now:
                elapsed, index = t['elapsed_seconds'], 0
                for i,level in enumerate(t['structure']):
                    index=i
                    if elapsed < level['minutes']*60: break
                    elapsed -= level['minutes']*60
                level=t['structure'][index]
                t.update(level=index+1, bb_ante=level['bb_ante'])
                state.update(small_blind=level['small_blind'], big_blind=level['big_blind'])
                self.engine.start_hand(state)
                s.arm_action_deadline(state)
            # Persist a heartbeat every 5 seconds, plus every exact game deadline.
            self.save(state, notify=False)
            h=state.get('hand') or {}
            deadlines=[now+5]
            if state['status']=='playing':
                if h.get('action_deadline'): deadlines.append(datetime.fromisoformat(h['action_deadline']).timestamp())
                if h.get('runout_due_at_epoch'): deadlines.append(h['runout_due_at_epoch'])
            elif t['status']=='running': deadlines.append(state.get('next_hand_at_epoch') or now+1.6)
        await s.hub.broadcast(eid)
        return min(deadlines)

    async def run(self):
        # An app can have overlapping lifespan contexts (e.g. concurrent test
        # clients). Only one scheduler may own its events and table locks.
        while not self._runner_guard.acquire(blocking=False):
            await asyncio.sleep(.1)
        self.loop=asyncio.get_running_loop()
        self.event=asyncio.Event()
        recovered=set()
        try:
            self.recover_legacy()
            while True:
                self.event.clear()
                try:
                    self.service.reconcile()
                except Exception as exc:
                    import resilience
                    import sitngo_observability
                    resilience.record_error(self.db,'sitngo_reconcile',f'{type(exc).__name__}: {exc}',path='scheduler')
                    sitngo_observability.record(self.db,'reconcile_error')
                    await asyncio.sleep(1)
                    continue
                with self.db.connect() as con:
                    ids=[r['id'] for r in con.execute("SELECT id FROM sitngo_events WHERE status='running'").fetchall()]
                due=time.time()+5
                for eid in ids:
                    try:
                        value=await self.tick(eid,recover=eid not in recovered)
                        recovered.add(eid)
                        if value is not None: due=min(due,value)
                    except Exception as exc:
                        import resilience
                        import sitngo_observability
                        resilience.record_error(self.db,'sitngo_lifecycle',f'{type(exc).__name__}: {exc}',path=eid)
                        sitngo_observability.record(self.db,'tick_error')
                # tick() does not signal its own checkpoint. Preserve signals
                # from actions arriving while a broadcast yielded control.
                if self.event.is_set():
                    continue
                try:
                    await asyncio.wait_for(self.event.wait(),timeout=max(.05,due-time.time()))
                except TimeoutError:
                    pass
        finally:
            self.event=None
            self.loop=None
            self._runner_guard.release()
