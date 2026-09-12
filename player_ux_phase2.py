from __future__ import annotations

"""Phase 2 player-experience hardening for JJ Arena online poker.

This layer is intentionally applied *after* ``player_ux_asset_transform``.  The
materialized v1.24.4 tree remains the parity oracle, while the production shim
serves deterministic edits at the original implementation sites.
"""

PHASE2_MARKER = "v2 player-ux phase2 participation 2026-09-12"


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"player UX phase2 drift at {label}: expected 1 source block, found {count}")
    return source.replace(old, new, 1)


def _replace_final_duplicate(source: str, old: str, new: str, label: str) -> str:
    """Replace the later of two known legacy renderer copies.

    The materialized client intentionally contains an older compatibility copy
    and a later authoritative table-controls renderer.  Treating either copy as
    unique made the drift guard fail correctly.  We now require exactly two
    copies and patch only the later, effective definition.
    """
    count = source.count(old)
    if count != 2:
        raise RuntimeError(f"player UX phase2 drift at {label}: expected 2 source blocks, found {count}")
    head, sep, tail = source.rpartition(old)
    if not sep:
        raise RuntimeError(f"player UX phase2 drift at {label}: final source block not found")
    return head + new + tail


def leave_after_hand_transition(state: dict, user_id: int, enabled: bool) -> str:
    """Pure state decision used by the POST route and smoke tests.

    ``leave_now`` means the caller may safely invoke the existing authoritative
    remove-player path. Reserving during an active hand only sets a lifecycle
    flag; it never folds the player or changes chips/cards/action state.
    """
    player = next(
        (p for p in state.get("seats", []) if int(p.get("user_id", -1)) == int(user_id)),
        None,
    )
    if player is None:
        return "left"
    if not enabled:
        player.pop("leave_after_hand", None)
        return "cancelled"
    if state.get("status") == "playing" and bool(player.get("in_hand")):
        player["leave_after_hand"] = True
        # A full leave reservation supersedes a temporary next-hand sit-out.
        player["sit_out_next"] = False
        return "reserved"
    return "leave_now"


def transform_app_js(source: str) -> str:
    if PHASE2_MARKER in source:
        return source

    source = _replace_once(
        source,
        """  async function openTable(id){currentTableId=id;$('#lobbyPanel').classList.add('hidden');$('#pokerRoom').classList.remove('hidden');await refreshMe();const data=await api('/tables/'+id);tableState=data.state;tableMessages=data.messages;renderPokerRoom();if(tableClock)clearInterval(tableClock);tableClock=setInterval(()=>{if(currentTableId&&tableState?.status==='playing')renderHandStatusOnly()},1000);await acquireWakeLock();connectTable(id)}
  function disconnectTable(){if(tableWS){tableWS.close();tableWS=null}if(tablePoll){clearInterval(tablePoll);tablePoll=null}if(tableHeartbeat){clearInterval(tableHeartbeat);tableHeartbeat=null}if(tableReconnect){clearTimeout(tableReconnect);tableReconnect=null}if(tableClock){clearInterval(tableClock);tableClock=null}releaseWakeLock();currentTableId=null;tableState=null;tableMessages=[];tableChatSig='';handLogSig='';wasMyTurn=false}
  function connectTable(id){if(tableHeartbeat){clearInterval(tableHeartbeat);tableHeartbeat=null}if(tableReconnect){clearTimeout(tableReconnect);tableReconnect=null}if(tableWS&&tableWS.readyState<2)tableWS.close();const proto=location.protocol==='https:'?'wss':'ws';tableWS=new WebSocket(`${proto}://${location.host}/ws/tables/${encodeURIComponent(id)}`);tableWS.onopen=()=>{if(tablePoll){clearInterval(tablePoll);tablePoll=null}tableHeartbeat=setInterval(()=>{if(tableWS?.readyState===WebSocket.OPEN)tableWS.send('ping')},15000)};tableWS.onmessage=e=>{try{const m=JSON.parse(e.data);if(m.type==='state'){tableState=m.state;tableMessages=m.messages||[];renderPokerRoom();refreshMe().catch(()=>{})}}catch{}};tableWS.onclose=()=>{if(tableHeartbeat){clearInterval(tableHeartbeat);tableHeartbeat=null}if(currentTableId===id&&!tablePoll)tablePoll=setInterval(async()=>{try{const d=await api('/tables/'+id);tableState=d.state;tableMessages=d.messages;renderPokerRoom()}catch{}},3000);if(currentTableId===id)tableReconnect=setTimeout(()=>connectTable(id),3000)}}
""",
        """  const jjV2PokerConfig={action_timeout_seconds:45};
  const jjV2Connection={mode:'idle',fresh:false,lastStateAt:0,lastTimeoutKey:''};
  async function jjV2LoadPokerConfig(){
    try{Object.assign(jjV2PokerConfig,await post('/poker-config',{}))}catch{}
    return jjV2PokerConfig;
  }
  function jjV2ConnectionLabel(){
    return ({ws:'リアルタイム接続',http:'最新状態取得',fallback:'HTTP同期中',connecting:'接続中',syncing:'再接続済み・同期中',reconnecting:'再接続中',idle:'未接続'})[jjV2Connection.mode]||'接続確認中';
  }
  function jjV2RenderConnection(){
    const meta=$('#roomMeta');
    if(meta){
      let badge=$('#jjConnectionStatus',meta);
      if(!badge){meta.insertAdjacentHTML('beforeend','<span id="jjConnectionStatus" class="jj-connection-status" aria-live="polite"></span>');badge=$('#jjConnectionStatus',meta)}
      const stamp=jjV2Connection.lastStateAt?new Date(jjV2Connection.lastStateAt).toLocaleTimeString('ja-JP',{hour:'2-digit',minute:'2-digit',second:'2-digit'}):'—';
      badge.classList.toggle('is-degraded',!jjV2Connection.fresh||jjV2Connection.mode==='fallback');
      badge.textContent=`${jjV2ConnectionLabel()} · 最新 ${stamp}`;
    }
    document.body.classList.toggle('jj-poker-state-stale',!!currentTableId&&!jjV2Connection.fresh);
    if(!jjV2Connection.fresh)document.querySelectorAll('#actionBar button,#actionBar input').forEach(el=>{el.disabled=true});
  }
  function jjV2SetConnection(mode,fresh=jjV2Connection.fresh){jjV2Connection.mode=mode;jjV2Connection.fresh=!!fresh;jjV2RenderConnection()}
  function jjV2TimeoutAction(logs,index){
    const prev=String(logs[index-1]||'').toLowerCase();
    return prev.includes(' checks')?'チェック':'フォールド';
  }
  function jjV2MaybeTimeoutNotice(previous,next){
    const prevHand=previous?.hand||{},hand=next?.hand||{},before=prevHand.log||[],logs=hand.log||[];
    if(!previous||String(prevHand.id||'')!==String(hand.id||'')||logs.length<=before.length)return;
    for(let i=before.length;i<logs.length;i++){
      const line=String(logs[i]||'');
      if(!line.endsWith(' timed out · sit out next'))continue;
      const key=`${hand.id||''}:${i}:${line}`;
      if(key===jjV2Connection.lastTimeoutKey)continue;
      jjV2Connection.lastTimeoutKey=key;
      if(me?.name&&line.startsWith(`${me.name} timed out`))toast(`時間切れで${jjV2TimeoutAction(logs,i)}しました。次ハンドから一時離席になります`);
    }
  }
  function jjV2AcceptState(source,previous){
    jjV2MaybeTimeoutNotice(previous,tableState);
    jjV2Connection.lastStateAt=Date.now();
    jjV2SetConnection(source==='ws'?'ws':source==='poll'?'fallback':'http',true);
  }
  document.addEventListener('click',e=>{
    if(jjV2Connection.fresh)return;
    const action=e.target.closest('#actionBar [data-action],#actionBar .jj-size-btn,#actionBar [data-jj-raise-step]');
    if(!action)return;
    e.preventDefault();e.stopImmediatePropagation();toast('最新の卓状態を同期中です。更新後に操作できます');
  },true);

  async function openTable(id){
    currentTableId=id;$('#lobbyPanel').classList.add('hidden');$('#pokerRoom').classList.remove('hidden');
    jjV2SetConnection('connecting',false);await refreshMe();
    const [data]=await Promise.all([api('/tables/'+id),jjV2LoadPokerConfig()]);
    tableState=data.state;tableMessages=data.messages;renderPokerRoom();jjV2AcceptState('http',null);
    if(tableClock)clearInterval(tableClock);tableClock=setInterval(()=>{if(currentTableId&&tableState?.status==='playing')renderHandStatusOnly()},1000);
    await acquireWakeLock();connectTable(id);
  }
  function disconnectTable(){
    if(tableWS){tableWS.close();tableWS=null}if(tablePoll){clearInterval(tablePoll);tablePoll=null}if(tableHeartbeat){clearInterval(tableHeartbeat);tableHeartbeat=null}if(tableReconnect){clearTimeout(tableReconnect);tableReconnect=null}if(tableClock){clearInterval(tableClock);tableClock=null}
    releaseWakeLock();currentTableId=null;tableState=null;tableMessages=[];tableChatSig='';handLogSig='';wasMyTurn=false;
    jjV2Connection.mode='idle';jjV2Connection.fresh=false;jjV2Connection.lastStateAt=0;jjV2RenderConnection();
  }
  function connectTable(id){
    if(tableHeartbeat){clearInterval(tableHeartbeat);tableHeartbeat=null}if(tableReconnect){clearTimeout(tableReconnect);tableReconnect=null}if(tableWS&&tableWS.readyState<2)tableWS.close();
    jjV2SetConnection('connecting',jjV2Connection.fresh);
    const proto=location.protocol==='https:'?'wss':'ws';tableWS=new WebSocket(`${proto}://${location.host}/ws/tables/${encodeURIComponent(id)}`);
    tableWS.onopen=()=>{
      if(tablePoll){clearInterval(tablePoll);tablePoll=null}
      jjV2SetConnection('syncing',false);
      tableHeartbeat=setInterval(()=>{if(tableWS?.readyState===WebSocket.OPEN)tableWS.send('ping')},15000);
    };
    tableWS.onmessage=e=>{try{const m=JSON.parse(e.data);if(m.type==='state'){const previous=tableState;tableState=m.state;tableMessages=m.messages||[];renderPokerRoom();jjV2AcceptState('ws',previous);refreshMe().catch(()=>{})}}catch{}};
    tableWS.onclose=()=>{
      if(tableHeartbeat){clearInterval(tableHeartbeat);tableHeartbeat=null}
      if(currentTableId!==id)return;
      jjV2SetConnection('reconnecting',false);
      const pollOnce=async()=>{try{const previous=tableState,d=await api('/tables/'+id);if(currentTableId!==id)return;tableState=d.state;tableMessages=d.messages||[];renderPokerRoom();jjV2AcceptState('poll',previous)}catch{}};
      if(!tablePoll){pollOnce();tablePoll=setInterval(pollOnce,3000)}
      tableReconnect=setTimeout(()=>connectTable(id),3000);
    };
  }
""",
        "connection freshness",
    )

    source = _replace_once(
        source,
        """  function renderHandLog(){const logs=tableState.hand?.log||[],sig=logs.join('|');if(sig===handLogSig)return;handLogSig=sig;$('#handLog').innerHTML=[...logs].reverse().map(x=>`<div>${safe(x)}</div>`).join('')||'<div>まだハンド履歴はありません</div>'}
""",
        """  function jjV2HandLogText(line,index,logs){
    const text=String(line||'');
    if(text.endsWith(' timed out · sit out next')){
      const name=text.slice(0,-' timed out · sit out next'.length);
      return `${name}：時間切れ → ${jjV2TimeoutAction(logs,index)}（次ハンドから一時離席）`;
    }
    return text;
  }
  function renderHandLog(){const logs=tableState.hand?.log||[],sig=logs.join('|');if(sig===handLogSig)return;handLogSig=sig;$('#handLog').innerHTML=logs.map((x,i)=>`<div>${safe(jjV2HandLogText(x,i,logs))}</div>`).reverse().join('')||'<div>まだハンド履歴はありません</div>'}
""",
        "timeout log language",
    )

    source = _replace_once(
        source,
        """if(result){const mine=(result.net_results||[]).find(x=>x.user_id===me.id);$('#resultBanner').innerHTML=`<b>${safe(result.message)}</b>${mine?`<span>Your result: <strong class="${Number(mine.bb)>=0?'positive':'negative'}">${Number(mine.bb)>=0?'+':''}${fmt(mine.bb)}bb / ${Number(mine.bb)>=0?'+':''}${fmt(Number(mine.bb)*3)}pt</strong></span>`:''}`;}""",
        """if(result){
      const mine=(result.net_results||[]).find(x=>Number(x.user_id)===Number(me.id)),gross=bb(Number(result.gross_pot||0)),rake=bb(Number(result.rake||0)),handId=tableState.hand?.id||'';
      const winners=(result.winners||[]).map(x=>x.name).filter(Boolean).join(' / ');
      $('#resultBanner').innerHTML=`<div class="jj-settlement-head"><b>ハンド精算</b><span>${winners?`勝者 ${safe(winners)}`:'ハンド終了'}</span></div><div class="jj-settlement-grid"><span>総ポット（卓全体） <b>${safe(gross)}</b></span><span>レーキ（卓全体） <b>${safe(rake)}</b></span>${mine?`<span>あなたの純損益 <strong class="${Number(mine.bb)>=0?'positive':'negative'}">${Number(mine.bb)>=0?'+':''}${fmt(mine.bb)}bb</strong></span><span>ランキング反映 <strong class="${Number(mine.bb)>=0?'positive':'negative'}">${Number(mine.bb)>=0?'+':''}${fmt(Number(mine.bb)*3)}pt</strong></span>`:''}</div>${handId?`<button class="soft" data-jj-review-hand="${safe(handId)}">直前のハンドを見る</button>`:''}<small class="jj-settlement-note">投入内訳とアクションはハンド分析で確認できます。レーキ表示は卓全体額です。</small>`;
    }""",
        "settlement summary",
    )

    source = _replace_once(
        source,
        """    const pct=Math.max(0,Math.min(100,(sec/45)*100));
""",
        """    const pct=Math.max(0,Math.min(100,(sec/Math.max(1,Number(jjV2PokerConfig?.action_timeout_seconds||45)))*100));
""",
        "server-derived action clock",
    )

    source = _replace_final_duplicate(
        source,
        """    const countText=tableState.session_active?`次ハンド ${nextPlayers.length}/6`:`準備 ${ready}/${nextPlayers.length}`;
    const leave=canLeaveNow?'<button class="ghost" id="leaveSeatBtn">テーブルから退席</button>':'';
    $('#tableControls').innerHTML=`<div class="jj-table-control-left">${readyButton}<span class="jj-ready-count">${countText}</span></div><div class="jj-table-control-right">${presence}${leave}</div>`;
""",
        """    const countText=tableState.session_active?`次ハンド ${nextPlayers.length}/6`:`準備 ${ready}/${nextPlayers.length}`;
    const leaveReserved=!!seated.leave_after_hand;
    if(leaveReserved)presence='';
    const leave=leaveReserved
      ? '<button class="soft" data-jj-leave-after="cancel">ハンド終了後の退席を取消</button>'
      : canLeaveNow
        ? '<button class="ghost" id="leaveSeatBtn">今すぐ退席</button>'
        : '<button class="ghost" data-jj-leave-after="reserve">このハンド終了後に退席</button>';
    const leaveNote=leaveReserved?'<span class="jj-leave-reservation">退席予約中 · 現在のハンドはそのままプレイします</span>':'';
    $('#tableControls').innerHTML=`<div class="jj-table-control-left">${readyButton}<span class="jj-ready-count">${countText}</span>${leaveNote}</div><div class="jj-table-control-right">${presence}${leave}</div>`;
""",
        "leave reservation controls",
    )

    insertion = """
  // Player lifecycle actions added by the 2026-09-12 audit. These use unique
  // endpoints and leave the existing immediate-leave and sit-out paths intact.
  document.addEventListener('click',async e=>{
    const leave=e.target.closest('[data-jj-leave-after]');
    if(leave){
      e.preventDefault();e.stopImmediatePropagation();
      if(!currentTableId)return;
      const enabled=leave.dataset.jjLeaveAfter==='reserve';leave.disabled=true;
      try{
        const result=await post(`/tables/${currentTableId}/leave-after-hand`,{enabled});
        tableState=result.state||tableState;renderPokerRoom();
        toast(result.status==='reserved'?'ハンド終了後に退席します。現在のハンドは続行します':result.status==='cancelled'?'退席予約を取り消しました':'テーブルから退席しました');
      }catch(err){leave.disabled=false;toast(err.message)}
      return;
    }
    const review=e.target.closest('[data-jj-review-hand]');
    if(review){
      e.preventDefault();e.stopImmediatePropagation();
      if(typeof jjOpenHand!=='function')return toast('ハンド分析を準備中です');
      try{await jjOpenHand(review.dataset.jjReviewHand)}catch(err){toast(err.message)}
    }
  },true);

"""
    anchor = "  // Desktop bet markers use explicit poker-table lanes rather than the old\n"
    if source.count(anchor) != 1:
        raise RuntimeError("player UX phase2 drift at lifecycle listener anchor")
    source = source.replace(anchor, insertion + anchor, 1)

    marker_anchor = "  // v1.24.0 unified online-poker presentation layer."
    if source.count(marker_anchor) != 1:
        raise RuntimeError("player UX phase2 drift at marker anchor")
    return source.replace(marker_anchor, f"  // {PHASE2_MARKER}\n{marker_anchor}", 1)


PHASE2_CSS = r'''

/* v2 player-ux phase2 participation 2026-09-12 */
.jj-connection-status{display:inline-flex;align-items:center;gap:.35rem;margin-left:.55rem;padding:.2rem .5rem;border-radius:999px;font-size:.68rem;font-weight:800;white-space:nowrap;background:rgba(87,194,139,.13);color:var(--accent2,#8ee7bb)}
.jj-connection-status.is-degraded{background:rgba(245,190,90,.14);color:#f3d981}
.jj-poker-state-stale #actionBar{opacity:.78}
.jj-leave-reservation{display:block;margin-top:.25rem;font-size:.72rem;color:#f3d981}
.jj-settlement-head{display:flex;align-items:baseline;justify-content:space-between;gap:.75rem}
.jj-settlement-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.35rem .8rem;margin:.45rem 0}
.jj-settlement-grid span{font-size:.76rem}.jj-settlement-grid b,.jj-settlement-grid strong{margin-left:.25rem}
.jj-settlement-note{display:block;margin-top:.35rem;opacity:.72}
@media(max-width:760px){.jj-connection-status{display:flex;margin:.3rem 0 0}.jj-settlement-grid{grid-template-columns:1fr}.jj-settlement-head{align-items:flex-start;flex-direction:column;gap:.1rem}}
'''


def transform_styles(source: str) -> str:
    if PHASE2_MARKER in source:
        return source
    return source.rstrip() + PHASE2_CSS + "\n"
