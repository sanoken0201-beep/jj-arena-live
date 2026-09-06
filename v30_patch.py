from __future__ import annotations
from pathlib import Path
import re


def apply(root: Path) -> None:
    _server(root / 'server.py')
    _app(root / 'static' / 'app.js')
    _index(root / 'static' / 'index.html')
    _sw(root / 'static' / 'sw.js')


def _replace_once(s: str, old: str, new: str, label: str) -> str:
    count = s.count(old)
    if count != 1:
        raise RuntimeError(f'v1.16.1 {label} target mismatch: {count}')
    return s.replace(old, new, 1)


def _server(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    s = s.replace('version="1.16.0"', 'version="1.16.1"').replace('"version":"1.16.0"', '"version":"1.16.1"')
    s = s.replace('request.url.query == "v=29"', 'request.url.query == "v=30"')

    # READY is consent for the first deal, so it must remain revocable until the
    # deal actually starts.
    s = _replace_once(
        s,
        'mode: str = Field(pattern="^(sitout|cancel_sitout|return|rebuy)$")',
        'mode: str = Field(pattern="^(sitout|cancel_sitout|return|rebuy|unready)$")',
        'presence pattern',
    )
    old_cancel = '''        elif mode == "cancel_sitout":\n            player["sit_out_next"] = False\n        elif mode == "return":\n'''
    new_cancel = '''        elif mode == "cancel_sitout":\n            player["sit_out_next"] = False\n        elif mode == "unready":\n            if state.get("status") == "playing" or bool(state.get("session_active")):\n                raise HTTPException(400, "開始後はREADYを取り消せません")\n            player["ready"] = False\n        elif mode == "return":\n'''
    s = _replace_once(s, old_cancel, new_cancel, 'unready branch')

    # Serialize the cross-table membership decision. Without this, simultaneous
    # A/B seat requests from two tabs could both pass the pre-lock membership
    # check and create a double seat for one user.
    seat_pattern = re.compile(
        r'@app\.post\("/api/tables/\{table_id\}/seat"\)\nasync def sit\(table_id: str, payload: SeatIn, user=Depends\(current_user\)\):.*?\n\n@app\.post\("/api/tables/\{table_id\}/leave"\)',
        re.S,
    )
    seat_replacement = r'''table_membership_lock = asyncio.Lock()


@app.post("/api/tables/{table_id}/seat")
async def sit(table_id: str, payload: SeatIn, user=Depends(current_user)):
    async with table_membership_lock:
        other = seated_table_for_user(user["id"], exclude=table_id)
        if other:
            raise HTTPException(400, "別のテーブルに着席中です")
        async with get_table_lock(table_id):
            state = load_table(table_id)
            try:
                seat_player(state, user_id=user["id"], name=user["name"], seat=payload.seat, stack=db.TABLE_STARTING_STACK)
            except ValueError as e:
                raise HTTPException(400, str(e))
            save_table(state)
    await hub.broadcast(table_id)
    return public_state(state, user["id"])


@app.post("/api/tables/{table_id}/leave")'''
    s, count = seat_pattern.subn(seat_replacement, s, count=1)
    if count != 1:
        raise RuntimeError(f'v1.16.1 seat endpoint replacement mismatch: {count}')

    # A timed-out player must not stall every automatic hand. They finish the
    # current action using the existing check/fold timeout rule, then sit out
    # automatically from the next hand. If the timeout itself ends the hand,
    # sit-out is applied immediately because _finish_hand has already run.
    timeout_old = '''                                apply_action(state, player["user_id"], "check" if legal.get("can_check") else "fold")\n                                if state.get("hand"):\n                                    state["hand"]["log"].append(f"{player['name']} timed out")\n                                arm_action_deadline(state)\n                                save_table(state)\n                                changed = True\n'''
    timeout_new = '''                                apply_action(state, player["user_id"], "check" if legal.get("can_check") else "fold")\n                                if state.get("hand"):\n                                    state["hand"]["log"].append(f"{player['name']} timed out · sit out next")\n                                if state.get("status") == "playing":\n                                    player["sit_out_next"] = True\n                                else:\n                                    player["sitting_out"] = True\n                                    player["sit_out_next"] = False\n                                    player["ready"] = False\n                                    active_after_timeout = _jj_table_active_players(state)\n                                    if len(active_after_timeout) < 2:\n                                        state["session_active"] = False\n                                        state["next_hand_at_epoch"] = None\n                                arm_action_deadline(state)\n                                save_table(state)\n                                changed = True\n'''
    s = _replace_once(s, timeout_old, timeout_new, 'timeout sitout')

    p.write_text(s, encoding='utf-8')


def _app(p: Path) -> None:
    s = p.read_text(encoding='utf-8')

    # v1.16 renderTableControls source is already in the runtime after v29.
    old_ready = '''    if(tableState.status!=='playing'&&!tableState.session_active&&!seated.sitting_out){\n      readyButton=`<button class="primary jj-ready-btn ${seated.ready?'is-ready':''}" id="jjReadyBtn" ${seated.ready?'disabled':''}>${seated.ready?'✓ READY':'READY'}</button>`;\n    }\n'''
    new_ready = '''    if(tableState.status!=='playing'&&!tableState.session_active&&!seated.sitting_out){\n      readyButton=seated.ready\n        ? '<button class="soft jj-ready-btn is-ready" data-table-presence="unready">✓ READY · 取消</button>'\n        : '<button class="primary jj-ready-btn" id="jjReadyBtn">READY</button>';\n    }\n'''
    s = _replace_once(s, old_ready, new_ready, 'revocable ready UI')

    # Presence feedback must distinguish READY cancellation from sit-out changes.
    old_toast = "toast(presence.dataset.tablePresence==='sitout'?'次ハンドから離席します':presence.dataset.tablePresence==='return'?'復帰します':presence.dataset.tablePresence==='rebuy'?'150bbでRebuyしました':'離席予約を取り消しました')"
    new_toast = "toast(presence.dataset.tablePresence==='sitout'?'離席を設定しました':presence.dataset.tablePresence==='return'?'次ハンドから参加します':presence.dataset.tablePresence==='rebuy'?'150bbでRebuyしました':presence.dataset.tablePresence==='unready'?'READYを取り消しました':'離席予約を取り消しました')"
    s = _replace_once(s, old_toast, new_toast, 'presence feedback')

    # The legacy control listener waited for a websocket round-trip after leave.
    # Refresh the authoritative table state immediately so the vacated seat and
    # player counts change as soon as the request succeeds.
    old_leave = '''if(e.target.id==='leaveSeatBtn'){try{await post(`/tables/${currentTableId}/leave`);await refreshMe();toast('席を離れました')}catch(err){toast(err.message)}}'''
    new_leave = '''if(e.target.id==='leaveSeatBtn'){try{await post(`/tables/${currentTableId}/leave`);const d=await api('/tables/'+currentTableId);tableState=d.state;tableMessages=d.messages||[];renderPokerRoom();await refreshMe();toast('席を離れました')}catch(err){toast(err.message)}}'''
    s = _replace_once(s, old_leave, new_leave, 'leave immediate refresh')

    p.write_text(s, encoding='utf-8')


def _index(p: Path) -> None:
    s = p.read_text(encoding='utf-8').replace('?v=29', '?v=30')
    p.write_text(s, encoding='utf-8')


def _sw(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    s = re.sub(r'jj-arena-live-v\d+', 'jj-arena-live-v30', s)
    p.write_text(s, encoding='utf-8')
