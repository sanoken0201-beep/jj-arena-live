from __future__ import annotations

"""Final live-table simplification and action reliability layer.

The materialized v1.24.4 client remains immutable. This transform runs after the
historical UX stack and Sit&Go UI transform, and owns only the presentation and
interaction surface of an open ring table.

Goals:
- keep the live table focused on cards, board, pot, stacks and legal actions;
- render the hero's private cards in a dedicated layer independent of seat-box
  geometry, so responsive layout cannot hide the hand;
- remove confusing safe pre-actions and redundant live-table chrome;
- give desktop CHECK/FOLD clicks one deterministic dispatch path without
  changing server betting legality or settlement.
"""

POKER_TABLE_FOCUS_MARKER = "jj poker table focus 2026-09-15"


_APP_PATCH = r'''
  // jj poker table focus 2026-09-15
  function jjFocusHero(){
    return tableState?.seats?.find(p=>Number(p.user_id)===Number(me?.id))||null;
  }

  function jjFocusRenderHeroHand(){
    const table=$('#pokerTable');
    if(!table)return;
    const hero=jjFocusHero(),playing=tableState?.status==='playing';
    const cards=Array.isArray(hero?.cards)?hero.cards:[];
    let dock=$('#jjHeroHandDock',table);
    if(!hero||!playing){dock?.remove();return}
    if(!dock){
      dock=document.createElement('div');
      dock.id='jjHeroHandDock';
      dock.className='jj-hero-hand-dock';
      dock.setAttribute('aria-label','あなたのホールカード');
      table.appendChild(dock);
    }
    const visible=cards.filter(c=>c&&c!=='??');
    const complete=visible.length===2;
    dock.classList.toggle('is-syncing',!complete);
    dock.innerHTML=complete
      ? `<div class="jj-hero-hand-cards">${cards.map(cardHTML).join('')}</div><span>YOU</span>`
      : '<div class="jj-hero-hand-sync" role="status">カードを同期中…</div><span>YOU</span>';
  }

  function jjFocusSimplifyRoom(){
    const room=$('#pokerRoom');if(!room)return;
    const hero=jjFocusHero(),live=tableState?.status==='playing';
    room.classList.toggle('jj-focus-hand-live',!!live);
    room.classList.toggle('jj-focus-seated',!!hero);
    room.classList.toggle('jj-focus-can-act',!!tableState?.legal?.can_act);

    // These controls are useful in settings/review contexts, not in the live
    // decision surface. Keep the underlying features intact outside the table.
    $('#jjPokerSettings',room)?.remove();
    $('#jjFocusModeToggle',room)?.remove();
    $('#jjSoundToggle',room)?.remove();
    $('#jjV5HotkeyBadge',room)?.remove();

    // Phase 4B pre-actions added a second CHECK/FOLD concept that has proved
    // confusing and unreliable on desktop. The live table now exposes only
    // authoritative server-legal actions.
    if(typeof jjV5ClearPreAction==='function')jjV5ClearPreAction();

    // Hero cards now have one authoritative visual location. Keep name/stack
    // in the seat box but remove the duplicate seat-attached hole-card layer.
    room.querySelector('.jj-seat.is-hero .jj-hole')?.remove();
  }

  // Action buttons are controls, never form submitters. This also prevents
  // browser-dependent default-button behaviour if surrounding markup evolves.
  if(typeof jjV124ActionButtons==='function'){
    const jjFocusBaseActionButtons=jjV124ActionButtons;
    jjV124ActionButtons=function(l){
      return jjFocusBaseActionButtons(l).replace(/<button class="jj-action-btn/g,'<button type="button" class="jj-action-btn');
    };
  }

  const jjFocusBaseRenderPokerRoom=renderPokerRoom;
  renderPokerRoom=function(){
    jjFocusBaseRenderPokerRoom();
    jjFocusSimplifyRoom();
    jjFocusRenderHeroHand();
  };

  // CHECK/FOLD had accumulated several historical click listeners. Give these
  // two zero/low-complexity actions one final explicit dispatch path. Earlier
  // safety capture handlers still run first, so stale-state protection remains.
  let jjFocusSafeActionBusy=false;
  document.addEventListener('click',async e=>{
    const btn=e.target.closest('#actionBar [data-action="check"],#actionBar [data-action="fold"]');
    if(!btn)return;
    e.preventDefault();
    e.stopImmediatePropagation();
    if(btn.disabled||jjFocusSafeActionBusy)return;
    const action=btn.dataset.action,l=tableState?.legal||{};
    if(!l.can_act)return toast('現在はあなたのアクションではありません');
    if(action==='check'&&!l.can_check)return toast('現在はチェックできません');
    if(action==='fold'&&l.disabled_reasons?.fold)return toast(l.disabled_reasons.fold);
    if(typeof jjV2Connection!=='undefined'&&!jjV2Connection.fresh)return toast('最新の卓状態を同期中です');
    jjFocusSafeActionBusy=true;
    btn.disabled=true;
    try{await doAction(action)}
    finally{
      jjFocusSafeActionBusy=false;
      // A WebSocket/poll render normally replaces this node. If it has not yet
      // arrived, restore the button only when the same decision remains legal.
      if(btn.isConnected&&tableState?.legal?.can_act){
        if(action==='check'&&tableState.legal.can_check)btn.disabled=false;
        if(action==='fold'&&!tableState.legal.disabled_reasons?.fold)btn.disabled=false;
      }
    }
  },true);
'''


_CSS_PATCH = r'''

/* jj poker table focus 2026-09-15 */
/* Live poker should read like a poker client, not an operations dashboard. */
#pokerRoom .room-head{min-height:48px!important;padding-block:6px!important}
#pokerRoom .room-head .eyebrow{display:none!important}
#pokerRoom #roomTitle{margin:0!important}
#pokerRoom #roomMeta{font-size:0!important;min-width:0!important}
#pokerRoom #roomMeta .jj-connection-status{font-size:.64rem!important}
#pokerRoom #roomMeta .jj-connection-status:not(.is-degraded){display:none!important}
#pokerRoom #jjPokerSettings,
#pokerRoom #jjFocusModeToggle,
#pokerRoom #jjSoundToggle,
#pokerRoom #jjV5HotkeyBadge,
#pokerRoom .jj-v4-mobile-tools,
#actionBar .jj-v5-preactions,
#actionBar .jj-v124-decision-meta,
#actionBar #jjV123DisabledHints,
#actionBar #jjV123ActionStatus{display:none!important}

/* Keep only controls that affect participation outside an active decision. */
#pokerRoom.jj-focus-hand-live.jj-focus-can-act #tableControls{display:none!important}
#pokerRoom.jj-focus-hand-live #tableControls .jj-ready-count{display:none!important}
#pokerRoom.jj-focus-hand-live #tableControls{min-height:0!important;padding-block:4px!important}
#pokerRoom.jj-focus-hand-live #tableControls button{min-height:34px!important;padding:0 10px!important;font-size:.68rem!important}

/* The hero hand is independent from responsive seat geometry. */
#pokerTable .jj-hero-hand-dock{
  position:absolute!important;z-index:48!important;left:50%!important;bottom:5.5%!important;
  transform:translateX(-50%)!important;display:flex!important;flex-direction:column!important;
  align-items:center!important;justify-content:center!important;gap:3px!important;
  pointer-events:none!important;filter:drop-shadow(0 7px 12px rgba(0,0,0,.45))!important;
}
#pokerTable .jj-hero-hand-cards{display:flex!important;align-items:flex-end!important;justify-content:center!important;gap:5px!important}
#pokerTable .jj-hero-hand-dock .card-face{width:52px!important;height:72px!important;font-size:1.18rem!important;border-radius:8px!important;opacity:1!important;visibility:visible!important}
#pokerTable .jj-hero-hand-dock>span{font-size:.56rem!important;line-height:1!important;font-weight:950!important;letter-spacing:.12em!important;color:#f5e29a!important;text-shadow:0 1px 5px #000!important}
#pokerTable .jj-hero-hand-sync{min-width:118px!important;padding:9px 12px!important;border-radius:10px!important;background:rgba(6,15,12,.94)!important;border:1px solid rgba(245,226,154,.45)!important;color:#f4f8f6!important;font-size:.7rem!important;font-weight:800!important;text-align:center!important}
#pokerRoom .jj-seat.is-hero .jj-hole{display:none!important}

/* Primary decisions stay visually dominant and always receive pointer input. */
#pokerRoom #actionBar{position:relative!important;z-index:70!important;pointer-events:auto!important}
#pokerRoom #actionBar .jj-main-actions{position:relative!important;z-index:2!important;gap:8px!important}
#pokerRoom #actionBar .jj-action-btn{pointer-events:auto!important;touch-action:manipulation!important;cursor:pointer!important;min-height:52px!important}
#pokerRoom #actionBar .jj-action-btn:disabled{cursor:not-allowed!important}
#pokerRoom #actionBar .jj-v124-sizing{margin-block:0 7px!important}
#pokerRoom #actionBar .jj-sub-bet-hint{display:none!important}

@media(min-width:761px){
  #pokerRoom .poker-zone{padding-top:8px!important}
  #pokerRoom #pokerTable{min-height:520px!important}
  #pokerRoom #actionBar{max-width:760px!important;margin:8px auto 0!important;padding:8px 10px!important}
  #pokerRoom #actionBar .jj-main-actions{grid-template-columns:repeat(var(--jj-action-count,3),minmax(0,1fr))!important}
  #pokerRoom #actionBar .jj-action-btn{font-size:.82rem!important}
  #pokerRoom #actionBar .jj-action-btn b{font-size:.9rem!important}
  #pokerRoom #tableControls{max-width:760px!important;margin-inline:auto!important}
}

@media(max-width:760px){
  body.jj-mobile-table-open #pokerRoom .room-head{grid-template-columns:auto minmax(0,1fr)!important}
  body.jj-mobile-table-open #roomMeta{display:none!important}
  body.jj-mobile-table-open #pokerTable .jj-hero-hand-dock{bottom:7%!important}
  body.jj-mobile-table-open #pokerTable .jj-hero-hand-dock .card-face{width:42px!important;height:58px!important;font-size:1rem!important}
  body.jj-mobile-table-open #pokerRoom #actionBar .jj-action-btn{min-height:48px!important}
}
'''


def transform_app_js(source: str) -> str:
    if POKER_TABLE_FOCUS_MARKER in source:
        return source
    anchor = "\n  init();"
    position = source.rfind(anchor)
    if position < 0:
        raise RuntimeError("poker table focus drift: init anchor not found")
    return source[:position] + "\n" + _APP_PATCH.rstrip() + source[position:]


def transform_styles(source: str) -> str:
    if POKER_TABLE_FOCUS_MARKER in source:
        return source
    return source.rstrip() + _CSS_PATCH + "\n"


__all__ = ["POKER_TABLE_FOCUS_MARKER", "transform_app_js", "transform_styles"]
