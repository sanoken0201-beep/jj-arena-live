from __future__ import annotations
from pathlib import Path
import re


def apply(root: Path) -> None:
    _server(root / 'server.py')
    _app(root / 'static' / 'app.js')
    _styles(root / 'static' / 'styles.css')
    _index(root / 'static' / 'index.html')
    _sw(root / 'static' / 'sw.js')


def _server(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    s = s.replace('version="1.14.2"', 'version="1.15.0"').replace('"version":"1.14.2"', '"version":"1.15.0"')
    s = s.replace('request.url.query == "v=26"', 'request.url.query == "v=27"')
    p.write_text(s, encoding='utf-8')


def _app(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    if 'v1.15 responsive poker workspace' in s:
        return
    marker = '})();'
    pos = s.rfind(marker)
    if pos < 0:
        raise RuntimeError('v1.15 app.js closing marker not found')
    addon = r'''

  // v1.15 responsive poker workspace. The table is sized from its real column,
  // not from the viewport, so the felt can never invade chat/log or create a
  // horizontal page scrollbar. This wrapper preserves the v1.14 game UI logic.
  function jjFitPokerWorkspace(){
    const room=$('#pokerRoom'),zone=$('#pokerRoom .poker-zone');
    if(!room||!zone||room.classList.contains('hidden'))return;
    const zoneWidth=Math.max(300,zone.clientWidth-24),vh=Math.max(560,window.innerHeight||800);
    let height;
    if(window.innerWidth<=760){height=Math.max(430,Math.min(560,vh*.62));}
    else{height=Math.max(500,Math.min(680,zoneWidth*.61,vh*.74));}
    room.style.setProperty('--jj-stage-h',`${Math.round(height)}px`);
  }

  const jjV15RenderPokerRoom=renderPokerRoom;
  renderPokerRoom=function(){
    jjV15RenderPokerRoom();
    requestAnimationFrame(jjFitPokerWorkspace);
  };

  renderHandStatusOnly=function(){
    if(!tableState)return;
    const el=$('#handStatus');if(!el)return;
    const phase=tableState.hand?.phase||'waiting',actionSeat=tableState.hand?.action_seat,
      acting=tableState.seats.find(p=>p.seat===actionSeat),deadline=tableState.hand?.action_deadline;
    let sec='';
    if(deadline){const left=Math.max(0,Math.ceil((new Date(deadline)-new Date())/1000));sec=` · ${left}s`;}
    if(tableState.status==='playing'){
      const mine=acting?.user_id===me?.id;
      el.innerHTML=`<b>${jjStreetLabel[phase]||String(phase).toUpperCase()}</b><span class="${mine?'jj-your-turn':''}">${mine?'YOUR TURN':acting?`${safe(acting.name)} TO ACT`:''}${sec}</span>`;
    }else if(tableState.session_active){
      el.innerHTML='<b>NEXT HAND</b><span>自動ディール</span>';
    }else{
      el.innerHTML='<b>TABLE READY</b><span>全員のREADYで開始</span>';
    }
  };

  let jjFitTimer=null;
  window.addEventListener('resize',()=>{
    clearTimeout(jjFitTimer);
    jjFitTimer=setTimeout(jjFitPokerWorkspace,80);
  },{passive:true});
'''
    s = s[:pos] + addon + s[pos:]
    p.write_text(s, encoding='utf-8')


def _styles(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    if 'v1.15 contained poker workspace' in s:
        return
    s += r'''

/* v1.15 contained poker workspace
   One bounded game stage + one bounded utility column. No child is allowed to
   determine page width. The felt lives inside the stage instead of being the
   stage itself, which removes the double-oval/oversized-table failure mode. */
#tablesView{overflow-x:hidden!important;max-width:100%!important}
#pokerRoom{--jj-side-w:clamp(270px,21vw,320px);container-type:inline-size;max-width:100%!important;min-width:0!important;overflow:visible!important}
#pokerRoom .room-head{max-width:100%;min-width:0}
#pokerRoom .poker-layout{display:grid!important;grid-template-columns:minmax(0,1fr) var(--jj-side-w)!important;gap:14px!important;align-items:start!important;width:100%!important;max-width:100%!important;min-width:0!important;overflow:visible!important}
#pokerRoom .poker-zone,#pokerRoom .table-side{min-width:0!important;max-width:100%!important;box-sizing:border-box!important}
#pokerRoom .poker-zone{position:relative!important;isolation:isolate;width:100%!important;overflow:hidden!important;padding:12px!important;border-radius:18px!important;background:linear-gradient(180deg,#111816,#090f0d)!important}

/* The rectangular stage owns all geometry. The inner ::before is the only felt. */
#pokerTable{position:relative!important;width:100%!important;max-width:100%!important;min-width:0!important;height:var(--jj-stage-h,600px)!important;min-height:0!important;max-height:none!important;aspect-ratio:auto!important;overflow:hidden!important;border:0!important;border-radius:16px!important;background:radial-gradient(circle at 50% 42%,#111b17 0%,#09120f 70%,#050b09 100%)!important;box-shadow:inset 0 0 0 1px rgba(255,255,255,.045),inset 0 -36px 90px rgba(0,0,0,.30),0 16px 38px rgba(0,0,0,.22)!important}
#pokerTable:before{display:block!important;content:""!important;position:absolute!important;left:4.5%!important;right:4.5%!important;top:7.5%!important;bottom:7.5%!important;border-radius:50%!important;background:radial-gradient(ellipse at 50% 40%,#137b57 0%,#0b694b 40%,#07533c 72%,#043829 100%)!important;border:clamp(9px,1vw,13px) solid #161d1a!important;outline:2px solid rgba(203,163,79,.72)!important;outline-offset:-5px!important;box-shadow:inset 0 0 0 2px rgba(255,255,255,.055),inset 0 0 75px rgba(0,0,0,.29),0 12px 28px rgba(0,0,0,.34)!important;z-index:0!important;pointer-events:none!important}
#pokerTable:after{z-index:1!important;top:58%!important;pointer-events:none!important}
#pokerTable #seatLayer{position:absolute!important;inset:0!important;z-index:4!important;pointer-events:none}
#pokerTable #seatLayer .jj-seat,#pokerTable #seatLayer .jj-empty-seat{pointer-events:auto}
#pokerTable .felt-center{top:42%!important;width:min(66%,560px)!important;min-width:0!important;max-width:66%!important;z-index:3!important}
#pokerTable .cards.board{max-width:100%;flex-wrap:nowrap}

/* Player and bet information must remain above the felt and inside the stage. */
#pokerRoom .jj-seat{z-index:7!important;max-width:158px}
#pokerRoom .jj-seat-box{backdrop-filter:blur(6px)}
#pokerRoom .jj-bet-marker{z-index:8!important;padding:5px 9px!important;background:rgba(4,11,9,.96)!important;border-color:rgba(244,205,93,.88)!important;box-shadow:0 5px 14px rgba(0,0,0,.42)!important}
#pokerRoom .jj-bet-marker b{font-size:clamp(.76rem,.9vw,.92rem)!important;font-variant-numeric:tabular-nums!important}
#pokerRoom .jj-seat.active .jj-seat-box{border-color:#f4ce5d!important;box-shadow:0 0 0 2px rgba(244,206,93,.24),0 8px 22px rgba(0,0,0,.36)!important}

/* The utility column is a real sibling, never an overlay. */
#pokerRoom .table-side{display:flex!important;flex-direction:column!important;width:100%!important;height:var(--jj-stage-h,600px)!important;min-height:0!important;max-height:none!important;overflow:hidden!important;padding:14px!important;position:relative!important;z-index:1!important}
#pokerRoom .side-tabs{flex:0 0 auto}
#pokerRoom #tableChatPanel,#pokerRoom #handLogPanel{min-height:0;flex:1 1 auto;overflow:hidden}
#pokerRoom #tableChatPanel:not(.hidden){display:flex;flex-direction:column}
#pokerRoom #handLogPanel:not(.hidden){display:flex;flex-direction:column}
#pokerRoom .table-messages,#pokerRoom .hand-log{height:auto!important;min-height:0!important;max-height:none!important;flex:1 1 auto!important;overflow:auto!important;overscroll-behavior:contain}
#pokerRoom .chat-form{flex:0 0 auto;margin-top:8px!important}

/* Controls inherit the game column width and can shrink without forcing overflow. */
#pokerRoom .table-controls,#pokerRoom .action-bar,#pokerRoom .jj-sizing,#pokerRoom .jj-raise-editor,#pokerRoom .jj-main-actions{width:100%;max-width:100%;min-width:0}
#pokerRoom .jj-raise-editor{grid-template-columns:minmax(90px,1fr) 84px auto!important}
#pokerRoom .jj-size-row{min-width:0}

/* If the actual content column is not wide enough for a useful table + chat,
   stack chat underneath. This is container-based, so a desktop sidebar or zoom
   level cannot recreate the overlap seen in v1.14. */
@container (max-width:1120px){
  #pokerRoom .poker-layout{grid-template-columns:minmax(0,1fr)!important}
  #pokerRoom .table-side{height:300px!important;max-height:300px!important;margin-top:0}
  #pokerRoom .table-messages,#pokerRoom .hand-log{max-height:205px!important}
}
@media(max-width:1220px){
  #pokerRoom .poker-layout{grid-template-columns:minmax(0,1fr)!important}
  #pokerRoom .table-side{height:300px!important;max-height:300px!important}
}
@media(max-width:760px){
  #tablesView{overflow-x:clip!important}
  #pokerRoom{margin-left:0!important;margin-right:0!important}
  #pokerRoom .room-head{padding-left:10px!important;padding-right:10px!important}
  #pokerRoom .poker-zone{padding:6px!important;border-radius:0!important}
  #pokerTable{height:var(--jj-stage-h,500px)!important;border-radius:10px!important}
  #pokerTable:before{left:1.5%!important;right:1.5%!important;top:9%!important;bottom:9%!important;border-width:8px!important;outline-width:1px!important;outline-offset:-4px!important}
  #pokerTable .felt-center{top:41%!important;width:76%!important;max-width:76%!important}
  #pokerRoom .table-side{display:none!important}
  #pokerRoom .jj-seat{max-width:102px}
  #pokerRoom .jj-bet-marker{padding:4px 7px!important}
  #pokerRoom .jj-raise-editor{grid-template-columns:minmax(80px,1fr) 76px!important}
  #pokerRoom .action-bar{left:0!important;right:0!important;max-width:100vw!important}
}
@media(max-width:420px){
  #pokerTable:before{left:.5%!important;right:.5%!important;top:10%!important;bottom:10%!important}
  #pokerRoom .jj-seat{width:92px!important}
  #pokerRoom .jj-seat-box{padding:5px 6px!important}
  #pokerRoom .jj-bet-marker b{font-size:.66rem!important}
}
'''
    p.write_text(s, encoding='utf-8')


def _index(p: Path) -> None:
    s = p.read_text(encoding='utf-8').replace('?v=26', '?v=27')
    p.write_text(s, encoding='utf-8')


def _sw(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    s = re.sub(r'jj-arena-live-v\d+', 'jj-arena-live-v27', s)
    p.write_text(s, encoding='utf-8')
