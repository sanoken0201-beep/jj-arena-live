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
          <div class="section-head"><div><div class="eyebrow">SIT &amp; GO</div><h3>次回大会</h3></div><span class="table-rule">6-MAX · 10 MIN LEVELS · BB ANTE</span></div>
          <div id="sitngoNext"></div>
        </div>
'''

_APP_PATCH = r'''
  // jj sitngo phase1 ui 2026-09-15
  let jjPlayMode='ring',jjSngPoll=null,jjSngClock=null;
  const jjSngStatusLabel={scheduled:'受付前',registration_open:'受付中',starting:'開始処理中',running:'開催中',finished:'終了',cancelled:'中止'};
  const jjSngLocal=v=>{const d=new Date(v);if(Number.isNaN(d.getTime()))return String(v||'—');return new Intl.DateTimeFormat('ja-JP',{month:'numeric',day:'numeric',weekday:'short',hour:'2-digit',minute:'2-digit'}).format(d)};
  const jjSngCountdown=deadline=>{const ms=new Date(deadline).getTime()-Date.now();if(!Number.isFinite(ms)||ms<=0)return '00:00';const sec=Math.floor(ms/1000),h=Math.floor(sec/3600),m=Math.floor((sec%3600)/60),s=sec%60;return h>0?`${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`:`${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`};
  function jjSngRefreshClocks(){document.querySelectorAll('[data-jj-sng-deadline]').forEach(el=>{el.textContent=jjSngCountdown(el.dataset.jjSngDeadline)})}
  function jjSngStructureHtml(levels){return `<details class="jj-sng-structure"><summary>ブラインドストラクチャーを見る</summary><div class="jj-sng-levels">${(levels||[]).map(x=>`<div class="jj-sng-level ${Number(x.level)===9?'target':''}"><span>Lv.${x.level}</span><b>${fmt(x.small_blind)} / ${fmt(x.big_blind)}</b><small>BBA ${fmt(x.bb_ante)} · ${x.minutes}分${Number(x.level)===9?' · 90分':''}</small></div>`).join('')}</div></details>`}
  function jjSngEmpty(){return `<article class="card jj-sng-empty"><div class="eyebrow">NO EVENT</div><h4>現在、開催予定はありません</h4><p class="hint">Sit&Goは定期開催ではありません。管理者が大会を設定すると、開始1時間前から先着順で参加受付が始まります。</p></article>`}
  function jjSngEventHtml(event,levels){
    const status=event.status||'scheduled',registered=!!event.is_registered,full=!!event.full;
    const registrationOpen=new Date(event.registration_opens_at).getTime(),starts=new Date(event.starts_at).getTime(),now=Date.now();
    const untilOpen=now<registrationOpen,untilStart=now<starts;
    let action='';
    if(status==='running')action=registered?`<div class="jj-sng-seat">あなたの席 <strong>Seat ${Number(event.seat)+1}</strong></div>`:'<div class="jj-sng-note">大会は開催中です。</div>';
    else if(registered&&event.can_cancel_registration)action=`<div class="jj-sng-reg"><span>参加登録済み · 受付順 #${event.registration_order||'—'}</span><button type="button" class="soft" data-sng-cancel="${safe(event.id)}">参加を取り消す</button></div>`;
    else if(event.can_register)action=`<button type="button" class="primary jj-sng-register" data-sng-register="${safe(event.id)}">参加する</button>`;
    else if(full)action='<button type="button" class="soft jj-sng-register" disabled>満席</button>';
    else if(untilOpen)action='<button type="button" class="soft jj-sng-register" disabled>受付開始前</button>';
    else if(!untilStart)action='<button type="button" class="soft jj-sng-register" disabled>受付終了</button>';
    const timer=untilOpen?`受付開始まで <b data-jj-sng-deadline="${safe(event.registration_opens_at)}">${jjSngCountdown(event.registration_opens_at)}</b>`:untilStart&&status!=='running'?`開始まで <b data-jj-sng-deadline="${safe(event.starts_at)}">${jjSngCountdown(event.starts_at)}</b>`:'定刻開始済み';
    const participants=status==='running'&&Array.isArray(event.participants)?`<div class="jj-sng-seats">${event.participants.filter(x=>x.status!=='cancelled').sort((a,b)=>Number(a.seat)-Number(b.seat)).map(x=>`<span>Seat ${Number(x.seat)+1} · ${safe(x.name)}</span>`).join('')}</div>`:'';
    return `<article class="card jj-sng-card"><div class="jj-sng-head"><div><div class="eyebrow">${safe(jjSngStatusLabel[status]||status)}</div><h4>${safe(event.name||'JJ Sit&Go')}</h4></div><span class="jj-sng-count">${event.participant_count}/${event.max_players}</span></div><div class="jj-sng-datetime">${safe(jjSngLocal(event.starts_at))}</div><div class="jj-sng-timer">${timer}</div><div class="jj-sng-rules"><span>6-max</span><span>10,000点</span><span>10分レベル</span><span>BB Ante</span><span>90分終了目標</span></div><p class="hint">受付は当日の開始1時間前から先着順。定刻になれば2〜6人で開始し、1人以下の場合は自動中止します。席は開始時にサーバー側で完全ランダムに決定します。</p>${action}${participants}${jjSngStructureHtml(levels||event.structure)}</article>`;
  }
  async function renderSitNGo(){
    const host=$('#sitngoNext');if(!host)return;
    try{const data=await api('/sitngo/next'),event=data?.event;host.innerHTML=event?jjSngEventHtml(event,data.structure):jjSngEmpty();jjSngRefreshClocks()}catch(err){host.innerHTML=`<article class="card empty">${safe(err.message)}</article>`}
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
    return source[:position] + "\n" + _APP_PATCH.rstrip() + source[position:]


def transform_styles(source: str) -> str:
    if SITNGO_UI_MARKER in source:
        return source
    return source.rstrip() + _CSS_PATCH + "\n"


__all__ = ["SITNGO_UI_MARKER", "transform_app_js", "transform_index", "transform_styles"]
