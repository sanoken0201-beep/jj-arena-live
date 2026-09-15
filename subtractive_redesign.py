from __future__ import annotations

"""Final subtractive UI pass for JJ Arena.

The materialized v1.24.4 browser bundle is immutable.  This transform runs after
all historical UX transforms and removes non-essential in-hand/lobby surface
without changing poker rules, settlement, hand-history persistence, or the
admin APIs.
"""

import re

SUBTRACTIVE_RED282_MARKER = "jj subtractive redesign 2026-09-15"


def _remove_primary_nav(html: str, view: str) -> str:
    pattern = re.compile(
        rf'\s*<button class="nav" data-view="{re.escape(view)}">.*?</button>',
        re.DOTALL,
    )
    return pattern.sub("", html, count=1)


def transform_index(source: str) -> str:
    if f"<!-- {SUBTRACTIVE_RED282_MARKER} -->" in source:
        return source

    html = _remove_primary_nav(source, "schedule")
    html = _remove_primary_nav(html, "discussion")

    # Keep the existing Home composition; only make its table copy truthful.
    html = html.replace("6-max固定・0.5/1bb・2卓。", "6-max固定・0.5/1bb・1卓。")
    html = html.replace("2 TABLES · 6-MAX · 150BB", "1 TABLE · 6-MAX · 150BB")

    # The calendar becomes part of the announcement workflow.  The legacy
    # schedule section remains in the DOM for rollback/data compatibility but
    # has no primary navigation and is hidden by the final CSS pass.
    html = html.replace("<h3>お知らせ / 外部イベント</h3>", "<h3>お知らせ / 活動予定</h3>")

    # The served-assets layer may already have shortened the canonical notice,
    # so support both the canonical and compiled forms here.
    html = html.replace(
        "JJ内の練習用プレイマネーテーブルです。A/Bの2卓のみ、6-max、0.5/1bb、着席時150bb固定。各ハンドは10% rake・5bb capで、結果は1bb=3ptとして後期ランキングへ自動反映されます。テーブル画面との接続・操作が15分ない場合、ハンド終了後に自動離席します。",
        "JJ内の練習用プレイマネーテーブルです。6-max、0.5/1bb、着席時150bb固定。結果は1bb=3ptとして後期ランキングへ自動反映されます。15分無操作の場合はハンド終了後に自動離席します。",
    )
    html = html.replace(
        "プレイマネー｜6-max｜0.5/1bb｜150bb固定｜rake 10%・5bb cap｜ランキング 1bb=3pt｜15分無操作でハンド終了後に自動離席",
        "プレイマネー｜6-max｜0.5/1bb｜150bb固定｜ランキング 1bb=3pt｜15分無操作でハンド終了後に自動離席",
    )

    return html.replace("</body>", f"  <!-- {SUBTRACTIVE_RED282_MARKER} -->\n</body>", 1)


_APP_PATCH = r'''
  // jj subtractive redesign 2026-09-15
  // Keep one public ring table while retaining the second server table as a
  // rollback-compatible implementation detail.
  renderLobby=async function(){
    if(currentTableId)return;
    $('#lobbyPanel').classList.remove('hidden');$('#pokerRoom').classList.add('hidden');
    const raw=await api('/tables'),tables=Array.isArray(raw)?raw:[],t=tables[0];
    $('#tableCards').innerHTML=t?(()=>{
      const seated=Number(t.seated||0),active=Number(t.players||0),maxSeats=Number(t.max_seats||6),full=seated>=maxSeats,extra=[];
      if(seated!==active)extra.push(`着席中 ${seated}/${maxSeats}`);
      if(Number(t.sitouts||0)>0)extra.push(`一時離席 ${Number(t.sitouts||0)}`);
      return `<article class="lobby-card jj-sub-single-table"><div class="eyebrow ${t.status==='playing'?'status-live':''}">${t.status==='playing'?'● HAND IN PROGRESS':'OPEN TABLE'}</div><h4>${safe(t.name||'JJ Ring')}</h4><div class="lobby-stats"><span>参加者 ${active}/${maxSeats}</span>${extra.map(x=>`<span>${x}</span>`).join('')}<span>0.5 / 1 bb</span><span>150bb start</span></div><p class="hint">観戦だけでも入れます。プレイする場合は「着席する」を押してください。</p><div class="jj-lobby-actions"><button class="soft" data-open-table="${safe(t.id)}">観戦する</button><button class="primary" data-jj-join="${safe(t.id)}" ${full?'disabled':''}>${full?'満席':'着席する · 150bb'}</button></div></article>`;
    })():'<div class="card empty">テーブルがありません</div>';
  };

  // Preserve the fully hardened action renderer (clock, pending-state,
  // all-in confirmation, keyboard safety), then remove only sizing shortcuts.
  const jjSubBaseRenderActionBar=renderActionBar;
  renderActionBar=function(){
    const draft=Number($('#raiseTo')?.value);
    jjSubBaseRenderActionBar();
    const bar=$('#actionBar'),input=$('#raiseTo');
    if(!bar||!input)return;
    bar.querySelector('.jj-size-row')?.remove();
    bar.querySelector('#raiseSlider')?.remove();
    bar.querySelectorAll('[data-jj-raise-step],[data-pot-pct],[data-raise-bb],[data-allin-size],.jj-size-settings,[data-jj-sizing-settings]').forEach(el=>el.remove());
    const stepper=bar.querySelector('.jj-v124-stepper');
    if(stepper){
      stepper.querySelectorAll('button').forEach(el=>el.remove());
      stepper.classList.add('jj-sub-manual-stepper');
    }
    input.step='0.01';
    input.inputMode='decimal';
    const bounds=typeof jjRaiseBounds==='function'?jjRaiseBounds():{min:Number(input.min||0),max:Number(input.max||0)};
    const min=Number(bounds.min||0),max=Number(bounds.max||0);
    if(Number.isFinite(draft)&&draft>=min&&(!max||draft<=max))input.value=String(Math.round(draft*100)/100);
    let hint=bar.querySelector('.jj-sub-bet-hint');
    if(!hint&&stepper){hint=document.createElement('small');hint.className='jj-sub-bet-hint';stepper.appendChild(hint)}
    if(hint)hint.textContent=`Min ${Math.round(min*100)/100}bb · Max ${Math.round(max*100)/100}bb · 数値を直接入力`;
    if(typeof jjV185SyncRaiseUi==='function')jjV185SyncRaiseUi();
  };

  // Chat and the live action log are deliberately absent during a hand.  The
  // persisted hand-history/review APIs remain untouched for post-hand review.
  renderTableChat=function(){};
  renderHandLog=function(){};

  const jjSubBaseRenderPokerRoom=renderPokerRoom;
  renderPokerRoom=function(){
    jjSubBaseRenderPokerRoom();
    const meta=$('#roomMeta');
    if(meta)meta.textContent=String(meta.textContent||'').replace(/\s*[·|]\s*rake.*$/i,'').replace(/\s+rake.*$/i,'');
  };

  // Home keeps its current layout.  Only constrain the live-table card to the
  // single public table and allow dated announcements to drive "next session".
  const jjSubBaseRenderHome=renderHome;
  renderHome=async function(){
    await jjSubBaseRenderHome();
    const tableHost=$('#homeTables');
    if(tableHost){const items=[...tableHost.children];items.slice(1).forEach(el=>el.remove())}
    try{
      const announcements=await api('/announcements'),today=new Date().toISOString().slice(0,10);
      const upcoming=(Array.isArray(announcements)?announcements:[]).filter(x=>x?.date&&x.date>=today&&x.kind!=='external').sort((a,b)=>String(a.date).localeCompare(String(b.date)))[0];
      if(upcoming&&$('#homeSchedule'))$('#homeSchedule').innerHTML=`<div class="next-session"><b>${safe(upcoming.date)}</b><strong>${safe(upcoming.title||'JJ活動')}</strong><span>${safe(upcoming.body||'')}</span></div>`;
    }catch{}
  };

  // Existing calendar records remain readable inside Announcements while all
  // new dates are posted through the announcement form.
  const jjSubBaseRenderNews=renderNews;
  renderNews=async function(){
    await jjSubBaseRenderNews();
    const grid=$('#newsGrid');if(!grid)return;
    try{
      const schedules=await api('/schedules');
      const legacy=(Array.isArray(schedules)?schedules:[]).filter(x=>x?.date).map(x=>`<article class="news-card jj-sub-legacy-schedule"><span class="tag">ACTIVITY</span><div class="hint">${safe(x.date)}${x.time?` · ${safe(x.time)}`:''}</div><h3>${safe(x.title||'JJ活動')}</h3><p>${x.room?`場所: ${safe(x.room)}${x.note?' · ':''}`:''}${safe(x.note||'')}</p></article>`).join('');
      if(legacy)grid.insertAdjacentHTML('beforeend',legacy);
    }catch{}
  };
'''


def transform_app_js(source: str) -> str:
    if SUBTRACTIVE_RED282_MARKER in source:
        return source

    js = source.replace("お知らせを投稿", "お知らせ / 活動予定を投稿", 1)
    js = js.replace(
        '<label>本文<textarea name="body" rows="5" required></textarea></label>',
        '<label>本文（活動予定は時間・場所も記載）<textarea name="body" rows="5" required></textarea></label>',
        1,
    )

    anchor = "\n  init();"
    position = js.rfind(anchor)
    if position < 0:
        raise RuntimeError("subtractive redesign drift: init anchor not found")
    return js[:position] + "\n" + _APP_PATCH.rstrip() + js[position:]


_CSS_PATCH = r'''

/* jj subtractive redesign 2026-09-15 */
#scheduleView{display:none!important}
.nav[data-view="schedule"],.nav[data-view="discussion"]{display:none!important}
#tablesView .online-overview{display:none!important}
#pokerRoom .table-side{display:none!important}
#pokerRoom .poker-layout{grid-template-columns:minmax(0,1fr)!important}
#pokerRoom .poker-zone{width:100%!important;max-width:none!important}
#pokerRoom #jjV5HotkeyBadge{display:none!important}
#actionBar .jj-size-settings,
#actionBar [data-jj-sizing-settings]{display:none!important}
#actionBar .jj-sub-manual-stepper{display:flex;align-items:center;justify-content:center;gap:10px;flex-wrap:wrap}
#actionBar .jj-sub-manual-stepper label{display:flex;align-items:center;gap:6px}
#actionBar .jj-sub-manual-stepper input#raiseTo{min-width:110px;text-align:center;font-variant-numeric:tabular-nums}
#actionBar .jj-sub-bet-hint{flex-basis:100%;text-align:center;color:#9fb2aa;font-size:.64rem;line-height:1.35}
#tablesView .jj-sub-single-table{max-width:720px;margin-inline:auto}
@media(max-width:760px){
  #pokerRoom .poker-layout{display:block!important}
  #actionBar .jj-sub-manual-stepper input#raiseTo{min-width:96px;font-size:1rem}
  #actionBar .jj-sub-bet-hint{font-size:.6rem}
}
'''


def transform_styles(source: str) -> str:
    if SUBTRACTIVE_RED282_MARKER in source:
        return source
    return source.rstrip() + _CSS_PATCH + "\n"


__all__ = [
    "SUBTRACTIVE_RED282_MARKER",
    "transform_app_js",
    "transform_index",
    "transform_styles",
]
