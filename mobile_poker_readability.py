from __future__ import annotations

"""Final mobile table readability and expandable live hand-log treatment."""

MARKER = "v80 mobile poker readability and hand-log overlay 2026-10-06"

JS_PATCH = r'''
  // v80 mobile poker readability and hand-log overlay 2026-10-06
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
    if(isLog)requestAnimationFrame(()=>$('#handLog')?.scrollTo({top:0,behavior:'instant'}));
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
/* v80 mobile poker readability and hand-log overlay 2026-10-06 */
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
  /* Lower-side opponents show cards above their nameplate, toward the felt center. */
  body.jj-poker-simple.jj-mobile-table-open #pokerRoom .jj-seat[data-jj-visual="1"] .jj-hole,
  body.jj-poker-simple.jj-mobile-table-open #pokerRoom .jj-seat[data-jj-visual="5"] .jj-hole{
    top:-50px!important;bottom:auto!important;transform:translateX(-50%)!important;
  }
  /* Upper-side opponents show cards below their nameplate. This prevents the
     opposite seat's cards from being clipped by the top edge of the phone felt. */
  body.jj-poker-simple.jj-mobile-table-open #pokerRoom .jj-seat[data-jj-visual="2"] .jj-hole,
  body.jj-poker-simple.jj-mobile-table-open #pokerRoom .jj-seat[data-jj-visual="3"] .jj-hole,
  body.jj-poker-simple.jj-mobile-table-open #pokerRoom .jj-seat[data-jj-visual="4"] .jj-hole{
    top:calc(100% + 5px)!important;bottom:auto!important;transform:translateX(-50%)!important;
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
    source = _replace_once(
        source,
        """    const coords=[
      {left:50,top:82},
      {left:13,top:64},
      {left:18,top:31},
      {left:50,top:15},
      {left:82,top:31},
      {left:87,top:64},
    ];""",
        """    const coords=[
      {left:50,top:83},
      {left:14,top:65},
      {left:15,top:34},
      {left:50,top:21},
      {left:85,top:34},
      {left:86,top:65},
    ];""",
        "portrait seat coordinates",
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
