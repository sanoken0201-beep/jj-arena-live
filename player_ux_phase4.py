from __future__ import annotations

"""Stage 4A of the 2026-09-12 player UX audit.

This stage is deliberately presentation-only. It fixes a Phase 3 visibility
regression, moves sizing preferences away from the live action controls, and
restores chat/hand-history access on compact layouts without changing poker
legality, settlement, ranking, or card-privacy behavior.
"""

PHASE4_MARKER = "v2 player-ux phase4a readability 2026-09-12"


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"player UX phase4 drift at {label}: expected 1 source block, found {count}")
    return source.replace(old, new, 1)


def transform_app_js(source: str) -> str:
    if PHASE4_MARKER in source:
        return source

    source = _replace_once(
        source,
        """      <div class=\"jj-size-row\" aria-label=\"ベットサイズ候補\">${quick}${allin}<button type=\"button\" class=\"jj-size-btn jj-size-settings\" data-jj-sizing-settings aria-label=\"サイズ候補を設定\"><span>設定</span><small>⚙</small></button></div>
""",
        """      <div class=\"jj-size-row\" aria-label=\"ベットサイズ候補\">${quick}${allin}</div>
""",
        "remove sizing settings from live action row",
    )

    source = _replace_once(
        source,
        """    jjV3ApplyFocus();jjV3ViewportSync();
""",
        """    jjV3ApplyFocus();jjV3ViewportSync();jjV4SyncTableTools();
""",
        "sync safe table tools after render",
    )

    phase4_helpers = r'''
  // v2 player-ux phase4a readability 2026-09-12
  function jjV4CompactTable(){
    try{return window.matchMedia?window.matchMedia('(max-width:1000px)').matches:window.innerWidth<=1000}catch{return window.innerWidth<=1000}
  }
  function jjV4CloseSideDrawer(){
    document.body.classList.remove('jj-poker-side-open');
    const toggle=$('#jjSideDrawerToggle');
    if(toggle)toggle.setAttribute('aria-expanded','false');
  }
  function jjV4OpenSideDrawer(){
    if(!currentTableId||!jjV4CompactTable())return;
    document.body.classList.add('jj-poker-side-open');
    const toggle=$('#jjSideDrawerToggle');
    if(toggle)toggle.setAttribute('aria-expanded','true');
  }
  function jjV4SyncTableTools(){
    if(!currentTableId){jjV4CloseSideDrawer();return}
    const head=$('#pokerRoom .room-head'),side=$('#pokerRoom .table-side');
    if(!head||!side)return;
    let tools=$('#jjV4TableTools',head);
    if(!tools){
      head.insertAdjacentHTML('beforeend',`<div id="jjV4TableTools" class="jj-v4-table-tools"><button type="button" class="ghost jj-v4-tool" id="jjSizingSettingsOpen" data-jj-sizing-settings aria-label="ベットサイズ候補を設定"><span class="jj-v4-tool-long">サイズ設定</span><span class="jj-v4-tool-short">⚙</span></button><button type="button" class="ghost jj-v4-tool" id="jjSideDrawerToggle" aria-expanded="false" aria-controls="tableSidePanel"><span class="jj-v4-tool-long">履歴・チャット</span><span class="jj-v4-tool-short">履歴</span></button></div>`);
      tools=$('#jjV4TableTools',head);
    }
    const settings=$('#jjSizingSettingsOpen',tools),busy=!!tableState?.legal?.can_act;
    if(settings){
      settings.disabled=busy;
      settings.setAttribute('aria-disabled',busy?'true':'false');
      settings.title=busy?'自分のアクション中はサイズ設定を変更できません':'プリフロップ／ポストフロップのサイズ候補を変更';
    }
    const drawer=$('#jjSideDrawerToggle',tools);
    if(drawer)drawer.hidden=!jjV4CompactTable();
    if(!side.id)side.id='tableSidePanel';
    if(!$('#jjSideDrawerClose',side)){
      side.insertAdjacentHTML('afterbegin','<div class="jj-v4-side-head"><strong>テーブル情報</strong><button type="button" class="ghost" id="jjSideDrawerClose">閉じる</button></div>');
    }
    if(!$('#jjSideDrawerBackdrop')){
      side.insertAdjacentHTML('afterend','<button type="button" id="jjSideDrawerBackdrop" aria-label="履歴・チャットを閉じる"></button>');
    }
    if(!jjV4CompactTable())jjV4CloseSideDrawer();
  }
  document.addEventListener('click',e=>{
    const toggle=e.target.closest('#jjSideDrawerToggle');
    if(toggle){e.preventDefault();e.stopImmediatePropagation();document.body.classList.contains('jj-poker-side-open')?jjV4CloseSideDrawer():jjV4OpenSideDrawer();return}
    if(e.target.closest('#jjSideDrawerClose,#jjSideDrawerBackdrop')){e.preventDefault();e.stopImmediatePropagation();jjV4CloseSideDrawer();return}
    if(e.target.closest('#backLobby,[data-view],[data-jump],[data-mobile-view],[data-more-view]'))jjV4CloseSideDrawer();
  },true);
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.body.classList.contains('jj-poker-side-open'))jjV4CloseSideDrawer()},true);
  window.addEventListener('resize',()=>{if(!jjV4CompactTable())jjV4CloseSideDrawer();if(currentTableId&&tableState)jjV4SyncTableTools()},{passive:true});

'''
    anchor = "  document.addEventListener('click',async e=>{\n    const back=e.target.closest('#backLobby');\n"
    if source.count(anchor) != 1:
        raise RuntimeError("player UX phase4 drift at phase3 listener anchor")
    source = source.replace(anchor, phase4_helpers + anchor, 1)
    return source


PHASE4_CSS = r'''

/* v2 player-ux phase4a readability 2026-09-12 */
/* Phase 3 already emits the legal total in <small>; the older v1.24 desktop
   rule hid it with !important. Keep the actual total visible everywhere. */
#actionBar .jj-v124-sizing .jj-size-btn{height:48px!important;min-height:48px!important;padding-top:4px!important;padding-bottom:4px!important}
#actionBar .jj-v124-sizing .jj-size-btn small{display:block!important}
#pokerRoom .jj-v4-table-tools{display:flex;align-items:center;gap:6px;margin-left:6px}
#pokerRoom .jj-v4-tool{min-height:38px;padding:7px 10px;white-space:nowrap;font-size:.72rem}
#pokerRoom .jj-v4-tool-short{display:none}
#pokerRoom .jj-v4-side-head,#jjSideDrawerBackdrop{display:none}

@media(max-width:1000px){
  /* A running viewIn transform makes position:fixed descendants use the view
     as their containing block. Compact poker drawers must be viewport-fixed
     even if the user opens them immediately after switching to Tables. */
  #tablesView.active-view{animation:none!important}
  #pokerRoom .jj-v4-side-head{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:0 0 10px;border-bottom:1px solid var(--line)}
  #pokerRoom .jj-v4-side-head strong{font-size:.82rem;color:var(--ink)}
  #pokerRoom .jj-v4-side-head .ghost{min-height:36px;padding:6px 10px;font-size:.7rem}
  #pokerRoom .table-side{display:block!important;position:fixed!important;z-index:190!important;left:max(8px,env(safe-area-inset-left))!important;right:max(8px,env(safe-area-inset-right))!important;bottom:calc(8px + env(safe-area-inset-bottom))!important;width:auto!important;max-width:680px!important;max-height:min(58dvh,520px)!important;margin:0 auto!important;padding:14px!important;overflow:hidden!important;background:var(--surface)!important;border:1px solid var(--line-strong)!important;border-radius:18px!important;box-shadow:0 24px 70px rgba(0,0,0,.28)!important;transform:translateY(calc(100% + 32px));opacity:0;pointer-events:none;transition:transform .18s ease,opacity .18s ease}
  body.jj-poker-side-open #pokerRoom .table-side{transform:translateY(0);opacity:1;pointer-events:auto}
  #jjSideDrawerBackdrop{display:block;position:fixed;z-index:185;inset:0;border:0;border-radius:0;background:rgba(4,12,9,.42);opacity:0;pointer-events:none;transition:opacity .16s ease}
  body.jj-poker-side-open #jjSideDrawerBackdrop{opacity:1;pointer-events:auto}
  #pokerRoom .table-side .side-tabs{margin:10px 0 8px}
  #pokerRoom #tableMessages,#pokerRoom #handLog{max-height:min(38dvh,340px);overflow:auto;overscroll-behavior:contain}
  #pokerRoom #tableChatForm{position:sticky;bottom:0;background:var(--surface);padding-top:8px}
}

@media(max-width:760px){
  /* Focus mode has desktop-only layout effects; hiding its no-op mobile control
     frees the compact header for settings and history. */
  #pokerRoom #jjFocusModeToggle{display:none!important}
  #pokerRoom .jj-v4-table-tools{margin-left:auto;gap:4px}
  #pokerRoom .jj-v4-tool-long{display:none}
  #pokerRoom .jj-v4-tool-short{display:inline}
  #pokerRoom .jj-v4-tool{min-height:36px;padding:6px 9px;border-radius:10px;font-size:.68rem}
  body.jj-mobile-table-open #pokerRoom .table-side{display:block!important;left:5px!important;right:5px!important;bottom:calc(5px + env(safe-area-inset-bottom))!important;max-height:min(58dvh,470px)!important;padding:12px!important}
  body.jj-mobile-table-open.jj-mobile-poker-can-act #pokerRoom .table-side{bottom:calc(184px + env(safe-area-inset-bottom))!important;max-height:min(42dvh,330px)!important}
  body.jj-mobile-table-open.jj-mobile-poker-can-act #jjSideDrawerBackdrop{bottom:calc(180px + env(safe-area-inset-bottom))}
  body.jj-poker-keyboard-open.jj-mobile-table-open #pokerRoom .table-side{bottom:calc(var(--jj-vv-bottom,0px) + 5px)!important;max-height:min(38dvh,280px)!important}
  body.jj-poker-keyboard-open.jj-mobile-table-open #jjSideDrawerBackdrop{bottom:var(--jj-vv-bottom,0px)}
  body.jj-mobile-table-open #actionBar .jj-v124-sizing .jj-size-btn{height:44px!important;min-height:44px!important;padding:2px 3px!important}
  body.jj-mobile-table-open #actionBar .jj-v124-sizing .jj-size-btn small{display:block!important;font-size:.54rem!important;line-height:1.05!important}

  /* Read values before labels: stack/bet/decision numbers receive the strongest
     weight while decorative labels stay compact. */
  body.jj-mobile-table-open #pokerRoom .jj-seat-box .name{font-size:.7rem!important;line-height:1.15!important}
  body.jj-mobile-table-open #pokerRoom .jj-seat-box .stack{font-size:.8rem!important;line-height:1.15!important;font-weight:900!important}
  body.jj-mobile-table-open #pokerRoom .jj-bet-marker{font-size:.68rem!important;font-weight:900!important}
  body.jj-mobile-table-open #actionBar .jj-v124-decision-meta span{font-size:.5rem!important;letter-spacing:.075em!important}
  body.jj-mobile-table-open #actionBar .jj-v124-decision-meta strong{font-size:.74rem!important;line-height:1.15!important}
  body.jj-mobile-table-open #actionBar .jj-main-actions .jj-action-btn b{font-size:.9rem!important;line-height:1.08!important}
  body.jj-mobile-table-open #actionBar .jj-main-actions .jj-action-btn small{font-size:.58rem!important;line-height:1.05!important}
}

@media(prefers-reduced-motion:reduce){
  #pokerRoom .table-side,#jjSideDrawerBackdrop{transition:none!important}
}
'''


def transform_styles(source: str) -> str:
    if PHASE4_MARKER in source:
        return source
    return source.rstrip() + PHASE4_CSS + "\n"
