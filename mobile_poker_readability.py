from __future__ import annotations

"""Final mobile table readability and expandable live hand-log treatment."""

MARKER = "v81 mobile poker readability, compact controls, and hand-log overlay 2026-10-06"

JS_PATCH = r'''
  // v81 mobile poker readability, compact controls, and hand-log overlay 2026-10-06
  const jjV80PortraitMq=window.matchMedia('(max-width:760px) and (orientation:portrait)');
  const jjV80BaseSeatPos=jjSeatPos;
  jjSeatPos=function(actual){
    if(!jjV80PortraitMq.matches)return jjV80BaseSeatPos(actual);
    const coords=[
      {left:50,top:84},
      {left:16,top:68},
      {left:17,top:34},
      {left:50,top:15},
      {left:83,top:34},
      {left:84,top:68},
    ];
    return coords[jjVisualIndex(actual)]||coords[0];
  };
  let jjV80SideReturnFocus=null;
  function jjV80SyncSideChrome(tab){
    const side=$('#pokerRoom .table-side'),head=$('#pokerRoom .jj-v4-side-head');
    if(!side||!head)return;
    const isLog=tab==='log';
    head.innerHTML='<strong id="jjV80SideTitle">'+(isLog?'ハンドログ':'テーブルチャット')+'</strong><div class="jj-v80-side-actions"><button type="button" class="ghost" data-jj-handlog-expand '+(isLog?'':'hidden')+' aria-label="ハンドログを拡大">⛶ 拡大</button><button type="button" class="ghost jj-v80-side-close" id="jjV4SideClose" aria-label="卓に戻る">×</button></div>';
    side.setAttribute('aria-label',isLog?'ハンドログ':'テーブルチャット');
  }
  const jjV80BaseOpenSide=jjV4OpenSide;
  jjV4OpenSide=function(tab){
    jjV80SideReturnFocus=document.activeElement;
    jjV80BaseOpenSide(tab);
    const isLog=tab==='log';
    document.body.classList.toggle('jj-v80-handlog-open',isLog);
    document.body.classList.remove('jj-v80-handlog-expanded');
    if(isLog&&window.matchMedia('(max-width:760px)').matches)document.body.classList.add('jj-v80-handlog-expanded');
    jjV80SyncSideChrome(tab);
    if(isLog)requestAnimationFrame(()=>{const log=$('#handLog');if(log)log.scrollTop=0});
  };
  const jjV80BaseCloseSide=jjV4CloseSide;
  jjV4CloseSide=function(){
    document.body.classList.remove('jj-v80-handlog-open','jj-v80-handlog-expanded');
    jjV80BaseCloseSide();
    const target=jjV80SideReturnFocus;jjV80SideReturnFocus=null;
    if(target&&typeof target.focus==='function')requestAnimationFrame(()=>target.focus({preventScroll:true}));
  };
  function jjV80ToggleHandLogExpanded(){
    if(!document.body.classList.contains('jj-v80-handlog-open'))return;
    const expanded=document.body.classList.toggle('jj-v80-handlog-expanded');
    const btn=$('[data-jj-handlog-expand]');
    if(btn){btn.textContent=expanded?'↙ 縮小':'⛶ 拡大';btn.setAttribute('aria-label',expanded?'ハンドログを縮小':'ハンドログを拡大')}
  }
  document.addEventListener('click',e=>{
    const expand=e.target.closest('[data-jj-handlog-expand]');
    if(expand){e.preventDefault();e.stopImmediatePropagation();jjV80ToggleHandLogExpanded()}
  },true);
'''

CSS = r'''
/* v81 mobile poker readability, compact controls, and hand-log overlay 2026-10-06 */
body.jj-poker-simple #pokerRoom .jj-v80-side-actions{display:flex;align-items:center;gap:7px;margin-left:auto}
body.jj-poker-simple #pokerRoom .jj-v80-side-actions button{min-width:44px;min-height:40px!important;padding:0 10px!important}
body.jj-poker-simple #pokerRoom .jj-v80-side-close{font-size:1.45rem!important;line-height:1!important;padding:0!important}
body.jj-poker-simple.jj-v80-handlog-open #pokerRoom #tableChatPanel{display:none!important}
body.jj-poker-simple.jj-v80-handlog-open #pokerRoom #handLogPanel{display:flex!important;flex:1 1 auto;min-height:0;overflow:hidden}
body.jj-poker-simple.jj-v80-handlog-open #pokerRoom .hand-log{
  flex:1 1 auto!important;height:auto!important;min-height:0!important;overflow:auto!important;
  padding:6px 10px 18px!important;scrollbar-gutter:stable;
}
body.jj-poker-simple.jj-v80-handlog-open #pokerRoom .hand-log>div{
  padding:12px 10px!important;border-bottom:1px solid rgba(255,255,255,.09)!important;
  color:#e4eee9!important;font-size:.88rem!important;line-height:1.55!important;overflow-wrap:anywhere;
}
body.jj-poker-simple.jj-v80-handlog-expanded{overflow:hidden!important}
body.jj-poker-simple.jj-v80-handlog-expanded #pokerRoom .table-side{
  display:flex!important;position:fixed!important;z-index:260!important;inset:0!important;
  width:100vw!important;height:100dvh!important;max-width:none!important;max-height:none!important;
  margin:0!important;padding:0 14px max(16px,env(safe-area-inset-bottom))!important;
  border:0!important;border-radius:0!important;background:#0d1713!important;overflow:hidden!important;
  box-shadow:none!important;flex-direction:column!important;
}
body.jj-poker-simple.jj-v80-handlog-expanded #pokerRoom .jj-v4-side-head{
  position:sticky!important;top:0!important;z-index:3!important;margin:0 -14px 8px!important;
  padding:max(10px,env(safe-area-inset-top)) 14px 10px!important;min-height:58px!important;
  background:#101c17!important;border-bottom:1px solid rgba(255,255,255,.1)!important;
}
body.jj-poker-simple.jj-v80-handlog-expanded #pokerRoom .side-tabs{display:none!important}

@media(max-width:760px) and (orientation:portrait){
  body.jj-poker-simple.jj-mobile-table-open #pokerRoom .jj-seat{width:98px!important}
  body.jj-poker-simple.jj-mobile-table-open #pokerRoom .jj-seat-box{padding:6px 7px 7px!important}
  body.jj-poker-simple.jj-mobile-table-open #pokerRoom .jj-seat-box .name{font-size:.72rem!important;max-width:84px!important}
  body.jj-poker-simple.jj-mobile-table-open #pokerRoom .jj-seat-box .stack{font-size:.78rem!important}
  body.jj-poker-simple.jj-mobile-table-open #pokerRoom .jj-seat:not(.is-hero) .jj-hole{
    position:absolute!important;left:50%!important;display:flex!important;gap:3px!important;z-index:14!important;
  }
  body.jj-poker-simple.jj-mobile-table-open #pokerRoom .jj-seat:not(.is-hero) .jj-hole .card-face{
    width:34px!important;height:48px!important;min-width:34px!important;min-height:48px!important;
    font-size:.9rem!important;opacity:1!important;
  }
  /* Keep exposed opponent cards outside the board lane. Lower side seats fan
     inward horizontally, upper side seats fan upward, and the top seat fans
     downward. This prevents the six-max orbit from covering the community cards. */
  body.jj-poker-simple.jj-mobile-table-open #pokerRoom .jj-seat[data-jj-visual="1"]:not(.is-hero) .jj-hole,
  body.jj-poker-simple.jj-mobile-table-open #pokerRoom .jj-seat[data-jj-visual="5"]:not(.is-hero) .jj-hole{
    left:50%!important;right:auto!important;top:calc(100% + 5px)!important;bottom:auto!important;
    transform:translateX(-50%)!important;
  }
  body.jj-poker-simple.jj-mobile-table-open #pokerRoom .jj-seat[data-jj-visual="2"]:not(.is-hero) .jj-hole,
  body.jj-poker-simple.jj-mobile-table-open #pokerRoom .jj-seat[data-jj-visual="4"]:not(.is-hero) .jj-hole{
    left:50%!important;right:auto!important;top:auto!important;bottom:calc(100% + 5px)!important;
    transform:translateX(-50%)!important;
  }
  body.jj-poker-simple.jj-mobile-table-open #pokerRoom .jj-seat[data-jj-visual="3"]:not(.is-hero) .jj-hole{
    left:50%!important;right:auto!important;top:calc(100% + 5px)!important;bottom:auto!important;
    transform:translateX(-50%)!important;
  }

  /* The live table owns the viewport as a vertical flex surface. The old
     simplified-table override forced a 222px action panel even while waiting,
     which produced a large white dead area and pushed the hero cards off-canvas. */
  body.jj-poker-simple.jj-mobile-table-open #pokerRoom{
    display:flex!important;flex-direction:column!important;overflow:hidden!important;
    background:#040907!important;
  }
  body.jj-poker-simple.jj-mobile-table-open #pokerRoom .poker-layout{
    display:flex!important;flex:1 1 auto!important;min-height:0!important;overflow:hidden!important;
  }
  body.jj-poker-simple.jj-mobile-table-open #pokerRoom .poker-zone{
    display:flex!important;flex:1 1 auto!important;flex-direction:column!important;
    min-height:0!important;overflow-y:auto!important;overflow-x:hidden!important;padding:0!important;
    background:linear-gradient(180deg,#07100d 0%,#040907 100%)!important;
    overscroll-behavior:contain;
  }
  body.jj-poker-simple.jj-mobile-table-open #pokerTable{
    flex:1 1 auto!important;height:auto!important;min-height:380px!important;width:100%!important;
    margin:0!important;overflow:hidden!important;
  }
  body.jj-poker-simple.jj-mobile-table-open #pokerTable .felt-center{
    top:45%!important;min-width:0!important;width:min(72%,320px)!important;max-width:calc(100% - 92px)!important;
  }
  body.jj-poker-simple.jj-mobile-table-open #boardCards{
    display:flex!important;align-items:center!important;justify-content:center!important;
    flex-wrap:nowrap!important;gap:4px!important;width:100%!important;min-width:0!important;
  }
  body.jj-poker-simple.jj-mobile-table-open #boardCards .card-face{
    position:relative!important;inset:auto!important;transform:none!important;flex:0 0 auto!important;
    width:clamp(40px,11vw,48px)!important;height:clamp(56px,15.4vw,66px)!important;
    min-width:0!important;min-height:0!important;margin:0!important;font-size:.94rem!important;
  }

  /* Settlement is part of the layout, not an overlay over the top seat/board. */
  body.jj-poker-simple.jj-mobile-table-open #resultBanner.result-banner:not(.hidden){
    order:-1!important;position:relative!important;z-index:25!important;left:auto!important;right:auto!important;
    top:auto!important;bottom:auto!important;transform:none!important;width:auto!important;max-width:none!important;
    min-height:0!important;max-height:86px!important;overflow:auto!important;margin:5px 8px 6px!important;
    padding:8px 10px!important;border-radius:11px!important;pointer-events:auto!important;
  }
  body.jj-poker-simple.jj-mobile-table-open #resultBanner.result-banner:not(.hidden):not(.jj-v5-result-compact){
    max-height:min(38dvh,300px)!important;
  }

  body.jj-poker-simple.jj-mobile-table-open #tableControls{
    display:flex!important;flex:0 0 auto!important;gap:6px!important;height:auto!important;min-height:48px!important;
    margin:0!important;padding:4px 6px!important;background:#07100d!important;
    border-top:1px solid rgba(255,255,255,.07)!important;overflow:visible!important;
  }
  body.jj-poker-simple.jj-mobile-table-open #tableControls button{
    flex:1 1 140px!important;height:42px!important;min-height:42px!important;max-height:none!important;
    padding:0 8px!important;font-size:.72rem!important;
  }

  body.jj-poker-simple.jj-mobile-table-open #actionBar{
    display:block!important;position:relative!important;inset:auto!important;flex:0 0 auto!important;
    width:100%!important;min-height:0!important;height:auto!important;max-height:none!important;
    overflow:visible!important;margin:0!important;padding:6px 8px max(7px,env(safe-area-inset-bottom))!important;
    border:0!important;border-top:1px solid rgba(255,255,255,.08)!important;border-radius:0!important;
    background:#07100d!important;color:#eaf2ee!important;box-shadow:none!important;
  }
  body.jj-poker-simple.jj-mobile-table-open #actionBar .jj-v7-hero-strip{
    display:flex!important;align-items:center!important;justify-content:center!important;flex-wrap:wrap!important;
    gap:7px 10px!important;width:100%!important;min-width:0!important;min-height:0!important;margin:0 0 4px!important;
  }
  body.jj-poker-simple.jj-mobile-table-open #actionBar .jj-v7-hand{
    display:flex!important;align-items:center!important;justify-content:center!important;gap:4px!important;
    flex:0 0 auto!important;min-width:80px!important;margin:0!important;transform:none!important;
  }
  body.jj-poker-simple.jj-mobile-table-open #actionBar .jj-v7-hand .card-face{
    position:relative!important;inset:auto!important;transform:none!important;
    width:38px!important;height:52px!important;min-width:38px!important;min-height:52px!important;
    margin:0!important;font-size:.94rem!important;
  }
  body.jj-poker-simple.jj-mobile-table-open #actionBar .jj-v7-stack,
  body.jj-poker-simple.jj-mobile-table-open #actionBar .jj-v7-timebank{flex:0 0 auto!important}
  body.jj-poker-simple.jj-mobile-table-open #actionBar .jj-action-clock{
    flex:1 0 100%!important;margin-left:0!important;text-align:center!important;line-height:1.2!important;
  }
  body.jj-poker-simple.jj-mobile-table-open #actionBar .jj-action-clock:empty{display:none!important}
  body.jj-poker-simple.jj-mobile-table-open:not(.jj-mobile-poker-can-act) #actionBar{
    max-height:148px!important;overflow:hidden!important;box-sizing:border-box!important;
  }
  body.jj-poker-simple.jj-mobile-table-open:not(.jj-mobile-poker-can-act) #actionBar:not(:has(.jj-v5-preactions)){
    height:72px!important;min-height:72px!important;max-height:72px!important;
  }
  body.jj-poker-simple.jj-mobile-table-open:not(.jj-mobile-poker-can-act) #actionBar .jj-v7-hero-strip{
    min-height:54px!important;margin-bottom:0!important;
  }
  body.jj-poker-simple.jj-mobile-table-open.jj-mobile-poker-can-act #actionBar{
    max-height:min(42dvh,320px)!important;overflow-y:auto!important;overscroll-behavior:contain;
  }

  body.jj-poker-simple.jj-v80-handlog-open #pokerRoom .table-side{
    display:flex!important;position:fixed!important;z-index:260!important;inset:0!important;
    width:100vw!important;height:100dvh!important;max-width:none!important;max-height:none!important;
    margin:0!important;padding:0 12px max(14px,env(safe-area-inset-bottom))!important;border:0!important;
    border-radius:0!important;background:#0d1713!important;overflow:hidden!important;flex-direction:column!important;
  }
  body.jj-poker-simple.jj-v80-handlog-open #pokerRoom .jj-v4-side-head{
    position:sticky!important;top:0!important;margin:0 -12px 8px!important;
    padding:max(10px,env(safe-area-inset-top)) 12px 10px!important;min-height:58px!important;
  }
  body.jj-poker-simple.jj-v80-handlog-open #pokerRoom .side-tabs{display:none!important}
  body.jj-poker-simple.jj-v80-handlog-open #pokerRoom [data-jj-handlog-expand]{display:none!important}
  body.jj-poker-simple.jj-v80-handlog-open #pokerRoom .hand-log>div{font-size:.94rem!important;line-height:1.62!important;padding:13px 8px!important}
}

@media(max-width:390px) and (orientation:portrait){
  body.jj-poker-simple.jj-mobile-table-open #pokerRoom .jj-seat{width:92px!important}
  body.jj-poker-simple.jj-mobile-table-open #pokerRoom .jj-seat-box .name{font-size:.69rem!important;max-width:78px!important}
}
'''


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"mobile poker readability drift at {label}: expected 1, found {count}")
    return source.replace(old, new, 1)


def transform_app_js(source: str) -> str:
    if MARKER in source:
        return source

    source = _replace_once(
        source,
        'return `<div class="seat jj-seat seat-empty" style="left:${pos.left}%;top:${pos.top}%"><button class="jj-empty-seat" data-seat="${seat}">＋</button></div>`;',
        'return `<div class="seat jj-seat seat-empty" data-jj-visual="${jjVisualIndex(seat)}" style="left:${pos.left}%;top:${pos.top}%"><button class="jj-empty-seat" data-seat="${seat}">＋</button></div>`;',
        "empty seat visual index",
    )
    source = _replace_once(
        source,
        'return `<div class="seat jj-seat ${isAct?\'active\':\'\'}${isHero?\' is-hero\':\'\'}${statusClass}" style="left:${pos.left}%;top:${pos.top}%">',
        'return `<div class="seat jj-seat ${isAct?\'active\':\'\'}${isHero?\' is-hero\':\'\'}${statusClass}" data-jj-visual="${jjVisualIndex(seat)}" style="left:${pos.left}%;top:${pos.top}%">',
        "occupied seat visual index",
    )
    anchor = "  // Desktop bet markers use explicit poker-table lanes rather than the old\n"
    if source.count(anchor) != 1:
        raise RuntimeError("mobile poker readability drift at helper anchor")
    return source.replace(anchor, JS_PATCH + "\n" + anchor, 1)


def transform_styles(source: str) -> str:
    if MARKER in source:
        return source
    return source.rstrip() + "\n" + CSS + "\n"


__all__ = ["MARKER", "transform_app_js", "transform_styles"]
