from __future__ import annotations
from pathlib import Path
import re


def apply(root: Path) -> None:
    _server(root / 'server.py')
    _app(root / 'static' / 'app.js')
    _styles(root / 'static' / 'styles.css')
    _index(root / 'static' / 'index.html')
    _sw(root / 'static' / 'sw.js')


def _server(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    s = s.replace('version="1.16.1"', 'version="1.16.2"').replace('"version":"1.16.1"', '"version":"1.16.2"')
    s = s.replace('request.url.query == "v=30"', 'request.url.query == "v=31"')
    if 'v1.16.2 server-selected seat join' in s:
        p.write_text(s, encoding='utf-8')
        return

    marker = '@app.websocket("/ws/tables/{table_id}")'
    if marker not in s:
        raise RuntimeError('v1.16.2 websocket marker missing')
    join = r'''# v1.16.2 server-selected seat join.
# Primary seating no longer depends on a tiny seat marker in the table DOM.
# The server chooses and reserves one real empty seat while holding the same
# cross-table membership lock used by explicit seat selection.
@app.post("/api/tables/{table_id}/join")
async def join_table(table_id: str, user=Depends(current_user)):
    async with table_membership_lock:
        async with get_table_lock(table_id):
            state = load_table(table_id)
            existing = _jj_table_user(state, user["id"])
            if existing:
                return public_state(state, user["id"])

        other = seated_table_for_user(user["id"], exclude=table_id)
        if other:
            raise HTTPException(400, "別のテーブルに着席中です")

        async with get_table_lock(table_id):
            state = load_table(table_id)
            existing = _jj_table_user(state, user["id"])
            if existing:
                return public_state(state, user["id"])
            occupied = {int(p.get("seat", -1)) for p in state.get("seats", [])}
            free = [seat for seat in range(int(state.get("max_seats", 6))) if seat not in occupied]
            if not free:
                raise HTTPException(409, "このテーブルは満席です")

            button = int(state.get("button_seat", -1))
            free.sort(key=lambda seat: ((seat - button) % int(state.get("max_seats", 6))))
            chosen = free[0]
            live_session = bool(state.get("session_active")) or state.get("status") == "playing"
            try:
                seat_player(
                    state,
                    user_id=user["id"],
                    name=user["name"],
                    seat=chosen,
                    stack=db.TABLE_STARTING_STACK,
                )
            except ValueError as e:
                raise HTTPException(400, str(e))

            player = _jj_table_user(state, user["id"])
            if player and live_session:
                player["sitting_out"] = False
                player["sit_out_next"] = False
                player["ready"] = False
                player["in_hand"] = False
                player["folded"] = False
                player["all_in"] = False
                player["round_bet"] = 0
                player["contributed"] = 0
                player["cards"] = []
            save_table(state)

    await hub.broadcast(table_id)
    return public_state(state, user["id"])


'''
    s = s.replace(marker, join + marker, 1)
    p.write_text(s, encoding='utf-8')


def _app(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    if 'v1.16.2 unmistakable primary seating' in s:
        return
    marker = '})();'
    pos = s.rfind(marker)
    if pos < 0:
        raise RuntimeError('v1.16.2 app closing marker missing')
    addon = r'''

  // v1.16.2 unmistakable primary seating.
  // Seat markers remain optional; every observer gets a large persistent JOIN
  // control on the table and the lobby also exposes direct seating.
  let jjJoinBusy=false;

  async function jjJoinTable(tableId,{openAfter=false}={}){
    if(!tableId||jjJoinBusy)return;
    jjJoinBusy=true;
    document.querySelectorAll('[data-jj-join],#jjJoinTableBtn').forEach(b=>b.disabled=true);
    try{
      const state=await post(`/tables/${tableId}/join`);
      if(openAfter||currentTableId!==tableId){
        await openTable(tableId);
      }else{
        tableState=state;
        renderPokerRoom();
      }
      toast('150bbで着席しました。進行中なら次ハンドから参加します');
    }catch(err){
      toast(err.message);
      if(currentTableId===tableId){
        try{const d=await api('/tables/'+tableId);tableState=d.state;tableMessages=d.messages||[];renderPokerRoom()}catch{}
      }
    }finally{
      jjJoinBusy=false;
      document.querySelectorAll('[data-jj-join],#jjJoinTableBtn').forEach(b=>b.disabled=false);
    }
  }

  function jjRenderPrimaryJoin(){
    const table=$('#pokerTable');
    if(!table||!tableState||!me)return;
    table.querySelector('#jjObserverJoin')?.remove();
    const seated=(tableState.seats||[]).some(p=>p.user_id===me.id);
    if(seated)return;
    const full=(tableState.seats||[]).length>=Number(tableState.max_seats||6);
    const el=document.createElement('div');
    el.id='jjObserverJoin';
    el.className='jj-observer-join';
    el.innerHTML=full
      ? '<div><b>TABLE FULL</b><span>空席ができるまで観戦できます</span></div><button class="ghost" disabled>満席</button>'
      : '<div><b>JOIN TABLE</b><span>150bb · プレイマネー</span></div><button class="primary" id="jjJoinTableBtn">着席してプレイ</button>';
    table.appendChild(el);
  }

  const jjV162RenderPokerRoom=renderPokerRoom;
  renderPokerRoom=function(){
    jjV162RenderPokerRoom();
    jjRenderPrimaryJoin();
  };

  renderTableControls=function(){
    const seated=tableState?.seats?.find(p=>p.user_id===me?.id);
    const nextPlayers=(tableState?.seats||[]).filter(p=>Number(p.stack)>0&&!p.sitting_out&&!p.sit_out_next);
    const ready=nextPlayers.filter(p=>p.ready).length;
    if(!seated){
      const full=(tableState?.seats||[]).length>=Number(tableState?.max_seats||6);
      $('#tableControls').innerHTML=`<div class="jj-table-control-left"><b class="jj-control-title">観戦中</b><span class="hint">${full?'現在は満席です':'150bbで参加できます'}</span></div><div class="jj-table-control-right"><button class="primary jj-join-control" data-jj-join="${safe(currentTableId||'')}" ${full?'disabled':''}>${full?'満席':'着席する · 150bb'}</button></div>`;
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
      readyButton=seated.ready
        ? '<button class="soft jj-ready-btn is-ready" data-table-presence="unready">✓ READY · 取消</button>'
        : '<button class="primary jj-ready-btn" id="jjReadyBtn">READY</button>';
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
      const seated=Number(t.seated||0),active=Number(t.players||0),full=seated>=Number(t.max_seats||6),extra=[];
      if(seated!==active)extra.push(`着席 ${seated}/6`);
      if(Number(t.sitouts||0)>0)extra.push(`離席 ${Number(t.sitouts||0)}`);
      return `<article class="lobby-card"><div class="eyebrow ${t.status==='playing'?'status-live':''}">${t.status==='playing'?'● HAND IN PROGRESS':'OPEN TABLE'}</div><h4>${safe(t.name)}</h4><div class="lobby-stats"><span>参加 ${active}/6</span>${extra.map(x=>`<span>${x}</span>`).join('')}<span>0.5 / 1 bb</span><span>150bb start</span></div><p class="hint">観戦だけでも入れます。プレイする場合は「着席する」を押してください。</p><div class="jj-lobby-actions"><button class="soft" data-open-table="${safe(t.id)}">観戦する</button><button class="primary" data-jj-join="${safe(t.id)}" ${full?'disabled':''}>${full?'満席':'着席する · 150bb'}</button></div></article>`;
    }).join('')||'<div class="card empty">テーブルがありません</div>';
  };

  document.addEventListener('click',async e=>{
    const join=e.target.closest('#jjJoinTableBtn,[data-jj-join]');
    if(!join)return;
    e.preventDefault();
    const tableId=join.dataset.jjJoin||currentTableId;
    await jjJoinTable(tableId,{openAfter:currentTableId!==tableId});
  });
'''
    s = s[:pos] + addon + s[pos:]
    p.write_text(s, encoding='utf-8')


def _styles(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    if 'v1.16.2 primary join controls' in s:
        return
    s += r'''

/* v1.16.2 primary join controls — seating must be impossible to miss. */
#pokerRoom .jj-observer-join{position:absolute;left:50%;bottom:14px;transform:translateX(-50%);z-index:30;display:flex;align-items:center;gap:14px;min-width:min(430px,calc(100% - 28px));max-width:520px;padding:10px 12px 10px 16px;border-radius:15px;background:rgba(5,16,12,.94);border:1px solid rgba(244,206,93,.62);box-shadow:0 12px 28px rgba(0,0,0,.38);backdrop-filter:blur(12px);pointer-events:auto!important;color:#fff}
#pokerRoom .jj-observer-join>div{display:flex;flex-direction:column;min-width:0;flex:1}#pokerRoom .jj-observer-join b{font-size:.72rem;letter-spacing:.12em;color:#ffe59a}#pokerRoom .jj-observer-join span{font-size:.68rem;color:#a9bdb4;margin-top:2px}#pokerRoom .jj-observer-join button{flex:0 0 auto;min-height:42px;padding-inline:18px}
#pokerRoom .jj-join-control{min-width:170px;min-height:44px}#pokerRoom .jj-control-title{font-size:.78rem;color:#e9f4ef}.jj-lobby-actions{display:grid;grid-template-columns:1fr 1.2fr;gap:8px;margin-top:13px}.jj-lobby-actions button{min-height:44px}
@media(max-width:760px){#pokerRoom .jj-observer-join{bottom:8px;min-width:calc(100% - 16px);padding:8px 9px 8px 12px;gap:8px}#pokerRoom .jj-observer-join button{min-height:40px;padding-inline:12px;font-size:.78rem}#pokerRoom .jj-observer-join span{font-size:.61rem}.jj-lobby-actions{grid-template-columns:1fr}}
'''
    p.write_text(s, encoding='utf-8')


def _index(p: Path) -> None:
    s = p.read_text(encoding='utf-8').replace('?v=30', '?v=31')
    p.write_text(s, encoding='utf-8')


def _sw(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    s = re.sub(r'jj-arena-live-v\d+', 'jj-arena-live-v31', s)
    p.write_text(s, encoding='utf-8')
