from __future__ import annotations

"""Phase 4A player-experience fixes discovered by the 2026-09-12 follow-up audit.

This stage is intentionally presentation-only. It runs after phases 1-3 and
keeps the materialized v1.24.4 tree immutable.
"""

PHASE4_MARKER = "v2 player-ux phase4a usability 2026-09-12"


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"player UX phase4 drift at {label}: expected 1 source block, found {count}")
    return source.replace(old, new, 1)


def transform_app_js(source: str) -> str:
    if PHASE4_MARKER in source:
        return source

    # The sizing-settings control belongs in table chrome, not among live action
    # choices where opening it can consume a player's decision clock.
    source = _replace_once(
        source,
        '''      <div class="jj-size-row" aria-label="ベットサイズ候補">${quick}${allin}<button type="button" class="jj-size-btn jj-size-settings" data-jj-sizing-settings aria-label="サイズ候補を設定"><span>設定</span><small>⚙</small></button></div>\n''',
        '''      <div class="jj-size-row" aria-label="ベットサイズ候補">${quick}${allin}</div>\n''',
        "remove live-decision sizing settings button",
    )

    old_polish = '''  function jjV124PolishTableChrome(){
    if(!currentTableId||!tableState){document.body.classList.remove('jj-poker-focus','jj-poker-keyboard-open');return}
    const ready=$('#tableControls .jj-ready-count');
    if(ready&&/^次ハンド\\s/.test(ready.textContent||''))ready.textContent=(ready.textContent||'').replace(/^次ハンド\\s*/,'次ハンド参加予定 ');
    const sound=$('#jjSoundToggle'),head=$('#pokerRoom .room-head');
    if(JJ_V124_DESKTOP_MQ.matches&&sound&&head&&!head.contains(sound))head.appendChild(sound);
    if(head&&!$('#jjFocusModeToggle',head))head.insertAdjacentHTML('beforeend','<button type="button" class="ghost jj-focus-toggle" id="jjFocusModeToggle" aria-pressed="false">集中表示</button>');
    document.body.classList.toggle('jj-v124-desktop-poker',JJ_V124_DESKTOP_MQ.matches&&!!currentTableId);
    jjV3ApplyFocus();jjV3ViewportSync();
  }
'''
    new_polish = '''  function jjV124PolishTableChrome(){
    if(!currentTableId||!tableState){document.body.classList.remove('jj-poker-focus','jj-poker-keyboard-open','jj-v4-side-open');return}
    const ready=$('#tableControls .jj-ready-count');
    if(ready&&/^次ハンド\\s/.test(ready.textContent||''))ready.textContent=(ready.textContent||'').replace(/^次ハンド\\s*/,'次ハンド参加予定 ');
    const sound=$('#jjSoundToggle'),head=$('#pokerRoom .room-head');
    if(JJ_V124_DESKTOP_MQ.matches&&sound&&head&&!head.contains(sound))head.appendChild(sound);
    if(head&&!$('#jjPokerSettings',head))head.insertAdjacentHTML('beforeend','<button type="button" class="ghost jj-v4-settings" id="jjPokerSettings" data-jj-sizing-settings aria-label="ポーカー設定">⚙ 設定</button>');
    if(head&&!$('#jjFocusModeToggle',head))head.insertAdjacentHTML('beforeend','<button type="button" class="ghost jj-focus-toggle" id="jjFocusModeToggle" aria-pressed="false">集中表示</button>');
    document.body.classList.toggle('jj-v124-desktop-poker',JJ_V124_DESKTOP_MQ.matches&&!!currentTableId);
    jjV4EnsureMobileTools();jjV3ApplyFocus();jjV3ViewportSync();
  }
'''
    source = _replace_once(source, old_polish, new_polish, "safe poker settings placement")

    helper_anchor = "  document.addEventListener('click',async e=>{\n    const back=e.target.closest('#backLobby');\n"
    helpers = r'''  // v2 player-ux phase4a usability 2026-09-12
  function jjV4EnsureMobileTools(){
    const head=$('#pokerRoom .room-head'),side=$('#pokerRoom .table-side');
    if(head&&!$('#jjV4MobileTools',head))head.insertAdjacentHTML('beforeend','<div id="jjV4MobileTools" class="jj-v4-mobile-tools" aria-label="テーブル情報"><button type="button" class="ghost" data-jj-mobile-side="log">履歴</button><button type="button" class="ghost" data-jj-mobile-side="chat">チャット</button></div>');
    if(side&&!$('#jjV4SideClose',side))side.insertAdjacentHTML('afterbegin','<div class="jj-v4-side-head"><strong>テーブル情報</strong><button type="button" class="ghost" id="jjV4SideClose" aria-label="テーブル情報を閉じる">閉じる</button></div>');
  }
  function jjV4OpenSide(tab){
    jjV4EnsureMobileTools();
    document.body.classList.add('jj-v4-side-open');
    const target=$(`#pokerRoom [data-side-tab="${tab==='log'?'log':'chat'}"]`);
    target?.click();
  }
  function jjV4CloseSide(){document.body.classList.remove('jj-v4-side-open')}

'''
    if source.count(helper_anchor) != 1:
        raise RuntimeError("player UX phase4 drift at listener helper anchor")
    source = source.replace(helper_anchor, helpers + helper_anchor, 1)

    source = _replace_once(
        source,
        """    if(back){document.body.classList.remove('jj-poker-focus','jj-poker-keyboard-open');document.documentElement.style.setProperty('--jj-vv-bottom','0px')}\n    const settings=e.target.closest('[data-jj-sizing-settings]');\n    if(settings){e.preventDefault();e.stopImmediatePropagation();return jjV3OpenSizingSettings()}\n""",
        """    if(back){jjV4CloseSide();document.body.classList.remove('jj-poker-focus','jj-poker-keyboard-open');document.documentElement.style.setProperty('--jj-vv-bottom','0px')}\n    const mobileSide=e.target.closest('[data-jj-mobile-side]');\n    if(mobileSide){e.preventDefault();e.stopImmediatePropagation();return jjV4OpenSide(mobileSide.dataset.jjMobileSide)}\n    const sideClose=e.target.closest('#jjV4SideClose');\n    if(sideClose){e.preventDefault();e.stopImmediatePropagation();return jjV4CloseSide()}\n    const settings=e.target.closest('[data-jj-sizing-settings]');\n    if(settings){\n      e.preventDefault();e.stopImmediatePropagation();\n      if(tableState?.legal?.can_act)return toast('自分のアクション中は設定を変更できません');\n      return jjV3OpenSizingSettings();\n    }\n""",
        "action-clock-safe settings and mobile drawer listeners",
    )

    resize_anchor = "  window.addEventListener('resize',jjV3ViewportSync);\n"
    resize_replacement = "  window.addEventListener('resize',()=>{jjV3ViewportSync();if(window.innerWidth>1000)jjV4CloseSide()});\n"
    source = _replace_once(source, resize_anchor, resize_replacement, "mobile drawer resize cleanup")

    return source


PHASE4_CSS = r'''

/* v2 player-ux phase4a usability 2026-09-12 */
/* Phase 3 intentionally renders each preset's clamped legal total in <small>.
   An older v1.24 rule hid that element with !important; restore the contract. */
#actionBar .jj-v124-sizing .jj-size-btn small{display:block!important}
#pokerRoom .jj-v4-settings{white-space:nowrap}
#pokerRoom .jj-v4-mobile-tools,.jj-v4-side-head{display:none}

@media(max-width:1000px){
  #pokerRoom .jj-v4-mobile-tools{display:flex;gap:6px;margin-left:auto}
  #pokerRoom .jj-v4-mobile-tools button{min-height:36px;padding:0 9px;font-size:.68rem}
  body.jj-v4-side-open #pokerRoom .table-side{
    display:block!important;position:fixed!important;z-index:210!important;
    left:10px!important;right:10px!important;bottom:calc(10px + env(safe-area-inset-bottom))!important;
    width:auto!important;max-width:none!important;max-height:min(68dvh,620px)!important;
    overflow:auto!important;margin:0!important;padding:10px!important;border-radius:16px!important;
    box-shadow:0 24px 70px rgba(0,0,0,.52)!important;
  }
  body.jj-v4-side-open:after{content:'';position:fixed;z-index:205;inset:0;background:rgba(2,7,5,.58)}
  body.jj-v4-side-open #pokerRoom .table-side{isolation:isolate}
  #pokerRoom .jj-v4-side-head{display:flex;position:sticky;top:-10px;z-index:2;align-items:center;justify-content:space-between;gap:10px;margin:-10px -10px 8px;padding:9px 10px;background:rgba(15,24,21,.97);border-bottom:1px solid rgba(255,255,255,.08)}
  #pokerRoom .jj-v4-side-head strong{font-size:.78rem}
}

@media(max-width:760px){
  #pokerRoom .jj-seat-box .name{font-size:.68rem!important}
  #pokerRoom .jj-seat-box .stack{font-size:.76rem!important;font-weight:900!important}
  #pokerRoom .jj-player-state{font-size:.56rem!important}
  body.jj-mobile-table-open #actionBar .jj-v124-decision-meta span{font-size:.52rem!important}
  body.jj-mobile-table-open #actionBar .jj-v124-decision-meta strong{font-size:.72rem!important}
  body.jj-mobile-table-open #actionBar .jj-v124-sizing .jj-size-btn{height:44px!important;min-height:44px!important}
  body.jj-mobile-table-open #actionBar .jj-v124-sizing .jj-size-btn small{display:block!important;font-size:.5rem!important;opacity:.82!important}
  #pokerRoom .jj-v4-settings{font-size:.66rem!important;min-height:36px!important;padding-inline:8px!important}
}
'''


def transform_styles(source: str) -> str:
    if PHASE4_MARKER in source:
        return source
    return source.rstrip() + PHASE4_CSS + "\n"


__all__ = ["PHASE4_MARKER", "transform_app_js", "transform_styles"]
