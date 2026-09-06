from __future__ import annotations
from pathlib import Path
import re


def apply(root: Path) -> None:
    _engine(root / 'poker_engine.py')
    _server(root / 'server.py')
    _app(root / 'static' / 'app.js')
    _styles(root / 'static' / 'styles.css')
    _index(root / 'static' / 'index.html')
    _sw(root / 'static' / 'sw.js')


def _engine(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    if 'v1.16 join-during-hand lifecycle' in s:
        return
    s += r'''

# v1.16 join-during-hand lifecycle.
# A new player may reserve an empty seat while a hand is running, but is never
# inserted into that hand. They enter SIT OUT and explicitly opt into a future
# hand with the return/presence action. Existing waiting-state seating keeps the
# verified engine path unchanged.
_jj_v16_previous_seat_player = seat_player


def seat_player(state: dict[str, Any], *, user_id: int, name: str, seat: int, stack: int) -> None:
    if state.get("status") != "playing":
        _jj_v16_previous_seat_player(state, user_id=user_id, name=name, seat=seat, stack=stack)
        return
    if not 0 <= int(seat) < int(state.get("max_seats", 6)):
        raise ValueError("invalid seat")
    if any(int(p.get("seat", -1)) == int(seat) for p in state.get("seats", [])):
        raise ValueError("seat is occupied")
    if any(int(p.get("user_id", -1)) == int(user_id) for p in state.get("seats", [])):
        raise ValueError("already seated")
    if not int(state.get("min_buyin", stack)) <= int(stack) <= int(state.get("max_buyin", stack)):
        raise ValueError("buy-in is outside table limits")
    state.setdefault("session_active", True)
    state.setdefault("next_hand_at_epoch", None)
    state["seats"].append({
        "user_id": int(user_id), "name": name, "seat": int(seat), "stack": int(stack),
        "in_hand": False, "folded": False, "all_in": False, "round_bet": 0,
        "contributed": 0, "cards": [], "ready": False,
        "sitting_out": True, "sit_out_next": False,
    })
    state["seats"].sort(key=lambda player: int(player.get("seat", 0)))
'''
    p.write_text(s, encoding='utf-8')


def _server(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    s = s.replace('version="1.15.1"', 'version="1.16.0"').replace('"version":"1.15.1"', '"version":"1.16.0"')
    s = s.replace('request.url.query == "v=28"', 'request.url.query == "v=29"')

    old = '"players":len(state["seats"]),"max_seats":state["max_seats"],'
    new = '''"players":sum(1 for p in state["seats"] if int(p.get("stack",0))>0 and not bool(p.get("sitting_out")) and not bool(p.get("sit_out_next"))),
            "seated":len(state["seats"]),
            "sitouts":sum(1 for p in state["seats"] if bool(p.get("sitting_out")) or bool(p.get("sit_out_next"))),
            "busted":sum(1 for p in state["seats"] if int(p.get("stack",0))<=0),
            "max_seats":state["max_seats"],'''
    if old not in s:
        raise RuntimeError('v1.16 lobby player-count marker missing')
    s = s.replace(old, new, 1)

    if 'v1.16 table-state invariant repair' not in s:
        s += r'''

# v1.16 table-state invariant repair. Persistent tables survive deploys, so old
# transient flags must be normalized rather than trusted indefinitely.
_jj_v16_base_load_table = load_table


def _jj_v16_repair_table_state(state: dict[str, Any]) -> bool:
    changed = False
    if "session_active" not in state:
        state["session_active"] = False; changed = True
    if "next_hand_at_epoch" not in state:
        state["next_hand_at_epoch"] = None; changed = True
    playing = state.get("status") == "playing"
    for player in state.get("seats", []):
        for key, default in (("ready", False), ("sitting_out", False), ("sit_out_next", False)):
            if key not in player:
                player[key] = default; changed = True
        if player.get("sitting_out"):
            if player.get("ready"):
                player["ready"] = False; changed = True
            if player.get("sit_out_next"):
                player["sit_out_next"] = False; changed = True
        if int(player.get("stack", 0)) <= 0:
            if player.get("ready"):
                player["ready"] = False; changed = True
            if player.get("sit_out_next"):
                player["sit_out_next"] = False; changed = True
        if not playing and player.get("sit_out_next"):
            player["sit_out_next"] = False
            player["sitting_out"] = True
            player["ready"] = False
            changed = True
    eligible = [p for p in state.get("seats", []) if int(p.get("stack",0)) > 0 and not bool(p.get("sitting_out"))]
    if playing:
        if not bool(state.get("session_active")):
            state["session_active"] = True; changed = True
        if state.get("next_hand_at_epoch") is not None:
            state["next_hand_at_epoch"] = None; changed = True
    else:
        if bool(state.get("session_active")) and len(eligible) < 2:
            state["session_active"] = False
            state["next_hand_at_epoch"] = None
            changed = True
        elif not bool(state.get("session_active")) and state.get("next_hand_at_epoch") is not None:
            state["next_hand_at_epoch"] = None; changed = True
    return changed


def load_table(table_id: str) -> dict[str, Any]:
    state = _jj_v16_base_load_table(table_id)
    if _jj_v16_repair_table_state(state):
        save_table(state)
    return state


def _jj_v16_repair_all_tables() -> None:
    for table_id, _ in db.FIXED_TABLES:
        try:
            load_table(table_id)
        except Exception:
            pass


_jj_v16_repair_all_tables()
'''

    p.write_text(s, encoding='utf-8')


def _app(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    if 'v1.16 playable table state machine' in s:
        return
    marker = '})();'
    pos = s.rfind(marker)
    if pos < 0:
        raise RuntimeError('v1.16 app.js closing marker missing')
    addon = r'''

  // v1.16 playable table state machine.
  // Fixed 150bb means seating needs no modal. A seat click is one atomic API
  // action, including during an active hand (server queues that player SIT OUT).
  let jjSeatBusy=false;
  seatClick=async function(seat){
    if(!currentTableId||jjSeatBusy)return;
    if(tableState?.seats?.some(p=>p.user_id===me?.id))return toast('すでに着席しています');
    if(tableState?.seats?.some(p=>Number(p.seat)===Number(seat)))return toast('その席は使用中です');
    jjSeatBusy=true;
    const button=document.querySelector(`[data-seat="${Number(seat)}"]`);
    if(button)button.disabled=true;
    try{
      const wasPlaying=tableState?.status==='playing';
      tableState=await post(`/tables/${currentTableId}/seat`,{seat:Number(seat)});
      renderPokerRoom();
      toast(wasPlaying?'着席しました。次ハンドから参加を押すと参加します':'150bbで着席しました。READYで開始します');
    }catch(err){
      toast(err.message);
      try{const d=await api('/tables/'+currentTableId);tableState=d.state;tableMessages=d.messages||[];renderPokerRoom()}catch{}
    }finally{jjSeatBusy=false;if(button)button.disabled=false}
  };

  renderTableControls=function(){
    const seated=tableState?.seats?.find(p=>p.user_id===me?.id);
    const nextPlayers=(tableState?.seats||[]).filter(p=>Number(p.stack)>0&&!p.sitting_out&&!p.sit_out_next);
    const ready=nextPlayers.filter(p=>p.ready).length;
    if(!seated){
      $('#tableControls').innerHTML='<div class="jj-table-control-left"><span class="hint">空席の「座る」を押すと150bbで着席します</span></div>';
      return;
    }
    const canLeaveNow=!seated.in_hand;
    if(Number(seated.stack)<=0){
      $('#tableControls').innerHTML=`<div class="jj-table-control-left"><span class="jj-control-note">BUSTED · 0bb</span></div><div class="jj-table-control-right"><button class="primary" data-table-presence="rebuy" ${tableState.status==='playing'?'disabled':''}>Rebuy 150bb</button>${canLeaveNow?'<button class="ghost" id="leaveSeatBtn">席を離れる</button>':''}</div>`;
      return;
    }
    let presence='';
    if(seated.sitting_out){
      const label=tableState.session_active?'次ハンドから参加':'テーブルに戻る';
      presence=`<button class="primary" data-table-presence="return">${label}</button>`;
    }else if(seated.sit_out_next){
      presence='<button class="soft" data-table-presence="cancel_sitout">離席予約を取消</button>';
    }else if(tableState.status==='playing'){
      presence='<button class="ghost jj-sitout-btn" data-table-presence="sitout">次ハンドから離席</button>';
    }else{
      presence='<button class="ghost jj-sitout-btn" data-table-presence="sitout">離席する</button>';
    }
    let readyButton='';
    if(tableState.status!=='playing'&&!tableState.session_active&&!seated.sitting_out){
      readyButton=`<button class="primary jj-ready-btn ${seated.ready?'is-ready':''}" id="jjReadyBtn" ${seated.ready?'disabled':''}>${seated.ready?'✓ READY':'READY'}</button>`;
    }
    const countText=tableState.session_active?`NEXT HAND ${nextPlayers.length}/6`:`READY ${ready}/${nextPlayers.length}`;
    const leave=canLeaveNow?'<button class="ghost" id="leaveSeatBtn">席を離れる</button>':'';
    $('#tableControls').innerHTML=`<div class="jj-table-control-left">${readyButton}<span class="jj-ready-count">${countText}</span></div><div class="jj-table-control-right">${presence}${leave}</div>`;
  };

  renderLobby=async function(){
    if(currentTableId)return;
    $('#lobbyPanel').classList.remove('hidden');$('#pokerRoom').classList.add('hidden');
    const tables=await api('/tables');
    $('#tableCards').innerHTML=tables.map(t=>{
      const extra=[];
      if(Number(t.seated||0)!==Number(t.players||0))extra.push(`着席 ${Number(t.seated||0)}/6`);
      if(Number(t.sitouts||0)>0)extra.push(`離席 ${Number(t.sitouts||0)}`);
      return `<article class="lobby-card"><div class="eyebrow ${t.status==='playing'?'status-live':''}">${t.status==='playing'?'● HAND IN PROGRESS':'OPEN TABLE'}</div><h4>${safe(t.name)}</h4><div class="lobby-stats"><span>参加 ${Number(t.players||0)}/6</span>${extra.map(x=>`<span>${x}</span>`).join('')}<span>0.5 / 1 bb</span><span>150bb start</span></div><p class="hint">ハンド中でも空席を予約できます。途中着席はSIT OUTで入り、本人が「次ハンドから参加」を押すまで配られません。</p><button class="primary full" data-open-table="${safe(t.id)}">テーブルを見る</button></article>`;
    }).join('')||'<div class="card empty">テーブルがありません</div>';
  };
'''
    s = s[:pos] + addon + s[pos:]
    p.write_text(s, encoding='utf-8')


def _styles(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    if 'v1.16 seat interaction hardening' in s:
        return
    s += r'''

/* v1.16 seat interaction hardening. The seat layer is intentionally interactive;
   no transparent table layer may swallow the primary join action. */
#pokerTable #seatLayer{pointer-events:auto!important}
#pokerTable #seatLayer .jj-seat{pointer-events:auto!important}
#pokerRoom .jj-empty-seat{position:relative!important;z-index:12!important;width:72px!important;height:42px!important;border-radius:999px!important;display:flex!important;align-items:center!important;justify-content:center!important;touch-action:manipulation!important;cursor:pointer!important;background:rgba(5,39,29,.90)!important;border:1px dashed rgba(242,211,119,.72)!important;color:#fff2bd!important;font-weight:900!important}
#pokerRoom .jj-empty-seat:after{content:"座る";font-size:.66rem;margin-left:3px;letter-spacing:.04em}
#pokerRoom .jj-empty-seat:hover,#pokerRoom .jj-empty-seat:focus-visible{background:#116b4d!important;border-style:solid!important;outline:2px solid rgba(244,206,93,.38)!important;outline-offset:2px!important}
#pokerRoom .jj-empty-seat:disabled{opacity:.45;cursor:wait}
@media(max-width:760px){#pokerRoom .jj-empty-seat{width:60px!important;height:38px!important;font-size:.9rem!important}#pokerRoom .jj-empty-seat:after{font-size:.58rem}}
'''
    p.write_text(s, encoding='utf-8')


def _index(p: Path) -> None:
    s = p.read_text(encoding='utf-8').replace('?v=28', '?v=29')
    p.write_text(s, encoding='utf-8')


def _sw(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    s = re.sub(r'jj-arena-live-v\d+', 'jj-arena-live-v29', s)
    p.write_text(s, encoding='utf-8')
