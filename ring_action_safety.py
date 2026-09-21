"""Reject stale Ring decisions while preserving timebank boundary fairness."""
from __future__ import annotations
import hashlib
import time
import uuid
from fastapi import HTTPException


def turn_id(state):
    hand=state.get('hand') or {}
    if state.get('status')!='playing' or hand.get('action_seat') is None:
        return None
    if hand.get('turn_id'):
        return hand['turn_id']
    # A pre-release persisted hand must work immediately after restart. Derive
    # a stable token until its next real transition, without writing on reads.
    identity='|'.join(str(hand.get(k,'')) for k in ('id','street','action_seat','action_deadline'))
    return 'ring-legacy-'+hashlib.sha256(identity.encode()).hexdigest()[:32]


def pending_before_deadline(server,state,deadline):
    pending = getattr(server, '_jj_ring_pending_actions', {})
    if not pending:
        return False
    hand=state.get('hand') or {}
    actor=next((p for p in state.get('seats',[]) if p.get('seat')==hand.get('action_seat')),None)
    if not actor:return False
    arrivals=pending.get((state.get('id'),turn_id(state),actor['user_id']),[])
    return any(arrival<=deadline for arrival in arrivals)


def install(server,engine):
    if getattr(server,'_jj_ring_action_safety',False):return
    server._jj_ring_action_safety=True
    server._jj_ring_pending_actions={}
    original_deadline=server.arm_action_deadline
    def arm_action_deadline(state,seconds=30):
        result=original_deadline(state,seconds)
        if not state.get('tournament') and state.get('hand'):
            state['hand']['turn_id']=uuid.uuid4().hex if state.get('status')=='playing' and state['hand'].get('action_seat') is not None else None
        return result
    server.arm_action_deadline=arm_action_deadline
    original_public=engine.public_state
    def public_state(state,viewer_id=None):
        value=original_public(state,viewer_id)
        if not state.get('tournament'):
            value['turn_id']=turn_id(state)
            if value.get('hand'):value['hand']['turn_id']=value['turn_id']
        return value
    engine.public_state=server.public_state=public_state

    async def guarded_action(table_id,payload,user):
        received=time.time()
        receipt=str(payload.action_id or '').strip()
        hand_id=str(getattr(payload,'hand_id',None) or '').strip()
        token=str(getattr(payload,'turn_id',None) or '').strip()
        if not receipt or not hand_id or not token:
            raise HTTPException(409,'画面を再読み込みしてから操作してください')
        key=(table_id,token,user['id'])
        arrivals=server._jj_ring_pending_actions.setdefault(key,[])
        arrivals.append(received)
        try:
            async with server.get_table_lock(table_id):
                state=server.load_table(table_id)
                processed=list(state.get('_processed_action_ids') or [])
                receipt_key=f"{user['id']}:{receipt}"
                if receipt_key in processed:
                    return server.public_state(state,user['id'])
                hand=state.get('hand') or {}
                if hand_id!=str(hand.get('id') or '') or token!=turn_id(state):
                    raise HTTPException(409,'操作順が更新されました。最新の卓状態を確認してください')
                from runtime_performance import _deadline_epoch
                deadline=_deadline_epoch(hand.get('action_deadline'))
                if deadline is None or received>deadline:
                    raise HTTPException(409,'操作時間を過ぎました。最新の状態を確認してください')
                try:server.apply_action(state,user['id'],payload.action,payload.amount)
                except ValueError as exc:raise HTTPException(400,str(exc)) from exc
                state['_processed_action_ids']=(processed+[receipt_key])[-120:]
                server.arm_action_deadline(state)
                server.save_table(state)
                result=server.public_state(state,user['id'])
            await server.hub.broadcast(table_id)
            return result
        finally:
            arrivals.remove(received)
            if not arrivals:server._jj_ring_pending_actions.pop(key,None)
    # Sit&Go's front route delegates all non-tournament actions here and owns
    # its existing hand/turn request model. No tournament protocol is replaced.
    server.action=guarded_action
