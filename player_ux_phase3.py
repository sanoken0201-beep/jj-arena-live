from __future__ import annotations

"""Stage 3 of the 2026-09-12 player UX audit.

Applied after Phase 1 and Phase 2 so the committed materialized runtime remains
immutable. This stage only changes presentation/preferences/review navigation;
it does not change betting legality, settlement, or ranking rules.
"""

PHASE3_MARKER = "v2 player-ux phase3 focus-sizing 2026-09-12"


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"player UX phase3 drift at {label}: expected 1 source block, found {count}")
    return source.replace(old, new, 1)


def transform_app_js(source: str) -> str:
    if PHASE3_MARKER in source:
        return source

    helpers = r'''
  // v2 player-ux phase3 focus-sizing 2026-09-12
  const JJ_V3_SIZING_DEFAULTS={pre:[2.5,3,4],post:[33,50,75,100]};
  function jjV3UserKey(suffix){return `jj-poker-${suffix}-v1:${me?.id||me?.name||'device'}`}
  function jjV3ValidList(raw,count,min,max){
    if(!Array.isArray(raw)||raw.length!==count)return null;
    const out=raw.map(Number);
    return out.every(v=>Number.isFinite(v)&&v>=min&&v<=max)?out:null;
  }
  function jjV3SizingPrefs(){
    try{
      const saved=JSON.parse(localStorage.getItem(jjV3UserKey('sizing'))||'null')||{};
      return {
        pre:jjV3ValidList(saved.pre,3,1.5,10)||[...JJ_V3_SIZING_DEFAULTS.pre],
        post:jjV3ValidList(saved.post,4,10,300)||[...JJ_V3_SIZING_DEFAULTS.post],
      };
    }catch{return {pre:[...JJ_V3_SIZING_DEFAULTS.pre],post:[...JJ_V3_SIZING_DEFAULTS.post]}}
  }
  function jjV3SizingDefs(pre){
    const prefs=jjV3SizingPrefs(),values=pre?prefs.pre:prefs.post;
    return values.map(value=>[pre?`${jjV124FmtNumber(value,2)}x`:Number(value)===100?'POT':`${jjV124FmtNumber(value,1)}%`,Number(value)]);
  }
  function jjV3FocusEnabled(){try{return localStorage.getItem(jjV3UserKey('focus'))==='1'}catch{return false}}
  function jjV3ApplyFocus(){
    const enabled=!!currentTableId&&jjV3FocusEnabled();
    document.body.classList.toggle('jj-poker-focus',enabled);
    const btn=$('#jjFocusModeToggle');
    if(btn){btn.textContent=enabled?'通常表示':'集中表示';btn.setAttribute('aria-pressed',enabled?'true':'false')}
  }
  function jjV3OpenSizingSettings(){
    const prefs=jjV3SizingPrefs();
    openModal(`<div class="jj-v3-sizing-settings"><div class="eyebrow">BET SIZING</div><h3>サイズ候補の設定</h3><p class="hint">この端末に保存します。候補を変更してもアクションは送信されません。卓では合法範囲に丸めた実際の合計BBを併記します。</p><form id="jjV3SizingForm" class="stack"><fieldset><legend>プリフロップ · 倍率</legend><div class="jj-v3-setting-grid">${prefs.pre.map((v,i)=>`<label>候補 ${i+1}<input name="pre${i}" type="number" inputmode="decimal" min="1.5" max="10" step="0.1" value="${safe(String(v))}" required></label>`).join('')}</div></fieldset><fieldset><legend>ポストフロップ · ポット%</legend><div class="jj-v3-setting-grid">${prefs.post.map((v,i)=>`<label>候補 ${i+1}<input name="post${i}" type="number" inputmode="decimal" min="10" max="300" step="1" value="${safe(String(v))}" required></label>`).join('')}</div></fieldset><div class="jj-v3-setting-actions"><button class="primary" type="submit">保存</button><button class="soft" type="button" data-jj-sizing-reset>初期値に戻す</button></div></form></div>`);
  }
  function jjV3SaveSizing(form){
    const fd=new FormData(form),pre=[0,1,2].map(i=>Number(fd.get(`pre${i}`))),post=[0,1,2,3].map(i=>Number(fd.get(`post${i}`)));
    if(!jjV3ValidList(pre,3,1.5,10)||!jjV3ValidList(post,4,10,300))throw new Error('入力範囲を確認してください');
    localStorage.setItem(jjV3UserKey('sizing'),JSON.stringify({pre,post}));
  }
  async function jjV3BookmarkHand(handId){
    if(!handId)return;
    const data=await api(`/analysis/hands/${encodeURIComponent(handId)}`),review=data.review||{};
    await api(`/analysis/hands/${encodeURIComponent(handId)}/review`,{method:'PUT',body:JSON.stringify({bookmarked:true,note:String(review.note||''),tags:Array.isArray(review.tags)?review.tags:[]})});
    toast('あとで復習するハンドに保存しました');
  }
  function jjV3ViewportSync(){
    const vv=window.visualViewport;
    if(!vv){document.documentElement.style.setProperty('--jj-vv-bottom','0px');document.body.classList.remove('jj-poker-keyboard-open');return}
    const hidden=Math.max(0,window.innerHeight-vv.height-vv.offsetTop),keyboard=hidden>120&&!!currentTableId;
    document.documentElement.style.setProperty('--jj-vv-bottom',`${Math.round(hidden)}px`);
    document.body.classList.toggle('jj-poker-keyboard-open',keyboard);
  }
'''
    anchor = "  function jjV124SizingMarkup(hero,l){\n"
    if source.count(anchor) != 1:
        raise RuntimeError("player UX phase3 drift at sizing helper anchor")
    source = source.replace(anchor, helpers + "\n" + anchor, 1)

    source = _replace_once(
        source,
        """    const pre=tableState?.hand?.phase==='preflop';
    const defs=pre?[['2.5x',2.5],['3x',3],['4x',4]]:[['33%',33],['50%',50],['75%',75],['POT',100]];
    const quick=defs.map(([label,value])=>{
      const target=jjV124PresetTarget(pre?'pre':'post',value,hero,l);
      return `<button type="button" class="jj-size-btn" ${pre?`data-raise-bb="${target}" data-multiplier="${value}"`:`data-pot-pct="${value}"`} aria-label="${safe(label)} サイズ">${safe(label)}</button>`;
    }).join('');
    const allin=l.can_all_in?'<button type="button" class="jj-size-btn jj-allin-size" data-allin-size aria-label="オールイン額を選択">ALL-IN</button>':'';
""",
        """    const pre=tableState?.hand?.phase==='preflop';
    const defs=jjV3SizingDefs(pre),targets=defs.map(([,value])=>jjV124PresetTarget(pre?'pre':'post',value,hero,l));
    const targetCounts=targets.reduce((m,v)=>(m.set(String(Number(v).toFixed(3)),(m.get(String(Number(v).toFixed(3)))||0)+1),m),new Map());
    const quick=defs.map(([label,value],i)=>{
      const target=targets[i],same=targetCounts.get(String(Number(target).toFixed(3)))>1;
      return `<button type="button" class="jj-size-btn ${same?'is-duplicate-target':''}" ${pre?`data-raise-bb="${target}" data-multiplier="${value}"`:`data-pot-pct="${value}"`} aria-label="${safe(label)} サイズ・合計 ${safe(jjV185FmtBb(target))}"><span>${safe(label)}</span><small>${safe(jjV185FmtBb(target))}${same?' · 同額':''}</small></button>`;
    }).join('');
    const allin=l.can_all_in?`<button type="button" class="jj-size-btn jj-allin-size" data-allin-size aria-label="オールイン額を選択"><span>ALL-IN</span><small>${safe(jjV185FmtBb(max))}</small></button>`:'';
""",
        "configurable sizing presets",
    )

    source = _replace_once(
        source,
        """      <div class="jj-size-row" aria-label="ベットサイズ候補">${quick}${allin}</div>
""",
        """      <div class="jj-size-row" aria-label="ベットサイズ候補">${quick}${allin}<button type="button" class="jj-size-btn jj-size-settings" data-jj-sizing-settings aria-label="サイズ候補を設定"><span>設定</span><small>⚙</small></button></div>
""",
        "sizing settings entry",
    )

    source = _replace_once(
        source,
        """  function jjV124PolishTableChrome(){
    if(!currentTableId||!tableState)return;
    const ready=$('#tableControls .jj-ready-count');
    if(ready&&/^次ハンド\\s/.test(ready.textContent||''))ready.textContent=(ready.textContent||'').replace(/^次ハンド\\s*/,'次ハンド参加予定 ');
    const sound=$('#jjSoundToggle');
    const head=$('#pokerRoom .room-head');
    if(JJ_V124_DESKTOP_MQ.matches&&sound&&head&&!head.contains(sound))head.appendChild(sound);
    document.body.classList.toggle('jj-v124-desktop-poker',JJ_V124_DESKTOP_MQ.matches&&!!currentTableId);
  }
""",
        """  function jjV124PolishTableChrome(){
    if(!currentTableId||!tableState){document.body.classList.remove('jj-poker-focus','jj-poker-keyboard-open');return}
    const ready=$('#tableControls .jj-ready-count');
    if(ready&&/^次ハンド\\s/.test(ready.textContent||''))ready.textContent=(ready.textContent||'').replace(/^次ハンド\\s*/,'次ハンド参加予定 ');
    const sound=$('#jjSoundToggle'),head=$('#pokerRoom .room-head');
    if(JJ_V124_DESKTOP_MQ.matches&&sound&&head&&!head.contains(sound))head.appendChild(sound);
    if(head&&!$('#jjFocusModeToggle',head))head.insertAdjacentHTML('beforeend','<button type="button" class="ghost jj-focus-toggle" id="jjFocusModeToggle" aria-pressed="false">集中表示</button>');
    document.body.classList.toggle('jj-v124-desktop-poker',JJ_V124_DESKTOP_MQ.matches&&!!currentTableId);
    jjV3ApplyFocus();jjV3ViewportSync();
  }
""",
        "focus-mode chrome",
    )

    source = _replace_once(
        source,
        """${handId?`<button class="soft" data-jj-review-hand="${safe(handId)}">直前のハンドを見る</button>`:''}<small class="jj-settlement-note">""",
        """${handId?`<div class="jj-settlement-actions"><button class="soft" data-jj-review-hand="${safe(handId)}">直前のハンドを見る</button><button class="ghost" data-jj-bookmark-hand="${safe(handId)}">あとで復習</button></div>`:''}<small class="jj-settlement-note">""",
        "review and bookmark actions",
    )

    listeners = r'''
  document.addEventListener('click',async e=>{
    const back=e.target.closest('#backLobby');
    if(back){document.body.classList.remove('jj-poker-focus','jj-poker-keyboard-open');document.documentElement.style.setProperty('--jj-vv-bottom','0px')}
    const settings=e.target.closest('[data-jj-sizing-settings]');
    if(settings){e.preventDefault();e.stopImmediatePropagation();return jjV3OpenSizingSettings()}
    const reset=e.target.closest('[data-jj-sizing-reset]');
    if(reset){e.preventDefault();localStorage.removeItem(jjV3UserKey('sizing'));closeModal();if(currentTableId&&tableState)renderPokerRoom();toast('サイズ候補を初期値に戻しました');return}
    const focus=e.target.closest('#jjFocusModeToggle');
    if(focus){e.preventDefault();e.stopImmediatePropagation();try{localStorage.setItem(jjV3UserKey('focus'),jjV3FocusEnabled()?'0':'1')}catch{}jjV3ApplyFocus();return}
    const bookmark=e.target.closest('[data-jj-bookmark-hand]');
    if(bookmark){e.preventDefault();e.stopImmediatePropagation();bookmark.disabled=true;try{await jjV3BookmarkHand(bookmark.dataset.jjBookmarkHand);bookmark.textContent='保存済み'}catch(err){bookmark.disabled=false;toast(err.message)}return}
  },true);
  document.addEventListener('submit',e=>{
    if(e.target?.id!=='jjV3SizingForm')return;
    e.preventDefault();e.stopImmediatePropagation();
    try{jjV3SaveSizing(e.target);closeModal();if(currentTableId&&tableState)renderPokerRoom();toast('サイズ候補を保存しました')}catch(err){toast(err.message)}
  },true);
  document.addEventListener('focusin',e=>{if(e.target?.id==='raiseTo')setTimeout(()=>{jjV3ViewportSync();try{e.target.scrollIntoView({block:'nearest',inline:'nearest'})}catch{}},40)},true);
  window.visualViewport?.addEventListener('resize',jjV3ViewportSync);
  window.visualViewport?.addEventListener('scroll',jjV3ViewportSync);
  window.addEventListener('resize',jjV3ViewportSync);

'''
    listener_anchor = "  // Desktop bet markers use explicit poker-table lanes rather than the old\n"
    if source.count(listener_anchor) != 1:
        raise RuntimeError("player UX phase3 drift at listener anchor")
    source = source.replace(listener_anchor, listeners + listener_anchor, 1)

    return source


PHASE3_CSS = r'''

/* v2 player-ux phase3 focus-sizing 2026-09-12 */
#pokerRoom .jj-size-btn{height:auto;min-height:38px;display:inline-flex;flex-direction:column;align-items:center;justify-content:center;line-height:1.05;gap:2px}
#pokerRoom .jj-size-btn span{font-size:.68rem;font-weight:900}#pokerRoom .jj-size-btn small{font-size:.56rem;color:#9fb2aa;font-weight:750;white-space:nowrap}
#pokerRoom .jj-size-btn.is-duplicate-target{border-style:dashed}#pokerRoom .jj-size-btn.is-duplicate-target small{color:#f3d981}.jj-size-settings{opacity:.78}
.jj-v3-sizing-settings fieldset{border:1px solid var(--line);border-radius:14px;padding:13px}.jj-v3-sizing-settings legend{padding:0 7px;font-size:.75rem;font-weight:850;color:var(--green)}
.jj-v3-setting-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}.jj-v3-setting-actions{display:flex;gap:8px;flex-wrap:wrap}
.jj-focus-toggle{margin-left:auto;white-space:nowrap}.jj-settlement-actions{display:flex;justify-content:center;gap:7px;flex-wrap:wrap;margin-top:6px}
#pokerRoom .result-banner{flex-direction:column;align-items:stretch;justify-content:flex-start;max-width:min(90%,640px)}
@media(min-width:761px){
  body.jj-poker-focus .sidebar{display:none!important}body.jj-poker-focus .main{margin-left:0!important;max-width:none!important;padding:0 18px 28px!important}body.jj-poker-focus .topbar{display:none!important}
  body.jj-poker-focus #tablesView{padding-top:10px}body.jj-poker-focus #pokerRoom{--jj-side-w:250px;width:100%!important;max-width:none!important}body.jj-poker-focus #pokerRoom .room-head{position:sticky;top:0;z-index:35;padding:8px 0;background:rgba(244,242,236,.94);backdrop-filter:blur(10px)}
  body.jj-poker-focus #pokerTable{--jj-stage-h:min(76vh,680px)}body.jj-poker-focus #pokerRoom .table-side{opacity:.88}
}
@media(max-width:760px){
  .jj-v3-setting-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.jj-focus-toggle{margin-left:0}#pokerRoom .jj-size-settings{display:inline-flex!important;min-width:0!important}
  body.jj-poker-keyboard-open.jj-mobile-table-open.jj-mobile-poker-can-act #actionBar{bottom:var(--jj-vv-bottom,0px)!important;max-height:none!important;overflow:visible!important}
  body.jj-poker-keyboard-open.jj-mobile-table-open #pokerTable{height:min(43dvh,360px)!important}
  body.jj-poker-keyboard-open .toast{bottom:calc(var(--jj-vv-bottom,0px) + 12px)!important}
}
'''


def transform_styles(source: str) -> str:
    if PHASE3_MARKER in source:
        return source
    return source.rstrip() + PHASE3_CSS + "\n"
