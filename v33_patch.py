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
    s = s.replace('version="1.16.3"', 'version="1.17.0"').replace('"version":"1.16.3"', '"version":"1.17.0"')
    s = s.replace('request.url.query == "v=32"', 'request.url.query == "v=33"')
    p.write_text(s, encoding='utf-8')


def _app(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    if 'v1.17 mobile poker shell' in s:
        return
    marker = '})();'
    pos = s.rfind(marker)
    if pos < 0:
        raise RuntimeError('v1.17 app closing marker missing')
    addon = r'''

  // v1.17 mobile poker shell.
  // The general-purpose mobile navigation must not compete with poker controls.
  // A live table becomes an immersive surface with one compact table header,
  // one felt, and one action console.
  const jjMobilePokerMq=window.matchMedia('(max-width:760px)');

  function jjV17Hero(){return tableState?.seats?.find(p=>p.user_id===me?.id)||null}
  function jjV17SyncMobilePoker(){
    const mobile=jjMobilePokerMq.matches;
    const open=mobile&&!!currentTableId&&!!tableState;
    const hero=open?jjV17Hero():null;
    const canAct=!!(open&&hero&&tableState?.legal?.can_act);
    const playing=!!(open&&hero&&tableState?.status==='playing');
    const observer=!!(open&&!hero);
    document.body.classList.toggle('jj-mobile-table-open',open);
    document.body.classList.toggle('jj-mobile-poker-seated',!!hero&&open);
    document.body.classList.toggle('jj-mobile-poker-observer',observer);
    document.body.classList.toggle('jj-mobile-poker-can-act',canAct);
    document.body.classList.toggle('jj-mobile-poker-hand',playing);
    const zone=$('#pokerRoom .poker-zone');
    if(zone){
      zone.classList.toggle('jj-mobile-observer',observer);
      zone.classList.toggle('jj-mobile-can-act',canAct);
      zone.classList.toggle('jj-mobile-hand-live',playing);
    }
    const roomMeta=$('#roomMeta');
    if(open&&roomMeta){
      const active=(tableState.seats||[]).filter(p=>Number(p.stack)>0&&!p.sitting_out&&!p.sit_out_next).length;
      roomMeta.textContent=hero?`${bb(hero.stack)} · ${active}/6`:`観戦 · ${active}/6`;
    }
  }

  // Keep all six seats comfortably inside the phone felt. The previous top seat
  // was too close to the clipped edge on Safari.
  const jjV17DesktopSeatPos=jjSeatPos;
  jjSeatPos=function(actual){
    if(!jjMobilePokerMq.matches)return jjV17DesktopSeatPos(actual);
    const coords=[
      {left:50,top:80},{left:15,top:65},{left:16,top:28},
      {left:50,top:16},{left:84,top:28},{left:85,top:65}
    ];
    return coords[jjVisualIndex(actual)]||coords[0];
  };
  jjBetPos=function(actual){
    const p=jjSeatPos(actual);
    return {left:50+(p.left-50)*.58,top:48+(p.top-48)*.57};
  };

  const jjV17RenderPokerRoom=renderPokerRoom;
  renderPokerRoom=function(){
    jjV17RenderPokerRoom();
    jjV17SyncMobilePoker();
    // Observer seating has exactly one primary CTA on phones. The secondary
    // table-control duplicate is visually suppressed by the mobile shell CSS.
    const result=$('#resultBanner');
    if(result&&tableState?.last_result)result.setAttribute('role','status');
  };

  const jjV17OpenTable=openTable;
  openTable=async function(id){
    if(jjMobilePokerMq.matches)document.body.classList.add('jj-mobile-table-open');
    try{
      await jjV17OpenTable(id);
      jjV17SyncMobilePoker();
      if(jjMobilePokerMq.matches)window.scrollTo(0,0);
    }catch(err){
      document.body.classList.remove('jj-mobile-table-open','jj-mobile-poker-seated','jj-mobile-poker-observer','jj-mobile-poker-can-act','jj-mobile-poker-hand');
      throw err;
    }
  };

  const jjV17DisconnectTable=disconnectTable;
  disconnectTable=function(){
    jjV17DisconnectTable();
    document.body.classList.remove('jj-mobile-table-open','jj-mobile-poker-seated','jj-mobile-poker-observer','jj-mobile-poker-can-act','jj-mobile-poker-hand');
  };

  jjMobilePokerMq.addEventListener?.('change',()=>{jjV17SyncMobilePoker();requestAnimationFrame(()=>{try{jjFitPokerWorkspace()}catch{}})});
'''
    s = s[:pos] + addon + s[pos:]
    p.write_text(s, encoding='utf-8')


def _styles(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    if 'v1.17 immersive mobile poker' in s:
        return
    s += r'''

/* v1.17 immersive mobile poker — phone only. Desktop is intentionally untouched. */
@media(max-width:760px){
  /* A live poker table is a dedicated application surface, not another page
     behind the site's fixed navigation. */
  body.jj-mobile-table-open{overflow:hidden!important;background:#07100d!important}
  body.jj-mobile-table-open .topbar{display:none!important}
  body.jj-mobile-table-open #mobileDock{display:none!important}
  body.jj-mobile-table-open .main{height:100dvh!important;min-height:100dvh!important;padding:0!important;overflow:hidden!important;background:#07100d!important}
  body.jj-mobile-table-open #tablesView{height:100dvh!important;min-height:100dvh!important;overflow:hidden!important;margin:0!important}
  body.jj-mobile-table-open #pokerRoom{display:flex!important;flex-direction:column!important;height:100dvh!important;min-height:100dvh!important;margin:0!important;background:#07100d!important;color:#fff!important}

  /* Compact table-only header. The Lobby button is always reachable and
     replaces the global dock while playing. */
  body.jj-mobile-table-open #pokerRoom .room-head{display:grid!important;grid-template-columns:auto minmax(0,1fr) auto!important;align-items:center!important;gap:9px!important;flex:0 0 calc(50px + env(safe-area-inset-top))!important;height:calc(50px + env(safe-area-inset-top))!important;margin:0!important;padding:env(safe-area-inset-top) 10px 0!important;background:rgba(7,16,13,.98)!important;border-bottom:1px solid rgba(255,255,255,.08)!important;position:relative!important;z-index:110!important}
  body.jj-mobile-table-open #backLobby{min-height:36px!important;padding:0 11px!important;border-radius:10px!important;background:#17231f!important;border-color:#304139!important;color:#e5eee9!important;font-size:.72rem!important}
  body.jj-mobile-table-open #pokerRoom .room-head>div:nth-child(2){min-width:0!important}
  body.jj-mobile-table-open #pokerRoom .room-head .eyebrow{display:none!important}
  body.jj-mobile-table-open #roomTitle{margin:0!important;color:#f4f8f6!important;font-size:.86rem!important;white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important}
  body.jj-mobile-table-open #roomMeta{display:block!important;grid-column:auto!important;margin:0!important;color:#9eb1a8!important;font-size:.64rem!important;white-space:nowrap!important}

  body.jj-mobile-table-open #pokerRoom .poker-layout{display:block!important;flex:1 1 auto!important;height:auto!important;min-height:0!important;overflow:hidden!important}
  body.jj-mobile-table-open #pokerRoom .poker-zone{height:100%!important;min-height:0!important;margin:0!important;padding:5px 5px 0!important;border:0!important;border-radius:0!important;background:linear-gradient(180deg,#08110e,#050b09)!important;overflow:hidden!important}
  body.jj-mobile-table-open #pokerRoom .table-side{display:none!important}

  /* Stable felt geometry. Space is reserved for controls instead of allowing a
     fixed console to sit on top of the table. */
  body.jj-mobile-table-open #pokerTable{width:100%!important;height:calc(100dvh - 50px - env(safe-area-inset-top) - 116px)!important;min-height:390px!important;max-height:none!important;border-radius:12px!important;margin:0!important;overflow:hidden!important;background:radial-gradient(circle at 50% 43%,#101a16,#07100d 72%)!important}
  body.jj-mobile-table-open.jj-mobile-poker-hand #pokerTable{height:calc(100dvh - 50px - env(safe-area-inset-top) - 178px)!important}
  body.jj-mobile-table-open.jj-mobile-poker-observer #pokerTable{height:calc(100dvh - 50px - env(safe-area-inset-top) - 8px)!important}
  body.jj-mobile-table-open #pokerTable:before{left:1%!important;right:1%!important;top:6.5%!important;bottom:6.5%!important;border-width:7px!important;outline-width:1px!important;outline-offset:-3px!important}
  body.jj-mobile-table-open #pokerTable:after{top:57%!important;font-size:1.35rem!important}
  body.jj-mobile-table-open #pokerTable .felt-center{top:41%!important;width:78%!important;max-width:78%!important}

  /* Seats and cards prioritize the actual poker information. */
  body.jj-mobile-table-open #pokerRoom .jj-seat{width:88px!important;max-width:88px!important}
  body.jj-mobile-table-open #pokerRoom .jj-seat-box{padding:5px 6px!important;border-radius:9px!important;background:rgba(8,14,12,.94)!important;box-shadow:0 5px 14px rgba(0,0,0,.34)!important}
  body.jj-mobile-table-open #pokerRoom .jj-seat-box .name{font-size:.59rem!important;max-width:76px!important}
  body.jj-mobile-table-open #pokerRoom .jj-seat-box .stack{font-size:.65rem!important}
  body.jj-mobile-table-open #pokerRoom .jj-player-state{font-size:.45rem!important;margin-top:3px!important}
  body.jj-mobile-table-open #pokerRoom .jj-hole{top:-38px!important}
  body.jj-mobile-table-open #pokerRoom .jj-hole .card-face{width:27px!important;height:38px!important;font-size:.69rem!important}
  body.jj-mobile-table-open #pokerRoom .jj-seat.is-hero{width:102px!important;max-width:102px!important}
  body.jj-mobile-table-open #pokerRoom .jj-seat.is-hero .jj-hole{top:-57px!important;gap:4px!important}
  body.jj-mobile-table-open #pokerRoom .jj-seat.is-hero .jj-hole .card-face{width:40px!important;height:56px!important;font-size:1rem!important}
  body.jj-mobile-table-open #pokerRoom .dealer{transform:scale(.78)!important}
  body.jj-mobile-table-open #pokerRoom .jj-bet-marker{padding:4px 7px!important;gap:4px!important;border-width:1px!important;box-shadow:0 4px 12px rgba(0,0,0,.5)!important}
  body.jj-mobile-table-open #pokerRoom .jj-bet-marker b{font-size:.7rem!important}
  body.jj-mobile-table-open #pokerRoom .jj-bet-marker i{width:10px!important;height:10px!important}
  body.jj-mobile-table-open .jj-board-card{width:42px!important;height:58px!important;font-size:1rem!important}
  body.jj-mobile-table-open .cards.board{gap:4px!important}
  body.jj-mobile-table-open .pot-display{margin-top:7px!important;padding:5px 10px!important}
  body.jj-mobile-table-open .pot-display span{font-size:.57rem!important}
  body.jj-mobile-table-open .pot-display b{font-size:.92rem!important}
  body.jj-mobile-table-open .hand-status{margin-top:5px!important;gap:7px!important}.hand-status b{font-size:.62rem!important}.hand-status span{font-size:.67rem!important}

  /* Result is a short toast, never a modal that blocks the table. */
  body.jj-mobile-table-open #resultBanner.result-banner:not(.hidden){display:block!important;position:absolute!important;z-index:55!important;left:50%!important;right:auto!important;top:10px!important;bottom:auto!important;transform:translateX(-50%)!important;width:min(330px,calc(100% - 28px))!important;max-width:none!important;height:auto!important;min-height:0!important;max-height:54px!important;overflow:hidden!important;margin:0!important;padding:8px 12px!important;border-radius:12px!important;background:rgba(5,13,10,.94)!important;border:1px solid rgba(240,203,102,.52)!important;color:#fff0c4!important;font-size:.69rem!important;line-height:1.35!important;text-align:center!important;box-shadow:0 8px 20px rgba(0,0,0,.34)!important;pointer-events:none!important}

  /* Observer has one join control: the in-table CTA. The duplicate control row
     below the felt is suppressed. */
  body.jj-mobile-table-open.jj-mobile-poker-observer #tableControls{display:none!important}
  body.jj-mobile-table-open #pokerRoom .jj-observer-join{left:50%!important;right:auto!important;bottom:12px!important;transform:translateX(-50%)!important;min-width:0!important;width:min(310px,calc(100% - 34px))!important;max-width:310px!important;padding:8px 9px 8px 12px!important;border-radius:13px!important;gap:8px!important;background:rgba(5,15,11,.94)!important;box-shadow:0 8px 20px rgba(0,0,0,.36)!important}
  body.jj-mobile-table-open #pokerRoom .jj-observer-join b{font-size:.61rem!important}body.jj-mobile-table-open #pokerRoom .jj-observer-join span{font-size:.56rem!important}
  body.jj-mobile-table-open #pokerRoom .jj-observer-join button{min-height:38px!important;padding:0 12px!important;font-size:.7rem!important;white-space:nowrap!important}
  body.jj-mobile-table-open #pokerRoom .jj-empty-seat{width:58px!important;height:36px!important;font-size:.85rem!important}
  body.jj-mobile-table-open #pokerRoom .jj-empty-seat:after{font-size:.55rem!important}

  /* Presence controls remain reachable but compact. During the user's actual
     decision they disappear, because betting controls have priority; they return
     immediately after the action. */
  body.jj-mobile-table-open #tableControls{height:54px!important;min-height:54px!important;padding:6px 7px!important;margin:0!important;background:#09120f!important;border-top:1px solid rgba(255,255,255,.06)!important;overflow:hidden!important}
  body.jj-mobile-table-open.jj-mobile-poker-can-act #tableControls{display:none!important}
  body.jj-mobile-table-open #tableControls .jj-ready-count{display:none!important}
  body.jj-mobile-table-open #tableControls button{min-height:38px!important;max-height:38px!important;padding:0 10px!important;font-size:.67rem!important;border-radius:10px!important}

  /* Betting console: no duplicate hole cards, no site dock, no excessive dead
     space. It owns the bottom of the viewport only when the hero can act. */
  body.jj-mobile-table-open #actionBar{display:none!important}
  body.jj-mobile-table-open.jj-mobile-poker-can-act #actionBar{display:block!important;position:fixed!important;z-index:120!important;left:0!important;right:0!important;bottom:0!important;max-height:178px!important;overflow:hidden!important;margin:0!important;padding:7px 8px calc(8px + env(safe-area-inset-bottom))!important;border-radius:16px 16px 0 0!important;border:1px solid rgba(255,255,255,.09)!important;border-bottom:0!important;background:rgba(9,15,13,.985)!important;box-shadow:0 -8px 24px rgba(0,0,0,.35)!important;backdrop-filter:blur(14px)!important;-webkit-backdrop-filter:blur(14px)!important}
  body.jj-mobile-table-open .jj-action-context{min-height:25px!important;height:25px!important;margin:0 0 5px!important;padding:0 2px!important}
  body.jj-mobile-table-open .jj-action-context .jj-hero-cards{display:none!important}
  body.jj-mobile-table-open .jj-action-context>div:last-child{display:flex!important;flex-direction:row!important;align-items:center!important;justify-content:space-between!important;width:100%!important;gap:8px!important}
  body.jj-mobile-table-open .jj-action-context span{font-size:.6rem!important}body.jj-mobile-table-open .jj-action-context b{font-size:.72rem!important}
  body.jj-mobile-table-open .jj-sizing{display:grid!important;grid-template-columns:auto minmax(0,1fr)!important;align-items:center!important;gap:6px!important;margin:0 0 6px!important}
  body.jj-mobile-table-open .jj-size-row{display:flex!important;gap:5px!important;overflow:visible!important;padding:0!important}
  body.jj-mobile-table-open .jj-size-btn{min-height:34px!important;height:34px!important;padding:0 10px!important;border-radius:8px!important;font-size:.67rem!important}
  body.jj-mobile-table-open .jj-raise-editor{grid-template-columns:minmax(78px,1fr) 68px!important;gap:5px!important}
  body.jj-mobile-table-open .jj-raise-editor input[type=range]{height:25px!important;min-height:25px!important}
  body.jj-mobile-table-open .jj-raise-editor label{height:34px!important;min-height:34px!important}
  body.jj-mobile-table-open .jj-raise-editor input[type=number]{width:45px!important;min-height:32px!important;height:32px!important;padding:0 2px!important;font-size:16px!important}
  body.jj-mobile-table-open .jj-raise-editor>b{display:none!important}
  body.jj-mobile-table-open .jj-main-actions{grid-template-columns:repeat(4,minmax(0,1fr))!important;gap:5px!important}
  body.jj-mobile-table-open .jj-action-btn{min-height:52px!important;height:52px!important;border-radius:10px!important}
  body.jj-mobile-table-open .jj-action-btn small{font-size:.47rem!important}body.jj-mobile-table-open .jj-action-btn b{font-size:.72rem!important}

  /* Never let Safari's layout or a long label create horizontal scroll. */
  body.jj-mobile-table-open #pokerRoom,body.jj-mobile-table-open #pokerRoom *{max-width:100vw}
}

@media(max-width:390px){
  body.jj-mobile-table-open #pokerRoom .jj-seat{width:82px!important;max-width:82px!important}
  body.jj-mobile-table-open #pokerRoom .jj-seat.is-hero{width:96px!important;max-width:96px!important}
  body.jj-mobile-table-open .jj-size-btn{padding:0 8px!important;font-size:.63rem!important}
  body.jj-mobile-table-open .jj-action-btn b{font-size:.67rem!important}
  body.jj-mobile-table-open .jj-board-card{width:39px!important;height:54px!important}
}
'''
    p.write_text(s, encoding='utf-8')


def _index(p: Path) -> None:
    s = p.read_text(encoding='utf-8').replace('?v=32', '?v=33')
    p.write_text(s, encoding='utf-8')


def _sw(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    s = re.sub(r'jj-arena-live-v\d+', 'jj-arena-live-v33', s)
    p.write_text(s, encoding='utf-8')
