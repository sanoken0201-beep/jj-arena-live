from __future__ import annotations
from pathlib import Path
import re


def apply(root: Path) -> None:
    _patch_engine(root / 'poker_engine.py')
    _patch_server(root / 'server.py')
    _patch_index(root / 'static' / 'index.html')
    _patch_appjs(root / 'static' / 'app.js')
    _patch_styles(root / 'static' / 'styles.css')
    _patch_sw(root / 'static' / 'sw.js')


def _patch_engine(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    if 'v1.14 continuous-table lifecycle' in s:
        return
    s += r'''

# v1.14 continuous-table lifecycle. Wrappers preserve the verified v1.4
# betting/rake/showdown implementation while adding ready/sit-out semantics.
import time as _jj_time

_jj_original_seat_player = seat_player
_jj_original_start_hand = start_hand
_jj_original_finish_hand = _finish_hand


def _jj_player_defaults(player: dict[str, Any]) -> None:
    player.setdefault("ready", False)
    player.setdefault("sitting_out", False)
    player.setdefault("sit_out_next", False)


def _jj_next_hand_players(state: dict[str, Any]) -> list[dict[str, Any]]:
    for player in state.get("seats", []):
        _jj_player_defaults(player)
    return [
        player for player in state.get("seats", [])
        if int(player.get("stack", 0)) > 0 and not bool(player.get("sitting_out"))
    ]


def seat_player(state: dict[str, Any], *args, **kwargs) -> None:
    _jj_original_seat_player(state, *args, **kwargs)
    user_id = kwargs.get("user_id")
    for player in state.get("seats", []):
        if user_id is None or int(player.get("user_id", -1)) == int(user_id):
            _jj_player_defaults(player)
            player["ready"] = False
            player["sitting_out"] = False
            player["sit_out_next"] = False
    state.setdefault("session_active", False)
    state.setdefault("next_hand_at_epoch", None)


def start_hand(state: dict[str, Any]) -> None:
    """Start a hand while excluding players who explicitly sit out."""
    active = _jj_next_hand_players(state)
    if len(active) < 2:
        raise ValueError("at least two active players with chips are required")
    held_stacks: list[tuple[dict[str, Any], int]] = []
    for player in state.get("seats", []):
        if player.get("sitting_out") and int(player.get("stack", 0)) > 0:
            held_stacks.append((player, int(player["stack"])))
            player["stack"] = 0
    state["next_hand_at_epoch"] = None
    try:
        _jj_original_start_hand(state)
    finally:
        for player, stack in held_stacks:
            player["stack"] = stack
    for player in state.get("seats", []):
        _jj_player_defaults(player)
        player["ready"] = False


def _finish_hand(state: dict[str, Any]) -> None:
    """Finish normally, then apply next-hand sit-out reservations and queue the next deal."""
    _jj_original_finish_hand(state)
    for player in state.get("seats", []):
        _jj_player_defaults(player)
        if player.get("sit_out_next"):
            player["sitting_out"] = True
            player["sit_out_next"] = False
            player["ready"] = False
    active = _jj_next_hand_players(state)
    if bool(state.get("session_active")) and len(active) >= 2:
        state["next_hand_at_epoch"] = _jj_time.time() + 2.4
    else:
        state["next_hand_at_epoch"] = None
        if len(active) < 2:
            state["session_active"] = False
            for player in state.get("seats", []):
                player["ready"] = False
'''
    p.write_text(s, encoding='utf-8')


def _patch_server(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    s = s.replace('version="1.13.0"', 'version="1.14.0"').replace('"version":"1.13.0"', '"version":"1.14.0"')
    s = s.replace('request.url.query == "v=23"', 'request.url.query == "v=24"')
    if '\nimport time\n' not in s:
        anchor = 'import re\n'
        if anchor in s:
            s = s.replace(anchor, anchor + 'import time\n', 1)
        else:
            s = 'import time\n' + s

    if 'class TablePresenceIn(BaseModel):' not in s:
        marker = 'class SeatIn(BaseModel):'
        if marker not in s:
            raise RuntimeError('v1.14 SeatIn model marker not found')
        model = '''class TablePresenceIn(BaseModel):\n    mode: str = Field(pattern="^(sitout|cancel_sitout|return)$")\n\n\n'''
        s = s.replace(marker, model + marker, 1)

    if 'def _jj_table_active_players(' not in s:
        marker = '@app.post("/api/tables/{table_id}/start")'
        if marker not in s:
            raise RuntimeError('v1.14 start endpoint marker not found')
        helpers = r'''def _jj_table_player_defaults(player: dict[str, Any]) -> None:
    player.setdefault("ready", False)
    player.setdefault("sitting_out", False)
    player.setdefault("sit_out_next", False)


def _jj_table_active_players(state: dict[str, Any]) -> list[dict[str, Any]]:
    for player in state.get("seats", []):
        _jj_table_player_defaults(player)
    return [
        player for player in state.get("seats", [])
        if int(player.get("stack", 0)) > 0 and not bool(player.get("sitting_out"))
    ]


def _jj_table_user(state: dict[str, Any], user_id: int) -> dict[str, Any] | None:
    for player in state.get("seats", []):
        if int(player.get("user_id", -1)) == int(user_id):
            _jj_table_player_defaults(player)
            return player
    return None


@app.post("/api/tables/{table_id}/presence")
async def table_presence(table_id: str, payload: TablePresenceIn, user=Depends(current_user)):
    async with get_table_lock(table_id):
        state = load_table(table_id)
        player = _jj_table_user(state, user["id"])
        if not player:
            raise HTTPException(400, "このテーブルに着席していません")
        mode = payload.mode
        if mode == "sitout":
            if state.get("status") == "playing" and player.get("in_hand"):
                player["sit_out_next"] = True
            else:
                player["sitting_out"] = True
                player["sit_out_next"] = False
                player["ready"] = False
        elif mode == "cancel_sitout":
            player["sit_out_next"] = False
        elif mode == "return":
            if int(player.get("stack", 0)) <= 0:
                raise HTTPException(400, "0bbのため復帰するにはRebuyが必要です")
            player["sitting_out"] = False
            player["sit_out_next"] = False
            if not bool(state.get("session_active")):
                player["ready"] = False
        active = _jj_table_active_players(state)
        if len(active) < 2 and state.get("status") != "playing":
            state["session_active"] = False
            state["next_hand_at_epoch"] = None
        save_table(state)
    await hub.broadcast(table_id)
    return public_state(state, user["id"])


'''
        s = s.replace(marker, helpers + marker, 1)

    pattern = re.compile(
        r'@app\.post\("/api/tables/\{table_id\}/start"\)\nasync def start\(table_id: str, user=Depends\(current_user\)\):.*?\n\n@app\.post\("/api/tables/\{table_id\}/action"\)',
        re.S,
    )
    replacement = r'''@app.post("/api/tables/{table_id}/start")
async def start(table_id: str, user=Depends(current_user)):
    async with get_table_lock(table_id):
        state = load_table(table_id)
        if state.get("status") == "playing":
            raise HTTPException(400, "ハンド進行中です")
        player = _jj_table_user(state, user["id"])
        if not player:
            raise HTTPException(403, "着席してから参加準備をしてください")
        if int(player.get("stack", 0)) <= 0:
            raise HTTPException(400, "0bbのため参加できません")
        player["sitting_out"] = False
        player["sit_out_next"] = False
        player["ready"] = True
        active = _jj_table_active_players(state)
        if len(active) >= 2 and all(bool(p.get("ready")) for p in active):
            state["session_active"] = True
            state["next_hand_at_epoch"] = None
            try:
                start_hand(state)
            except ValueError as e:
                raise HTTPException(400, str(e))
            arm_action_deadline(state)
        save_table(state)
    await hub.broadcast(table_id)
    return public_state(state, user["id"])


@app.post("/api/tables/{table_id}/action")'''
    s, count = pattern.subn(replacement, s, count=1)
    if count != 1:
        raise RuntimeError(f'v1.14 start endpoint replacement mismatch: {count}')

    if 'async def auto_deal_loop()' not in s:
        marker = 'async def timeout_loop():'
        if marker not in s:
            raise RuntimeError('v1.14 timeout loop marker not found')
        auto = r'''async def auto_deal_loop():
    """Continue a live table automatically after the result display delay."""
    while True:
        await asyncio.sleep(0.5)
        for table_id, _ in db.FIXED_TABLES:
            changed = False
            async with get_table_lock(table_id):
                try:
                    state = load_table(table_id)
                except HTTPException:
                    continue
                if state.get("status") != "waiting" or not bool(state.get("session_active")):
                    continue
                active = _jj_table_active_players(state)
                if len(active) < 2:
                    state["session_active"] = False
                    state["next_hand_at_epoch"] = None
                    for player in state.get("seats", []):
                        player["ready"] = False
                    save_table(state)
                    changed = True
                else:
                    due = state.get("next_hand_at_epoch")
                    if due is None:
                        state["next_hand_at_epoch"] = time.time() + 1.6
                        save_table(state)
                        changed = True
                    elif time.time() >= float(due):
                        try:
                            start_hand(state)
                        except ValueError:
                            state["session_active"] = False
                            state["next_hand_at_epoch"] = None
                        else:
                            arm_action_deadline(state)
                        save_table(state)
                        changed = True
            if changed:
                await hub.broadcast(table_id)


'''
        s = s.replace(marker, auto + marker, 1)

    if 'auto_task = asyncio.create_task(auto_deal_loop())' not in s:
        target = 'task = asyncio.create_task(timeout_loop())'
        if target not in s:
            raise RuntimeError('v1.14 lifespan task marker not found')
        s = s.replace(target, target + '\n    auto_task = asyncio.create_task(auto_deal_loop())', 1)
        target = 'task.cancel()'
        if target not in s:
            raise RuntimeError('v1.14 lifespan cancel marker not found')
        s = s.replace(target, target + '\n        auto_task.cancel()', 1)

    p.write_text(s, encoding='utf-8')


def _patch_index(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    s = s.replace('?v=23', '?v=24')
    s = s.replace('JJ内の練習用プレイマネーテーブルです。A/Bの2卓のみ、6-max、0.5/1bb、着席時150bb固定です。現金・換金・賭け機能はありません。',
                  'JJ内の練習用プレイマネーテーブルです。最初だけ全員READYで開始し、その後は自動で次ハンドへ進みます。離席は「次ハンドから離席」で予約できます。')
    p.write_text(s, encoding='utf-8')


def _patch_appjs(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    if 'v1.14 poker-table redesign' in s:
        return
    marker = '})();'
    pos = s.rfind(marker)
    if pos < 0:
        raise RuntimeError('v1.14 app.js closing marker not found')
    addon = r'''

  // v1.14 poker-table redesign — continuous play, unanimous first READY,
  // prominent street bets, poker-standard sizing presets, and hero-first layout.
  let jjPrevBoardCount=0,jjPrevHandId=null,jjPrevBets={};
  const jjSeatCoords=[
    {left:50,top:83},{left:16,top:66},{left:15,top:25},
    {left:50,top:10},{left:85,top:25},{left:84,top:66}
  ];
  const jjStreetLabel={preflop:'PREFLOP',flop:'FLOP',turn:'TURN',river:'RIVER',complete:'SHOWDOWN'};

  function jjHeroSeat(){return tableState?.seats?.find(p=>p.user_id===me?.id)?.seat ?? 0}
  function jjVisualIndex(actual){return ((Number(actual)-jjHeroSeat()+6)%6+6)%6}
  function jjSeatPos(actual){return jjSeatCoords[jjVisualIndex(actual)]||jjSeatCoords[0]}
  function jjBetPos(actual){const p=jjSeatPos(actual);return{left:50+(p.left-50)*.61,top:48+(p.top-48)*.59}}
  function jjPlayerState(p){
    if(p.sitting_out)return 'SIT OUT';if(p.sit_out_next)return 'SIT OUT NEXT';if(p.all_in)return 'ALL-IN';if(p.folded)return 'FOLDED';if(p.ready)return 'READY';return '';
  }
  function jjBoardHtml(cards){
    const handId=tableState?.hand?.id||null;
    if(handId!==jjPrevHandId){jjPrevHandId=handId;jjPrevBoardCount=0;jjPrevBets={}}
    const before=jjPrevBoardCount;
    const html=(cards||[]).map((c,i)=>{
      let h=cardHTML(c).replace('card-face ',`card-face jj-board-card ${i>=before?'jj-card-deal ':''}`);
      if(i>=before&&!h.includes('style="'))h=h.replace('>',` style="animation-delay:${Math.min(i-before,4)*90}ms">`);
      return h;
    }).join('');
    jjPrevBoardCount=(cards||[]).length;
    return html;
  }
  function jjMadeHand(){
    const hero=tableState?.seats?.find(p=>p.user_id===me?.id),board=tableState?.hand?.board||[],cards=[...(hero?.cards||[]),...board].filter(c=>c&&c!=='??');
    if(cards.length<2)return '';
    const ranks=cards.map(c=>'23456789TJQKA'.indexOf(c[0])+2),counts={};ranks.forEach(r=>counts[r]=(counts[r]||0)+1);
    const suits={};cards.forEach(c=>(suits[c[1]]||(suits[c[1]]=[])).push('23456789TJQKA'.indexOf(c[0])+2));
    const uniq=[...new Set(ranks)].sort((a,b)=>a-b);if(uniq.includes(14))uniq.unshift(1);
    const straight=uniq.some((_,i)=>i+4<uniq.length&&uniq[i+4]-uniq[i]===4);
    const flush=Object.values(suits).some(v=>v.length>=5);
    if(cards.length>=5&&straight&&flush)return 'Straight / Flush possible';
    const vals=Object.values(counts);if(vals.some(v=>v===4))return 'Four of a Kind';if(vals.includes(3)&&vals.filter(v=>v>=2).length>=2)return 'Full House';if(flush)return 'Flush';if(straight)return 'Straight';if(vals.some(v=>v===3))return 'Three of a Kind';if(vals.filter(v=>v===2).length>=2)return 'Two Pair';if(vals.some(v=>v===2))return 'One Pair';return board.length?'High Card':'Preflop';
  }
  function jjTotalPot(){return (tableState?.seats||[]).reduce((sum,p)=>sum+Number(p.contributed||0),0)}
  totalPot=jjTotalPot;

  renderSeat=function(seat){
    const p=tableState.seats.find(x=>x.seat===seat),pos=jjSeatPos(seat);
    if(!p)return `<div class="seat jj-seat seat-empty" style="left:${pos.left}%;top:${pos.top}%"><button class="jj-empty-seat" data-seat="${seat}">＋</button></div>`;
    const isAct=tableState.hand?.action_seat===seat,isButton=tableState.button_seat===seat,isHero=p.user_id===me.id,state=jjPlayerState(p),hole=(p.cards||[]).map(cardHTML).join('');
    const statusClass=p.sitting_out?' is-sitting':p.folded?' is-folded':'';
    return `<div class="seat jj-seat ${isAct?'active':''}${isHero?' is-hero':''}${statusClass}" style="left:${pos.left}%;top:${pos.top}%"><div class="seat-box jj-seat-box">${isButton?'<span class="dealer">D</span>':''}<div class="jj-player-top"><span class="jj-avatar">${safe(String(p.name||'?').slice(0,1))}</span><div><div class="name">${safe(p.name)}${isHero?' · YOU':''}</div><div class="stack">${bb(p.stack)}</div></div></div>${hole?`<div class="hole jj-hole">${hole}</div>`:''}${state?`<div class="jj-player-state">${state}</div>`:''}</div></div>`;
  };

  function jjRenderBetMarkers(){
    const layer=$('#seatLayer');if(!layer)return;
    const markers=(tableState?.seats||[]).filter(p=>Number(p.round_bet||0)>0).map(p=>{
      const pos=jjBetPos(p.seat),now=Number(p.round_bet||0),old=Number(jjPrevBets[p.user_id]||0),pulse=now>old?' jj-bet-pulse':'';jjPrevBets[p.user_id]=now;
      return `<div class="jj-bet-marker${pulse}" style="left:${pos.left}%;top:${pos.top}%"><i></i><b>${bb(now)}</b></div>`;
    }).join('');
    layer.insertAdjacentHTML('beforeend',markers);
  }

  renderPokerRoom=function(){
    if(!tableState)return;
    const hero=tableState.seats.find(p=>p.user_id===me.id),phase=tableState.hand?.phase||'waiting',actionSeat=tableState.hand?.action_seat,acting=tableState.seats.find(p=>p.seat===actionSeat),deadline=tableState.hand?.action_deadline;
    $('#roomTitle').textContent=tableState.name;$('#roomMeta').textContent='6-max · 0.5/1bb · 150bb · auto deal';
    $('#boardCards').innerHTML=jjBoardHtml(tableState.hand?.board||[]);$('#potDisplay').innerHTML=`<span>POT</span><b>${bb(jjTotalPot())}</b>`;
    let sec='';if(deadline){sec=Math.max(0,Math.ceil((new Date(deadline)-new Date())/1000));sec=` · ${sec}s`}
    const isMine=acting?.user_id===me.id;
    $('#handStatus').innerHTML=tableState.status==='playing'?`<b>${jjStreetLabel[phase]||String(phase).toUpperCase()}</b><span class="${isMine?'jj-your-turn':''}">${isMine?'YOUR TURN':acting?`${safe(acting.name)} TO ACT`:''}${sec}</span>`:tableState.session_active?'<b>NEXT HAND</b><span>自動ディール待機中</span>':'<b>TABLE READY</b><span>全員のREADYで開始</span>';
    $('#seatLayer').innerHTML=Array.from({length:6},(_,seat)=>renderSeat(seat)).join('');jjRenderBetMarkers();
    const result=tableState.last_result;$('#resultBanner').classList.toggle('hidden',!result);if(result)$('#resultBanner').textContent=result.message;
    renderTableControls();renderActionBar();renderTableChat();renderHandLog();
    const zone=$('.poker-zone');zone?.classList.toggle('jj-action-on',!!tableState.legal?.can_act);zone?.classList.toggle('jj-hero-seated',!!hero);
  };

  renderTableControls=function(){
    const seated=tableState.seats.find(p=>p.user_id===me.id),active=(tableState.seats||[]).filter(p=>p.stack>0&&!p.sitting_out),ready=active.filter(p=>p.ready).length;
    if(!seated){$('#tableControls').innerHTML='<span class="hint">空席を選んで150bbで着席</span>';return}
    if(seated.stack<=0){$('#tableControls').innerHTML='<span class="jj-control-note">BUSTED · Rebuyして復帰してください</span>';return}
    let primary='';
    if(seated.sitting_out)primary='<button class="primary" data-table-presence="return">復帰する</button>';
    else if(seated.sit_out_next)primary='<button class="soft" data-table-presence="cancel_sitout">離席予約を取消</button>';
    else primary='<button class="ghost jj-sitout-btn" data-table-presence="sitout">次ハンドから離席</button>';
    let readyButton='';
    if(tableState.status!=='playing'&&!tableState.session_active&&!seated.sitting_out){readyButton=`<button class="primary jj-ready-btn ${seated.ready?'is-ready':''}" id="jjReadyBtn" ${seated.ready?'disabled':''}>${seated.ready?'✓ READY':`READY ${ready}/${Math.max(active.length,2)}`}</button>`}
    const leave=(tableState.status!=='playing'&&seated.sitting_out)?'<button class="ghost" id="leaveSeatBtn">席を完全に離れる</button>':'';
    $('#tableControls').innerHTML=`<div class="jj-table-control-left">${readyButton}<span class="jj-ready-count">${tableState.session_active?'AUTO PLAY':`READY ${ready}/${active.length}`}</span></div><div class="jj-table-control-right">${primary}${leave}</div>`;
  };

  function jjHero(){return tableState?.seats?.find(p=>p.user_id===me?.id)}
  function jjRaiseBounds(){const l=tableState?.legal||{},big=Number(tableState?.big_blind||100);return{min:Number(l.min_raise_to||l.max_raise_to||0)/big,max:Number(l.max_raise_to||0)/big}}
  function jjClampRaiseBb(v){const b=jjRaiseBounds();return Math.max(b.min,Math.min(b.max,Number(v||b.min)))}
  function jjSetRaiseBb(v){const value=jjClampRaiseBb(v),inp=$('#raiseTo'),slider=$('#raiseSlider');if(inp)inp.value=(Math.round(value*100)/100);if(slider)slider.value=value;if($('#jjRaiseAmount'))$('#jjRaiseAmount').textContent=`${value.toFixed(value%1?1:0)}bb`}
  function jjPotPctBb(pct){
    const hero=jjHero(),l=tableState.legal||{},big=Number(tableState.big_blind||100),call=Number(l.call_amount||0),pot=jjTotalPot(),currentRound=Number(hero?.round_bet||0);
    const target=currentRound+call+(pot+call)*(Number(pct)/100);return jjClampRaiseBb(target/big);
  }

  renderActionBar=function(){
    const l=tableState.legal||{can_act:false},hero=jjHero();
    if(!hero){$('#actionBar').innerHTML='<span class="hint">着席するとアクションパネルが表示されます</span>';return}
    const handLabel=jjMadeHand();
    if(!l.can_act){$('#actionBar').innerHTML=`<div class="jj-hero-summary"><div class="jj-hero-cards">${(hero.cards||[]).map(cardHTML).join('')}</div><div><b>${safe(handLabel)}</b><span>${hero.sitting_out?'離席中':tableState.status==='playing'?'アクション待ち':'次のハンドを待機'}</span></div></div>`;return}
    const isPre=tableState.hand?.phase==='preflop',bounds=jjRaiseBounds(),min=bounds.min||0,max=bounds.max||0,call=Number(l.call_amount||0);
    const presets=isPre?[['2.5x',2.5],['3x',3],['4x',4]]:[[ '33%',33],[ '50%',50],[ '75%',75],[ 'POT',100]];
    const quick=presets.map(([label,val])=>isPre?`<button class="jj-size-btn" data-raise-bb="${val}">${label}</button>`:`<button class="jj-size-btn" data-pot-pct="${val}">${label}</button>`).join('');
    const raiseControls=l.can_raise&&max>0?`<div class="jj-sizing"><div class="jj-size-row">${quick}</div><div class="jj-raise-editor"><input id="raiseSlider" type="range" min="${min}" max="${max}" step="0.5" value="${min}"><label><input id="raiseTo" type="number" inputmode="decimal" min="${min}" max="${max}" step="0.5" value="${min}"><span>bb</span></label><b id="jjRaiseAmount">${min}bb</b></div></div>`:'';
    const callButton=l.can_check?'<button class="jj-action-btn jj-check" data-action="check"><small>CHECK</small><b>チェック</b></button>':`<button class="jj-action-btn jj-call" data-action="call"><small>CALL</small><b>${bb(call)}</b></button>`;
    const raiseButton=l.can_raise?`<button class="jj-action-btn jj-raise" data-action="raise"><small>${l.can_check?'BET':'RAISE'}</small><b>実行</b></button>`:'';
    const allin=l.can_all_in?'<button class="jj-action-btn jj-allin" data-action="allin"><small>ALL-IN</small><b>MAX</b></button>':'';
    $('#actionBar').innerHTML=`<div class="jj-action-context"><div class="jj-hero-cards">${(hero.cards||[]).map(cardHTML).join('')}</div><div><span>${safe(handLabel)}</span>${call?`<b>TO CALL ${bb(call)}</b>`:'<b>YOUR ACTION</b>'}</div></div>${raiseControls}<div class="jj-main-actions"><button class="jj-action-btn jj-fold" data-action="fold"><small>FOLD</small><b>フォールド</b></button>${callButton}${raiseButton}${allin}</div>`;
  };

  document.addEventListener('click',async e=>{
    const ready=e.target.closest('#jjReadyBtn');if(ready){try{ready.disabled=true;await post(`/tables/${currentTableId}/start`);toast('参加準備を送りました')}catch(err){toast(err.message)}return}
    const presence=e.target.closest('[data-table-presence]');if(presence){try{await post(`/tables/${currentTableId}/presence`,{mode:presence.dataset.tablePresence});toast(presence.dataset.tablePresence==='sitout'?'次ハンドから離席します':presence.dataset.tablePresence==='return'?'復帰します':'離席予約を取り消しました')}catch(err){toast(err.message)}return}
    const pct=e.target.closest('[data-pot-pct]');if(pct){jjSetRaiseBb(jjPotPctBb(Number(pct.dataset.potPct)));return}
    const rbb=e.target.closest('[data-raise-bb]');if(rbb){jjSetRaiseBb(Number(rbb.dataset.raiseBb));return}
  });
  document.addEventListener('input',e=>{if(e.target.id==='raiseSlider')jjSetRaiseBb(e.target.value);if(e.target.id==='raiseTo'&&$('#raiseSlider'))$('#raiseSlider').value=jjClampRaiseBb(e.target.value)});
'''
    s = s[:pos] + addon + s[pos:]
    p.write_text(s, encoding='utf-8')


def _patch_styles(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    if 'v1.14 premium poker table' in s:
        return
    s += r'''

/* v1.14 premium poker table — inspired by established online-poker information hierarchy, not copied artwork. */
#pokerRoom{--felt:#0b5a3f;--felt2:#073c2d;--rail:#131a18;--gold:#e6b94b;--action:#1d8c68}
#pokerRoom .room-head{margin-bottom:12px}
#pokerRoom .poker-layout{grid-template-columns:minmax(0,1fr) 280px;gap:14px;align-items:start}
#pokerRoom .poker-zone{padding:12px;background:linear-gradient(180deg,#111816,#0d1312);border-color:#29352f;overflow:visible}
#pokerTable{position:relative;min-height:620px;aspect-ratio:16/10;max-height:72vh;border-radius:50% / 43%;background:radial-gradient(ellipse at 50% 42%,#127754 0%,var(--felt) 42%,var(--felt2) 76%,#04271e 100%);border:15px solid var(--rail);box-shadow:inset 0 0 0 3px #334039,inset 0 0 60px rgba(0,0,0,.35),0 20px 55px rgba(0,0,0,.28)}
#pokerTable:after{content:"JJ ARENA";position:absolute;left:50%;top:58%;transform:translate(-50%,-50%);font:900 clamp(1.3rem,3vw,2.3rem)/1 system-ui;letter-spacing:.2em;color:rgba(255,255,255,.055);pointer-events:none}
.felt-center{top:39%;z-index:3}.cards.board{gap:8px;justify-content:center}.jj-board-card{width:clamp(48px,6vw,72px);height:clamp(67px,8.4vw,100px);font-size:clamp(1.15rem,2.2vw,1.75rem);border-radius:9px;box-shadow:0 7px 16px rgba(0,0,0,.25)}
.jj-card-deal{animation:jjDealCard .28s cubic-bezier(.2,.8,.2,1) both}@keyframes jjDealCard{from{opacity:0;transform:translateY(-22px) scale(.86) rotate(-3deg)}to{opacity:1;transform:none}}
.pot-display{display:flex!important;align-items:center;justify-content:center;gap:8px;margin:10px auto 0;width:max-content;padding:6px 12px;border-radius:999px;background:rgba(3,22,16,.72);border:1px solid rgba(255,255,255,.12);color:#fff}.pot-display span{font-size:.62rem;letter-spacing:.12em;color:#b8ccc3}.pot-display b{font-size:1.05rem;color:#fff}
.hand-status{display:flex;justify-content:center;gap:9px;margin-top:7px;color:#b9d2c7}.hand-status b{font-size:.68rem;letter-spacing:.14em}.hand-status span{font-size:.72rem}.jj-your-turn{color:#ffe38b!important;font-weight:900;animation:jjTurnPulse 1s ease-in-out infinite alternate}@keyframes jjTurnPulse{to{text-shadow:0 0 14px rgba(255,214,90,.75)}}
.jj-seat{position:absolute;transform:translate(-50%,-50%);z-index:6;width:clamp(112px,14vw,158px)}.jj-seat-box{position:relative;padding:7px 9px 8px;border-radius:12px;background:linear-gradient(180deg,rgba(22,30,28,.97),rgba(8,13,12,.97));border:1px solid #46524e;box-shadow:0 8px 18px rgba(0,0,0,.28);color:#fff;text-align:left}.jj-seat.active .jj-seat-box{border-color:#f0c74c;box-shadow:0 0 0 2px rgba(240,199,76,.24),0 8px 22px rgba(0,0,0,.35)}.jj-seat.is-folded{opacity:.48}.jj-seat.is-sitting{opacity:.58;filter:saturate(.5)}
.jj-player-top{display:flex;align-items:center;gap:7px}.jj-avatar{width:29px;height:29px;display:grid;place-items:center;border-radius:50%;background:#26362f;border:1px solid #52675e;font-size:.75rem;font-weight:900}.jj-seat-box .name{font-size:.73rem;font-weight:900;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.jj-seat-box .stack{font-size:.77rem;color:#dceae4;font-weight:800;margin-top:1px}.jj-player-state{margin-top:5px;width:max-content;max-width:100%;padding:2px 6px;border-radius:5px;background:#2b3934;color:#bcd0c7;font-size:.54rem;font-weight:900;letter-spacing:.08em}.jj-seat.is-hero .jj-seat-box{border-color:#4fae89}.jj-hole{position:absolute;left:50%;top:-53px;transform:translateX(-50%);display:flex;gap:3px;z-index:-1}.jj-hole .card-face{width:36px;height:50px;font-size:.9rem}.jj-seat.is-hero .jj-hole{top:-72px;gap:5px;z-index:2}.jj-seat.is-hero .jj-hole .card-face{width:50px;height:70px;font-size:1.25rem;box-shadow:0 7px 14px rgba(0,0,0,.28)}
.jj-empty-seat{width:42px;height:42px;border-radius:50%;border:1px dashed rgba(255,255,255,.34);background:rgba(4,30,21,.55);color:#c8ded4;font-size:1.25rem}.jj-empty-seat:hover{background:rgba(15,92,64,.7)}
.jj-bet-marker{position:absolute;transform:translate(-50%,-50%);z-index:5;display:flex;align-items:center;gap:5px;padding:4px 8px;border-radius:999px;background:rgba(5,14,11,.94);border:1px solid rgba(255,217,99,.72);box-shadow:0 4px 12px rgba(0,0,0,.35);pointer-events:none}.jj-bet-marker i{width:13px;height:13px;border-radius:50%;background:repeating-linear-gradient(45deg,#e7b643 0 3px,#fff0b0 3px 5px);border:1px solid #f6dc8c;box-shadow:0 0 0 2px #8f6919}.jj-bet-marker b{font-size:.8rem;color:#fff6c8;font-variant-numeric:tabular-nums;white-space:nowrap}.jj-bet-pulse{animation:jjBetPop .34s cubic-bezier(.2,.8,.2,1)}@keyframes jjBetPop{0%{transform:translate(-50%,-50%) scale(.7);filter:brightness(1.8)}100%{transform:translate(-50%,-50%) scale(1);filter:none}}
.table-controls{display:flex;align-items:center;justify-content:space-between;gap:10px;min-height:48px;padding:10px 4px 2px}.jj-table-control-left,.jj-table-control-right{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.jj-ready-count{font-size:.68rem;letter-spacing:.08em;color:#91a69d}.jj-ready-btn{min-width:116px}.jj-ready-btn.is-ready{background:#187455}.jj-sitout-btn{border-color:#58655f}.jj-control-note{color:#d6c383;font-size:.8rem}
.action-bar{display:block!important;margin-top:8px;padding:12px;border-radius:16px;background:linear-gradient(180deg,#141b19,#0c1110);border:1px solid #2f3b36;box-shadow:0 12px 30px rgba(0,0,0,.2)}.jj-action-context{display:flex;align-items:center;gap:11px;min-height:58px;margin-bottom:8px}.jj-hero-cards{display:flex;gap:5px}.jj-hero-cards .card-face{width:48px;height:66px;font-size:1.2rem;box-shadow:0 5px 12px rgba(0,0,0,.3)}.jj-action-context>div:last-child{display:flex;flex-direction:column;gap:2px}.jj-action-context span{font-size:.74rem;color:#9fb2aa}.jj-action-context b{font-size:.86rem;color:#f8e3a1;letter-spacing:.04em}.jj-hero-summary{display:flex;align-items:center;justify-content:center;gap:12px}.jj-hero-summary>div:last-child{display:flex;flex-direction:column}.jj-hero-summary span{font-size:.74rem;color:#9fb2aa}
.jj-sizing{display:grid;grid-template-columns:auto 1fr;gap:10px;align-items:center;margin-bottom:10px}.jj-size-row{display:flex;gap:5px;flex-wrap:wrap}.jj-size-btn{min-height:34px;padding:0 10px;border:1px solid #405049;border-radius:8px;background:#202a27;color:#d7e5df;font-size:.72rem;font-weight:900}.jj-size-btn:hover{border-color:#d3aa43;color:#fff}.jj-raise-editor{display:grid;grid-template-columns:minmax(100px,1fr) 84px auto;gap:7px;align-items:center}.jj-raise-editor input[type=range]{width:100%;accent-color:#d5aa3e}.jj-raise-editor label{display:flex;align-items:center;border:1px solid #3c4b45;border-radius:8px;background:#0b100f;overflow:hidden}.jj-raise-editor input[type=number]{width:58px;min-height:34px;border:0;background:transparent;color:#fff;text-align:right;font-weight:800}.jj-raise-editor label span{padding-right:6px;color:#91a69d;font-size:.7rem}.jj-raise-editor>b{min-width:48px;color:#f6dda0;font-size:.78rem;text-align:right}
.jj-main-actions{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px}.jj-action-btn{min-height:58px;border:0;border-radius:11px;color:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px;box-shadow:inset 0 1px rgba(255,255,255,.12),0 5px 12px rgba(0,0,0,.2);transition:transform .08s ease,filter .12s ease}.jj-action-btn:active{transform:translateY(1px) scale(.99)}.jj-action-btn small{font-size:.58rem;letter-spacing:.12em;opacity:.78}.jj-action-btn b{font-size:.88rem}.jj-fold{background:linear-gradient(#74403d,#562b29)}.jj-check,.jj-call{background:linear-gradient(#28745e,#185743)}.jj-raise{background:linear-gradient(#b47b28,#885813)}.jj-allin{background:linear-gradient(#7b3e76,#562752)}
.result-banner{position:absolute;z-index:20;left:50%;top:29%;transform:translateX(-50%);max-width:70%;padding:8px 14px;border-radius:10px;background:rgba(6,12,10,.91);border:1px solid rgba(246,216,125,.6);color:#fff4cc;box-shadow:0 8px 24px rgba(0,0,0,.3);font-size:.78rem;font-weight:800;text-align:center}
@media (max-width:1000px){#pokerRoom .poker-layout{grid-template-columns:1fr}#pokerRoom .table-side{display:none}#pokerTable{min-height:560px}}
@media (max-width:760px){
  #pokerRoom{margin:-8px -12px 0}#pokerRoom .room-head{padding:0 12px}.poker-zone.card{border-radius:0;padding:7px 6px calc(194px + env(safe-area-inset-bottom));border-left:0;border-right:0}.room-meta{display:none}
  #pokerTable{min-height:0;height:min(64vh,580px);aspect-ratio:auto;border-width:9px;border-radius:46% / 39%;margin:0;background:radial-gradient(ellipse at 50% 42%,#137452 0%,#09513a 52%,#053426 100%)}
  .felt-center{top:39%}.jj-board-card{width:44px;height:61px;font-size:1.05rem;border-radius:7px}.cards.board{gap:4px}.pot-display{padding:4px 9px;margin-top:7px}.pot-display b{font-size:.88rem}.hand-status{margin-top:5px}
  .jj-seat{width:102px}.jj-seat-box{padding:5px 6px 6px;border-radius:9px}.jj-avatar{display:none}.jj-seat-box .name{font-size:.62rem}.jj-seat-box .stack{font-size:.67rem}.jj-player-state{font-size:.48rem;padding:1px 4px}.jj-hole{top:-41px}.jj-hole .card-face{width:29px;height:41px;font-size:.72rem}.jj-seat.is-hero .jj-hole{top:-55px}.jj-seat.is-hero .jj-hole .card-face{width:39px;height:55px;font-size:.96rem}.dealer{transform:scale(.82)}
  .jj-bet-marker{padding:3px 6px;gap:4px}.jj-bet-marker i{width:10px;height:10px}.jj-bet-marker b{font-size:.68rem}
  .table-controls{padding:8px 8px 2px}.jj-ready-count{display:none}.jj-table-control-left,.jj-table-control-right{flex:1}.jj-table-control-right{justify-content:flex-end}.jj-table-control-left button,.jj-table-control-right button{min-height:38px;padding:0 9px;font-size:.7rem}
  .action-bar{position:fixed!important;z-index:72;left:0;right:0;bottom:calc(70px + env(safe-area-inset-bottom));margin:0;padding:8px 9px 9px;border-radius:15px 15px 0 0;border-left:0;border-right:0;border-bottom:0;background:rgba(11,16,15,.98);backdrop-filter:blur(12px);box-shadow:0 -12px 30px rgba(0,0,0,.25)}
  .jj-action-context{min-height:42px;margin-bottom:5px}.jj-action-context .jj-hero-cards .card-face,.jj-hero-summary .jj-hero-cards .card-face{width:34px;height:47px;font-size:.84rem}.jj-action-context>div:last-child span{font-size:.62rem}.jj-action-context>div:last-child b{font-size:.72rem}.jj-hero-summary{justify-content:flex-start;padding-left:4px}
  .jj-sizing{display:block;margin-bottom:6px}.jj-size-row{overflow-x:auto;flex-wrap:nowrap;padding-bottom:4px;scrollbar-width:none}.jj-size-row::-webkit-scrollbar{display:none}.jj-size-btn{flex:0 0 auto;min-height:31px;padding:0 13px}.jj-raise-editor{grid-template-columns:1fr 78px;gap:5px}.jj-raise-editor>b{display:none}.jj-raise-editor input[type=range]{height:25px}.jj-raise-editor input[type=number]{min-height:31px;font-size:16px}
  .jj-main-actions{gap:5px}.jj-action-btn{min-height:50px;border-radius:9px}.jj-action-btn small{font-size:.5rem}.jj-action-btn b{font-size:.75rem}.result-banner{top:25%;max-width:86%;font-size:.68rem}
}
@media (max-width:390px){.jj-board-card{width:39px;height:55px}.jj-seat{width:91px}.jj-seat-box .name{max-width:74px}.jj-main-actions{gap:4px}.jj-action-btn b{font-size:.7rem}.jj-size-btn{padding:0 10px}}
'''
    p.write_text(s, encoding='utf-8')


def _patch_sw(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    s = re.sub(r'jj-arena-live-v\d+', 'jj-arena-live-v24', s)
    p.write_text(s, encoding='utf-8')
