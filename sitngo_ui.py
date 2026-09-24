from __future__ import annotations

SITNGO_UI_MARKER = "jj sitngo phase1 ui 2026-09-15"

_PLAY_SWITCH = r'''
        <div class="jj-play-switch" role="tablist" aria-label="オンラインポーカー種別">
          <button type="button" class="active" data-play-mode="ring" role="tab" aria-selected="true">リング</button>
          <button type="button" data-play-mode="sitngo" role="tab" aria-selected="false">Sit&amp;Go</button>
        </div>
'''

_SITNGO_PANEL = r'''
        <div id="sitngoPanel" class="hidden">
          <div class="section-head"><div><div class="eyebrow">SIT &amp; GO</div><h3>次回大会</h3></div><span class="table-rule">6-MAX · 12 HAND LEVELS · BB ANTE</span></div>
          <div id="sitngoNext"></div>
        </div>
'''

_APP_PATCH = r'''
  // jj sitngo phase1 ui 2026-09-15
  // jj sng 12-hand levels 2026-09-18
  let jjPlayMode='ring',jjSngPoll=null,jjSngClock=null;
  const jjSngStatusLabel={scheduled:'受付前',registration_open:'受付中',starting:'開始処理中',running:'開催中',finished:'終了',cancelled:'中止'};
  const jjSngLocal=v=>{const d=new Date(v);if(Number.isNaN(d.getTime()))return String(v||'—');return new Intl.DateTimeFormat('ja-JP',{month:'numeric',day:'numeric',weekday:'short',hour:'2-digit',minute:'2-digit'}).format(d)};
  const jjSngCountdown=deadline=>{const ms=new Date(deadline).getTime()-Date.now();if(!Number.isFinite(ms)||ms<=0)return '00:00';const sec=Math.floor(ms/1000),h=Math.floor(sec/3600),m=Math.floor((sec%3600)/60),s=sec%60;return h>0?`${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`:`${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`};
  function jjSngRefreshClocks(){document.querySelectorAll('[data-jj-sng-deadline]').forEach(el=>{el.textContent=jjSngCountdown(el.dataset.jjSngDeadline)})}
  const jjSngLevelSummary=levels=>'12ハンド/レベル';
  function jjSngStructureHtml(levels){return `<details class="jj-sng-structure"><summary>ブラインドストラクチャーを見る</summary><div class="jj-sng-levels">${(levels||[]).map(x=>`<div class="jj-sng-level"><span>Lv.${x.level}</span><b>${fmt(x.small_blind)} / ${fmt(x.big_blind)}</b><small>BBA ${fmt(x.bb_ante)} · 12ハンド</small></div>`).join('')}</div></details>`}
  function jjSngEmpty(){return `<article class="card jj-sng-empty"><div class="eyebrow">NO EVENT</div><h4>現在、開催予定はありません</h4><p class="hint">Sit&Goは定期開催ではありません。管理者が大会を設定すると、開始1時間前から先着順で参加受付が始まります。</p></article>`}
  function jjSngHistoryHtml(event){
    const results=Array.isArray(event?.tournament?.results)?[...event.tournament.results].sort((a,b)=>Number(a.place)-Number(b.place)||String(a.name||'').localeCompare(String(b.name||''),'ja')):[];
    const rows=results.length?results.map(x=>{const prize=Number(x.prize_points||0);return `<div class="jj-sng-history-row"><b>${Number(x.place)}位</b><span>${safe(x.name||'—')}</span><strong>${prize>0?'+':''}${fmt(prize)} pt</strong></div>`}).join(''):'<div class="jj-sng-history-empty">結果情報を取得できません。</div>';
    const detail=event.table_id?`<button type="button" class="soft jj-sng-history-detail" data-sng-open="${safe(event.table_id)}">詳細を見る</button>`:'';
    return `<article class="card jj-sng-history"><div class="jj-sng-history-head"><div><div class="eyebrow">RESULT</div><h4>${safe(event.name||'JJ Sit&Go')}</h4></div><span>${safe(jjSngLocal(event.starts_at))}</span></div><div class="jj-sng-history-results">${rows}</div><div class="jj-sng-history-foot"><span>賞金総額 ${fmt(Number(event.prize_points||0))} pt</span>${detail}</div></article>`;
  }
  function jjSngEventHtml(event,levels){
    const status=event.status||'scheduled',registered=!!event.is_registered,full=!!event.full,eventLevels=event.structure||levels||[];
    const registrationOpen=new Date(event.registration_opens_at).getTime(),starts=new Date(event.starts_at).getTime(),now=Date.now();
    const untilOpen=now<registrationOpen,untilStart=now<starts;
    let action='';
    if(status==='running'||status==='finished')action=event.table_id?`<button type="button" class="primary jj-sng-register" data-sng-open="${safe(event.table_id)}">${status==='finished'?'結果を見る':registered?'大会テーブルへ':'観戦する'}</button>`:'<div class="jj-sng-note">テーブル準備中</div>';
    else if(status==='starting')action='<div class="jj-sng-note">前のSit&Go終了後に開始します。受付は締め切られています。</div>';
    else if(registered&&event.can_cancel_registration)action=`<div class="jj-sng-reg"><span>参加登録済み · 受付順 #${event.registration_order||'—'}</span><button type="button" class="soft" data-sng-cancel="${safe(event.id)}">参加を取り消す</button></div>`;
    else if(event.can_register)action=`<button type="button" class="primary jj-sng-register" data-sng-register="${safe(event.id)}">参加する</button>`;
    else if(full)action='<button type="button" class="soft jj-sng-register" disabled>満席</button>';
    else if(untilOpen)action='<button type="button" class="soft jj-sng-register" disabled>受付開始前</button>';
    else if(!untilStart)action='<button type="button" class="soft jj-sng-register" disabled>受付終了</button>';
    const timer=status==='starting'?'前のSit&Go終了後に開始':untilOpen?`受付開始まで <b data-jj-sng-deadline="${safe(event.registration_opens_at)}">${jjSngCountdown(event.registration_opens_at)}</b>`:untilStart&&status!=='running'?`開始まで <b data-jj-sng-deadline="${safe(event.starts_at)}">${jjSngCountdown(event.starts_at)}</b>`:'定刻開始済み';
    const participants=status==='running'&&Array.isArray(event.participants)?`<div class="jj-sng-seats">${event.participants.filter(x=>x.status!=='cancelled').sort((a,b)=>Number(a.seat)-Number(b.seat)).map(x=>`<span>Seat ${Number(x.seat)+1} · ${safe(x.name)}</span>`).join('')}</div>`:'';
    return `<article class="card jj-sng-card"><div class="jj-sng-head"><div><div class="eyebrow">${safe(jjSngStatusLabel[status]||status)}</div><h4>${safe(event.name||'JJ Sit&Go')}</h4></div><span class="jj-sng-count">${event.participant_count}/${event.max_players}</span></div><div class="jj-sng-datetime">${safe(jjSngLocal(event.starts_at))}</div><div class="jj-sng-timer">${timer}</div><div class="jj-sng-rules"><span>6-max</span><span>${fmt(event.starting_stack)}点</span><span>${jjSngLevelSummary(eventLevels)}</span><span>BB Ante</span><span>参加費 ${fmt(event.entry_fee)} pt · 賞金 ${fmt(event.prize_points)} pt</span><span>再参加なし</span></div><p class="hint">受付は当日の開始1時間前から先着順。定刻になれば2〜6人で開始し、1人以下の場合は自動中止します。席は抽選で決定します。通信切断中もブラインドは発生します。</p><details><summary>プライズ配分</summary>${Object.entries(event.payout_percentages||{}).map(([n,r])=>`<p>${safe(n)}人：${r.map((v,i)=>`${i+1}位 ${safe(v)}%`).join(" / ")}</p>`).join("")}<p>登録時に参加費を徴収します。開始前の取消・中止で返却。同順位は該当順位分を均等分配し、0.01pt単位で端数調整します。</p></details>${action}${participants}${jjSngStructureHtml(eventLevels)}</article>`;
  }
  async function renderSitNGo(){
    const host=$('#sitngoNext');if(!host)return;
    try{const data=await api('/sitngo/next'),event=data?.event,upcoming=data?.upcoming;if(currentTableId?.startsWith('sng-'))return;const current=event?jjSngEventHtml(event,data.structure):jjSngEmpty(),next=upcoming&&upcoming.id!==event?.id?`<div class="eyebrow jj-sng-next-label">NEXT EVENT</div>${jjSngEventHtml(upcoming,upcoming.structure||data.structure)}`:'',recent=data.recent||[],history=recent.length?`<div class="jj-sng-history-label"><div class="eyebrow">HISTORY</div><span>直近5大会</span></div>${recent.map(jjSngHistoryHtml).join('')}`:'';host.innerHTML=current+next+history;jjSngRefreshClocks()}catch(err){host.innerHTML=`<article class="card empty">${safe(err.message)}</article>`}
  }
  function jjSetPlayMode(mode){
    jjPlayMode=mode==='sitngo'?'sitngo':'ring';
    $$('[data-play-mode]').forEach(b=>{const on=b.dataset.playMode===jjPlayMode;b.classList.toggle('active',on);b.setAttribute('aria-selected',on?'true':'false')});
    const lobby=$('#lobbyPanel'),sng=$('#sitngoPanel'),room=$('#pokerRoom');
    if(jjPlayMode==='sitngo'){
      if(currentTableId)disconnectTable();
      lobby?.classList.add('hidden');room?.classList.add('hidden');sng?.classList.remove('hidden');
      renderSitNGo();
      clearInterval(jjSngPoll);jjSngPoll=setInterval(()=>{if(currentView==='tables'&&jjPlayMode==='sitngo')renderSitNGo()},15000);
      clearInterval(jjSngClock);jjSngClock=setInterval(jjSngRefreshClocks,1000);
    }else{
      sng?.classList.add('hidden');lobby?.classList.remove('hidden');
      clearInterval(jjSngPoll);jjSngPoll=null;clearInterval(jjSngClock);jjSngClock=null;
      renderLobby();
    }
  }
  const jjSngBaseRenderLobby=renderLobby;
  renderLobby=async function(){
    if(jjPlayMode==='sitngo'){
      $('#lobbyPanel')?.classList.add('hidden');$('#pokerRoom')?.classList.add('hidden');$('#sitngoPanel')?.classList.remove('hidden');
      return renderSitNGo();
    }
    $('#sitngoPanel')?.classList.add('hidden');return jjSngBaseRenderLobby();
  };
  document.addEventListener('click',async e=>{
    const mode=e.target.closest('[data-play-mode]');if(mode){e.preventDefault();jjSetPlayMode(mode.dataset.playMode);return}
    const reg=e.target.closest('[data-sng-register]');if(reg){reg.disabled=true;try{await post(`/sitngo/${reg.dataset.sngRegister}/register`,{});toast('Sit&Goに参加登録しました');await renderSitNGo()}catch(err){toast(err.message);reg.disabled=false}return}
    const cancel=e.target.closest('[data-sng-cancel]');if(cancel){if(!confirm('Sit&Goの参加登録を取り消しますか？'))return;cancel.disabled=true;try{await post(`/sitngo/${cancel.dataset.sngCancel}/cancel-registration`,{});toast('参加登録を取り消しました');await renderSitNGo()}catch(err){toast(err.message);cancel.disabled=false}}
  });
'''

_CSS_PATCH = r'''

/* jj sitngo phase1 ui 2026-09-15 */
#jjSngTableInfo{display:flex;flex-wrap:wrap;justify-content:space-between;gap:4px 12px;padding:5px 12px;color:#e8d39d;font-size:12px;font-variant-numeric:tabular-nums}
.jj-sng-finish{display:flex;flex-wrap:wrap;justify-content:center;gap:8px 16px;padding:12px}
.jj-sng-finish strong,.jj-sng-finish small{flex-basis:100%;text-align:center}
body.jj-sng-playing .jj-empty-seat,body.jj-sng-playing [data-table-presence],body.jj-sng-playing #leaveSeatBtn,body.jj-sng-playing [data-jj-leave-after],body.jj-sng-playing #rebuyBtn,body.jj-sng-playing #jjReadyBtn,body.jj-sng-playing #jjJoinTableBtn,body.jj-sng-playing .jj-room-join-banner{display:none!important}

.jj-play-switch{display:flex;gap:6px;width:max-content;margin:0 auto 18px;padding:5px;border:1px solid rgba(255,255,255,.1);border-radius:14px;background:rgba(11,23,18,.48)}
.jj-play-switch button{border:0;border-radius:10px;padding:9px 20px;background:transparent;color:var(--muted,#9fb2aa);font-weight:800;cursor:pointer}
.jj-play-switch button.active{background:var(--accent,#d8b45a);color:#102018}
#sitngoPanel{max-width:860px;margin:0 auto}
.jj-sng-card,.jj-sng-empty{padding:22px}
.jj-sng-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}
.jj-sng-head h4,.jj-sng-empty h4{margin:5px 0 0;font-size:1.35rem}
.jj-sng-count{display:grid;place-items:center;min-width:64px;height:42px;border-radius:12px;background:rgba(255,255,255,.07);font-weight:900;font-variant-numeric:tabular-nums}
.jj-sng-datetime{margin-top:18px;font-size:1.12rem;font-weight:850}
.jj-sng-timer{margin-top:8px;font-size:.9rem;color:var(--muted,#9fb2aa)}
.jj-sng-timer b{color:var(--text,#fff);font-variant-numeric:tabular-nums}
.jj-sng-rules{display:flex;flex-wrap:wrap;gap:7px;margin:16px 0 10px}
.jj-sng-rules span{padding:5px 9px;border:1px solid rgba(255,255,255,.09);border-radius:999px;font-size:.72rem;font-weight:800}
.jj-sng-register{width:100%;margin-top:10px;min-height:44px}
.jj-sng-reg{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:14px;padding:12px;border-radius:12px;background:rgba(255,255,255,.05)}
.jj-sng-reg span{font-weight:800}
.jj-sng-seat{margin-top:14px;padding:14px;border-radius:12px;background:rgba(216,180,90,.12);text-align:center}
.jj-sng-seat strong{font-size:1.1rem;margin-left:6px}
.jj-sng-note{margin-top:14px;color:var(--muted,#9fb2aa)}
.jj-sng-history-label{display:flex;align-items:end;justify-content:space-between;gap:12px;margin:22px 2px 8px}
.jj-sng-history-label span{font-size:.74rem;color:var(--muted,#9fb2aa);font-weight:800}
.jj-sng-history{padding:16px 18px;margin-top:10px}
.jj-sng-history-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
.jj-sng-history-head h4{margin:3px 0 0;font-size:1rem}
.jj-sng-history-head>span{font-size:.72rem;color:var(--muted,#9fb2aa);white-space:nowrap}
.jj-sng-history-results{display:grid;gap:6px;margin-top:12px}
.jj-sng-history-row{display:grid;grid-template-columns:52px minmax(0,1fr) auto;align-items:center;gap:10px;padding:9px 10px;border-radius:10px;background:rgba(255,255,255,.045)}
.jj-sng-history-row b{font-variant-numeric:tabular-nums}
.jj-sng-history-row span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.jj-sng-history-row strong{font-variant-numeric:tabular-nums;white-space:nowrap}
.jj-sng-history-empty{padding:10px;color:var(--muted,#9fb2aa);font-size:.82rem}
.jj-sng-history-foot{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:10px;color:var(--muted,#9fb2aa);font-size:.76rem}
.jj-sng-history-detail{min-height:34px;padding:7px 12px}
.jj-sng-seats{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;margin-top:12px}
.jj-sng-seats span{padding:9px 10px;border-radius:10px;background:rgba(255,255,255,.045);font-size:.78rem}
.jj-sng-structure{margin-top:16px;border-top:1px solid rgba(255,255,255,.08);padding-top:12px}
.jj-sng-structure summary{cursor:pointer;font-weight:800;font-size:.82rem}
.jj-sng-levels{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin-top:12px}
.jj-sng-level{display:grid;gap:2px;padding:9px;border-radius:10px;background:rgba(255,255,255,.04)}
.jj-sng-level.target{outline:1px solid rgba(216,180,90,.5)}
.jj-sng-level span,.jj-sng-level small{font-size:.64rem;color:var(--muted,#9fb2aa)}
.jj-sng-level b{font-size:.78rem}
@media(max-width:760px){
  .jj-play-switch{width:100%;display:grid;grid-template-columns:1fr 1fr}
  .jj-play-switch button{width:100%;padding:9px 8px}
  .jj-sng-card,.jj-sng-empty{padding:16px}
  .jj-sng-history{padding:14px}
  .jj-sng-history-head{align-items:flex-start}
  .jj-sng-history-row{grid-template-columns:44px minmax(0,1fr) auto;gap:7px;padding:8px}
  .jj-sng-history-foot{align-items:stretch;flex-direction:column}
  .jj-sng-history-detail{width:100%}
  .jj-sng-reg{align-items:stretch;flex-direction:column}
  .jj-sng-seats{grid-template-columns:1fr}
  .jj-sng-levels{grid-template-columns:repeat(2,minmax(0,1fr))}
}
'''


def transform_index(source: str) -> str:
    if f"<!-- {SITNGO_UI_MARKER} -->" in source:
        return source
    lobby_anchor = '        <div id="lobbyPanel">'
    room_anchor = '        <div id="pokerRoom" class="hidden">'
    if source.count(lobby_anchor) != 1 or source.count(room_anchor) != 1:
        raise RuntimeError("Sit&Go UI drift: poker lobby anchors changed")
    html = source.replace(lobby_anchor, _PLAY_SWITCH + lobby_anchor, 1)
    html = html.replace(room_anchor, _SITNGO_PANEL + room_anchor, 1)
    return html.replace("</body>", f"  <!-- {SITNGO_UI_MARKER} -->\n</body>", 1)


def transform_app_js(source: str) -> str:
    if SITNGO_UI_MARKER in source:
        return source
    anchor = "\n  init();"
    position = source.rfind(anchor)
    if position < 0:
        raise RuntimeError("Sit&Go UI drift: init anchor not found")
    value = source[:position] + "\n" + _APP_PATCH.rstrip() + source[position:]
    end = value.rfind("})();")
    if end < 0:
        raise RuntimeError("Sit&Go gameplay UI: final closure missing")
    return value[:end] + _GAMEPLAY_PATCH + value[end:]


def transform_styles(source: str) -> str:
    if SITNGO_UI_MARKER in source:
        return source
    return source.rstrip() + _CSS_PATCH + "\n"


__all__ = ["SITNGO_UI_MARKER", "transform_app_js", "transform_index", "transform_styles"]

_GAMEPLAY_PATCH = r'''

  // Sit&Go gameplay uses the ring renderer, input handlers and state transport.
  const jjSngRingOpen=openTable;
  openTable=async function(id){
    const result=await jjSngRingOpen(id);
    if(tableState?.tournament){jjPlayMode='sitngo';$('#sitngoPanel')?.classList.add('hidden')}
    return result;
  };
  const jjSngRingControls=renderTableControls;
  renderTableControls=function(){
    if(!tableState?.tournament)return jjSngRingControls();
    const t=tableState.tournament,result=t.results?.find(x=>x.user_id===me?.id);
    $('#tableControls').innerHTML=`<span class="hint">${result?`${result.place}位${t.status==='finished'?' · 大会終了':' · 観戦中'}`:`参加費 ${Number(t.entry_fee||0)} pt · 再参加なし`}</span>`;
  };
  const jjSngRingSeat=renderSeat;
  renderSeat=function(seat){
    if(tableState?.tournament&&!tableState.seats.some(p=>p.seat===seat))return '';
    return jjSngRingSeat(seat);
  };
  function jjSngTableClock(){
    const el=$('#jjSngTableInfo'),t=tableState?.tournament;if(!el||!t)return;
    el.innerHTML=`<span>Lv.${Number(t.level)} · ${fmt(tableState.small_blind)}/${fmt(tableState.big_blind)} · BBA ${fmt(t.bb_ante)}</span><span>${t.status==='finished'?'終了':`${Number(t.hand_in_level||0)}/${Number(t.hands_per_level||12)}ハンド`} · 残り${Number(t.remaining)}/${Number(t.entrants)}人</span>`;
  }
  const jjSngRingRoom=renderPokerRoom;
  renderPokerRoom=function(){
    jjSngRingRoom();
    const t=tableState?.tournament;document.body.classList.toggle('jj-sng-playing',!!t&&!!currentTableId);
    if(!t){$('#jjSngTableInfo')?.remove();return}
    $('#sitngoPanel')?.classList.add('hidden');
    const head=$('#pokerRoom .room-head');
    if(head&&!$('#jjSngTableInfo'))head.insertAdjacentHTML('afterend','<div id="jjSngTableInfo" role="status"></div>');
    jjSngTableClock();
    $('#jjObserverJoin')?.remove();
    if(t.status==='finished'){
      const ps=t.point_statement,sign=v=>Number(v||0)>0?`+${Number(v)}`:String(Number(v||0));
      const statement=ps?`<div class="jj-sng-point-statement"><b>あなたのポイント精算</b><span>参加費 ${sign(ps.entry_points)} pt</span>${Number(ps.refund_points||0)?`<span>返金 +${Number(ps.refund_points)} pt</span>`:''}<span>賞金 +${Number(ps.prize_points||0)} pt</span><strong>大会増減 ${sign(ps.net_points)} pt</strong></div>`:'';
      $('#actionBar').innerHTML=`<div class="jj-sng-finish"><strong>大会終了</strong>${t.results.map(x=>`<span>${x.place}位 · ${safe(x.name)} · ${Number(x.prize_points||0)} pt</span>`).join('')}<small>賞金総額 ${Number(t.prize_points||0)} pt</small>${statement}</div>`;
    }else if(t.results.some(x=>x.user_id===me?.id)){
      const r=t.results.find(x=>x.user_id===me.id);
      $('#actionBar').innerHTML=`<div class="jj-sng-finish"><strong>${r.place}位で終了しました</strong><span>このまま観戦できます</span></div>`;
    }
  };
  const jjSngFinalLobby=renderLobby;
  renderLobby=async function(){if(currentTableId?.startsWith('sng-'))return;return jjSngFinalLobby()};
  const jjSngFinalClocks=jjSngRefreshClocks;
  jjSngRefreshClocks=function(){jjSngFinalClocks();jjSngTableClock()};
  document.addEventListener('click',async e=>{
    const open=e.target.closest('[data-sng-open]');if(!open)return;
    open.disabled=true;try{await openTable(open.dataset.sngOpen)}catch(err){toast(err.message);open.disabled=false}
  });

'''
