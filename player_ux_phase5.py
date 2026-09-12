from __future__ import annotations

"""Phase 4B safe-action ergonomics for JJ Arena online poker.

This stage is intentionally client-side UX only. It does not add call-any,
auto-call, auto-raise, or any rule/settlement change. Pre-actions can only
resolve to CHECK or FOLD, and keyboard shortcuts never commit chips by
themselves.
"""

PHASE5_MARKER = "v2 player-ux phase4b safe-actions 2026-09-12"


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"player UX phase5 drift at {label}: expected 1 source block, found {count}")
    return source.replace(old, new, 1)


def transform_app_js(source: str) -> str:
    if PHASE5_MARKER in source:
        return source

    helper_anchor = "  renderActionBar=function(){\n    const bar=$('#actionBar');if(!bar)return;\n"
    helpers = r'''  // v2 player-ux phase4b safe-actions 2026-09-12
  let jjV5PreAction={key:'',mode:'',running:false};
  let jjV5SettlementKey='',jjV5SettlementTimer=null,jjV5SettlementExpanded=false;

  function jjV5HandKey(){
    const hand=tableState?.hand||{};
    return `${currentTableId||''}:${hand.id||''}:${me?.id||''}`;
  }
  function jjV5ClearPreAction(message=''){
    jjV5PreAction={key:'',mode:'',running:false};
    if(message)toast(message);
  }
  function jjV5WaitingEligible(hero){
    return !!currentTableId&&tableState?.status==='playing'&&!!hero&&Number(hero.stack||0)>0&&!hero.folded&&!hero.all_in&&!hero.sitting_out&&!tableState?.legal?.can_act;
  }
  function jjV5PreActionMarkup(hero){
    if(!jjV5WaitingEligible(hero)){if(jjV5PreAction.mode&&jjV5PreAction.key!==jjV5HandKey())jjV5ClearPreAction();return ''}
    if(jjV5PreAction.mode&&jjV5PreAction.key!==jjV5HandKey())jjV5ClearPreAction();
    const mode=jjV5PreAction.mode;
    return `<div class="jj-v5-preactions" aria-label="安全な先行アクション"><span>先行操作</span><button type="button" class="ghost ${mode==='check'?'is-selected':''}" data-jj-preaction="check" aria-pressed="${mode==='check'?'true':'false'}">チェックのみ</button><button type="button" class="ghost ${mode==='check_fold'?'is-selected':''}" data-jj-preaction="check_fold" aria-pressed="${mode==='check_fold'?'true':'false'}">チェック / フォールド</button><small>コール・ベット・レイズは自動実行しません</small></div>`;
  }
  function jjV5SetPreAction(mode){
    if(!['check','check_fold'].includes(mode))return;
    const hero=typeof jjV124Hero==='function'?jjV124Hero():null;
    if(!jjV5WaitingEligible(hero))return toast('先行操作は他プレイヤーのアクション待ち中だけ設定できます');
    if(jjV5PreAction.mode===mode&&jjV5PreAction.key===jjV5HandKey())jjV5ClearPreAction();
    else jjV5PreAction={key:jjV5HandKey(),mode,running:false};
    renderActionBar();
  }
  function jjV5MaybeRunPreAction(){
    if(!jjV5PreAction.mode||jjV5PreAction.running||!tableState?.legal?.can_act)return;
    if(jjV5PreAction.key!==jjV5HandKey()){jjV5ClearPreAction();return}
    if(document.visibilityState!=='visible'){jjV5ClearPreAction('画面が非表示だったため先行操作を解除しました');return}
    if(typeof jjV2Connection!=='undefined'&&!jjV2Connection.fresh){jjV5ClearPreAction('卓状態を同期中のため先行操作を解除しました');return}
    const mode=jjV5PreAction.mode,l=tableState.legal||{};
    let selector='';
    if(mode==='check'){
      if(!l.can_check){jjV5ClearPreAction('チェックできない状況になったため予約を解除しました');return}
      selector='#actionBar [data-action="check"]';
    }else{
      selector=l.can_check?'#actionBar [data-action="check"]':'#actionBar [data-action="fold"]';
    }
    const key=jjV124DecisionKey(),button=$(selector);
    if(!button||button.disabled){jjV5ClearPreAction();return}
    jjV5PreAction.running=true;
    const reserved={key:jjV5PreAction.key,mode:jjV5PreAction.mode};
    jjV5PreAction={key:'',mode:'',running:true};
    queueMicrotask(()=>{
      jjV5PreAction.running=false;
      if(!currentTableId||!tableState?.legal?.can_act||jjV124DecisionKey()!==key)return;
      if(reserved.key!==jjV5HandKey())return;
      const live=$(selector);if(live&&!live.disabled)live.click();
    });
  }

  function jjV5HotkeysEnabled(){try{return localStorage.getItem(jjV3UserKey('hotkeys'))==='1'}catch{return false}}
  function jjV5SetHotkeys(enabled){
    try{localStorage.setItem(jjV3UserKey('hotkeys'),enabled?'1':'0')}catch{}
    jjV5SyncHotkeyBadge();
  }
  function jjV5SyncHotkeyBadge(){
    const head=$('#pokerRoom .room-head');if(!head)return;
    let badge=$('#jjV5HotkeyBadge',head);
    if(jjV5HotkeysEnabled()){
      if(!badge)head.insertAdjacentHTML('beforeend','<span id="jjV5HotkeyBadge" class="jj-v5-hotkey-badge">KEY MODE</span>');
    }else badge?.remove();
  }
  function jjV5EnhanceSettingsModal(){
    const form=$('#jjV3SizingForm');if(!form||$('#jjV5HotkeySettings',form))return;
    form.insertAdjacentHTML('beforeend',`<fieldset id="jjV5HotkeySettings"><legend>安全なキーボード操作</legend><label class="jj-v5-hotkey-toggle"><input id="jjV5HotkeysEnabled" type="checkbox" ${jjV5HotkeysEnabled()?'checked':''}> キーボード補助を有効にする</label><div class="hint">初期設定はOFF。ブラウザ標準のCtrl+F / Ctrl+R / Ctrl+Kは使用しません。Ctrl+Shift+1＝フォールドへ移動、2＝チェックへ移動、3＝レイズ額欄、4〜7＝サイズ候補。フォールド・チェックはショートカットだけでは確定しません。</div></fieldset>`);
  }
  function jjV5TypingTarget(target){
    const el=target instanceof Element?target:document.activeElement;
    return !!el&&(el.matches?.('input,textarea,select,[contenteditable="true"]')||!!el.closest?.('[contenteditable="true"]'));
  }
  function jjV5HandleHotkey(e){
    if(!jjV5HotkeysEnabled()||!currentTableId||document.visibilityState!=='visible')return;
    if(!e.ctrlKey||!e.shiftKey||e.altKey||e.metaKey||e.repeat||jjV5TypingTarget(e.target)||$('#modal')?.open)return;
    if(typeof jjV2Connection!=='undefined'&&!jjV2Connection.fresh)return;
    let target=null,mode='';
    if(e.code==='Digit1'){target=$('#actionBar [data-action="fold"]');mode='focus-action'}
    else if(e.code==='Digit2'){target=$('#actionBar [data-action="check"]');mode='focus-action'}
    else if(e.code==='Digit3'){target=$('#raiseTo');mode='focus-input'}
    else if(/^Digit[4-7]$/.test(e.code)){target=$$('#actionBar .jj-size-btn:not(.jj-allin-size):not(.jj-size-settings)')[Number(e.code.slice(-1))-4];mode='size'}
    if(!target||target.disabled)return;
    e.preventDefault();e.stopPropagation();
    if(mode==='focus-action'){
      target.focus({preventScroll:false});
      target.classList.add('jj-v5-key-target');
      setTimeout(()=>target.classList.remove('jj-v5-key-target'),900);
      return;
    }
    if(mode==='focus-input'){target.focus({preventScroll:false});target.select?.();return}
    if(mode==='size')target.click();
  }

  function jjV5ResultKey(){
    const result=tableState?.last_result;
    return result?`${currentTableId||''}:${tableState?.hand?.id||''}:${String(result.message||'')}`:'';
  }
  function jjV5SetSettlementCompact(compact){
    const banner=$('#resultBanner');if(!banner)return;
    banner.classList.toggle('jj-v5-result-compact',!!compact);
    const toggle=$('[data-jj-result-toggle]',banner);
    if(toggle)toggle.textContent=compact?'結果を表示':'縮小';
  }
  function jjV5SyncSettlement(){
    const banner=$('#resultBanner'),result=tableState?.last_result;
    if(!banner||!result||banner.classList.contains('hidden')){
      if(jjV5SettlementTimer)clearTimeout(jjV5SettlementTimer);
      jjV5SettlementTimer=null;jjV5SettlementKey='';jjV5SettlementExpanded=false;return;
    }
    const key=jjV5ResultKey();
    if(key!==jjV5SettlementKey){
      if(jjV5SettlementTimer)clearTimeout(jjV5SettlementTimer);
      jjV5SettlementKey=key;jjV5SettlementExpanded=false;jjV5SetSettlementCompact(false);
      jjV5SettlementTimer=setTimeout(()=>{if(jjV5ResultKey()===key&&!jjV5SettlementExpanded)jjV5SetSettlementCompact(true)},7000);
    }
    const head=$('.jj-settlement-head',banner);
    if(head&&!$('[data-jj-result-toggle]',head))head.insertAdjacentHTML('beforeend','<button type="button" class="ghost jj-v5-result-toggle" data-jj-result-toggle>縮小</button>');
    if(tableState?.legal?.can_act&&!jjV5SettlementExpanded)jjV5SetSettlementCompact(true);
    else jjV5SetSettlementCompact(banner.classList.contains('jj-v5-result-compact'));
  }

'''
    if source.count(helper_anchor) != 1:
        raise RuntimeError("player UX phase5 drift at action renderer helper anchor")
    source = source.replace(helper_anchor, helpers + helper_anchor, 1)

    source = _replace_once(
        source,
        """    if(!l.can_act){
      const stateText=hero.sitting_out?'一時離席中':tableState?.status==='playing'?'他のプレイヤーのアクション待ち':'次のハンドを待機';
      bar.innerHTML=`<div class="jj-v124-waiting"><span>${safe(stateText)}</span><strong>${safe(jjV124RawBb(hero.stack,{maxDecimals:1}))}</strong></div>`;
      return;
    }
""",
        """    if(!l.can_act){
      const stateText=hero.sitting_out?'一時離席中':tableState?.status==='playing'?'他のプレイヤーのアクション待ち':'次のハンドを待機';
      bar.innerHTML=`<div class="jj-v124-waiting"><span>${safe(stateText)}</span><strong>${safe(jjV124RawBb(hero.stack,{maxDecimals:1}))}</strong></div>${jjV5PreActionMarkup(hero)}`;
      return;
    }
""",
        "safe waiting pre-actions",
    )

    source = _replace_once(
        source,
        """    if(typeof jjV123ClockFeedback==='function')jjV123ClockFeedback();
    if(focusDraft&&focusDraft.key===jjV124DecisionKey())requestAnimationFrame(()=>{
""",
        """    if(typeof jjV123ClockFeedback==='function')jjV123ClockFeedback();
    jjV5MaybeRunPreAction();
    if(focusDraft&&focusDraft.key===jjV124DecisionKey())requestAnimationFrame(()=>{
""",
        "execute pre-action only after authoritative legal actions render",
    )

    source = _replace_once(
        source,
        "renderTableControls();renderActionBar();renderTableChat();renderHandLog();",
        "renderTableControls();renderActionBar();renderTableChat();renderHandLog();jjV5SyncSettlement();jjV5SyncHotkeyBadge();",
        "settlement and hotkey sync",
    )

    source = _replace_once(
        source,
        """      return jjV3OpenSizingSettings();
""",
        """      const result=jjV3OpenSizingSettings();jjV5EnhanceSettingsModal();return result;
""",
        "settings hotkey section",
    )

    listener_anchor = "  // Desktop bet markers use explicit poker-table lanes rather than the old\n"
    listeners = r'''  document.addEventListener('click',e=>{
    const pre=e.target.closest('[data-jj-preaction]');
    if(pre){e.preventDefault();e.stopImmediatePropagation();return jjV5SetPreAction(pre.dataset.jjPreaction)}
    const toggle=e.target.closest('[data-jj-result-toggle]');
    if(toggle){
      e.preventDefault();e.stopImmediatePropagation();
      const banner=$('#resultBanner'),compact=!banner?.classList.contains('jj-v5-result-compact');
      jjV5SettlementExpanded=!compact;jjV5SetSettlementCompact(compact);return;
    }
    if(e.target.closest('#backLobby'))jjV5ClearPreAction();
    if(e.target.closest('#actionBar [data-action]'))jjV5ClearPreAction();
  },true);
  document.addEventListener('change',e=>{
    if(e.target?.id==='jjV5HotkeysEnabled')jjV5SetHotkeys(!!e.target.checked);
  },true);
  document.addEventListener('keydown',jjV5HandleHotkey,true);

'''
    if source.count(listener_anchor) != 1:
        raise RuntimeError("player UX phase5 drift at listener anchor")
    source = source.replace(listener_anchor, listeners + listener_anchor, 1)

    return source


PHASE5_CSS = r'''

/* v2 player-ux phase4b safe-actions 2026-09-12 */
#actionBar .jj-v5-preactions{display:flex;align-items:center;justify-content:center;gap:7px;flex-wrap:wrap;padding:8px 10px;border-top:1px solid rgba(255,255,255,.07)}
#actionBar .jj-v5-preactions>span{font-size:.63rem;font-weight:900;letter-spacing:.08em;color:#9fb2aa}
#actionBar .jj-v5-preactions button{min-height:36px;padding:0 11px;font-size:.72rem}
#actionBar .jj-v5-preactions button.is-selected{border-color:#7de3b5;background:rgba(66,190,137,.18);box-shadow:0 0 0 1px rgba(125,227,181,.22) inset}
#actionBar .jj-v5-preactions small{flex-basis:100%;text-align:center;font-size:.57rem;color:#9fb2aa}
.jj-v5-hotkey-toggle{display:flex!important;align-items:center;gap:9px;font-weight:800}.jj-v5-hotkey-toggle input{width:auto!important;min-width:18px;min-height:18px}
#jjV5HotkeySettings{margin-top:4px}.jj-v5-hotkey-badge{font-size:.58rem;font-weight:900;letter-spacing:.08em;color:#a8ebcb;border:1px solid rgba(168,235,203,.28);border-radius:999px;padding:5px 7px;white-space:nowrap}
#actionBar .jj-v5-key-target{outline:2px solid #a8ebcb!important;outline-offset:2px}
#resultBanner .jj-v5-result-toggle{margin-left:auto;min-height:30px;padding:0 9px;font-size:.65rem}
#resultBanner.jj-v5-result-compact{max-width:min(88%,430px);padding-block:8px!important}
#resultBanner.jj-v5-result-compact .jj-settlement-grid span:nth-child(1),#resultBanner.jj-v5-result-compact .jj-settlement-grid span:nth-child(2),#resultBanner.jj-v5-result-compact .jj-settlement-actions,#resultBanner.jj-v5-result-compact .jj-settlement-note{display:none!important}
#resultBanner.jj-v5-result-compact .jj-settlement-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}
@media(max-width:760px){
  #actionBar .jj-v5-preactions{gap:5px;padding:6px 7px}#actionBar .jj-v5-preactions button{min-height:34px;font-size:.66rem;padding:0 8px}
  #actionBar .jj-v5-preactions small{font-size:.52rem}
  #resultBanner.jj-v5-result-compact{left:8px!important;right:8px!important;max-width:none!important;width:auto!important}
  #resultBanner .jj-v5-result-toggle{min-height:28px;font-size:.6rem}
}
'''


def transform_styles(source: str) -> str:
    if PHASE5_MARKER in source:
        return source
    return source.rstrip() + PHASE5_CSS + "\n"


__all__ = ["PHASE5_MARKER", "transform_app_js", "transform_styles"]
