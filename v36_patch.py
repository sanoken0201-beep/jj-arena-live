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
    s = s.replace('version="1.18.3"', 'version="1.18.4"').replace('"version":"1.18.3"', '"version":"1.18.4"')
    s = s.replace('request.url.query == "v=35"', 'request.url.query == "v=36"')
    p.write_text(s, encoding='utf-8')


def _app(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    if 'v1.18.4 portrait-first table geometry' in s:
        return
    marker = '})();'
    pos = s.rfind(marker)
    if pos < 0:
        raise RuntimeError('v1.18.4 app closing marker missing')
    addon = r'''

  // v1.18.4 portrait-first table geometry.
  // Mobile poker apps commonly keep the hero at the bottom, arrange opponents
  // around a tall oval, place the board/pot in the visual center, and reserve
  // the thumb zone at the bottom for betting controls. Only portrait phones use
  // these coordinates; desktop and landscape retain the existing layout.
  const jjPortraitPokerMq=window.matchMedia('(max-width:760px) and (orientation:portrait)');
  const jjV184SeatPos=jjSeatPos;
  jjSeatPos=function(actual){
    if(!jjPortraitPokerMq.matches)return jjV184SeatPos(actual);
    const coords=[
      {left:50,top:82},
      {left:13,top:64},
      {left:18,top:31},
      {left:50,top:15},
      {left:82,top:31},
      {left:87,top:64},
    ];
    return coords[jjVisualIndex(actual)]||coords[0];
  };
  jjBetPos=function(actual){
    if(!jjPortraitPokerMq.matches){
      const p=jjSeatPos(actual);
      return {left:50+(p.left-50)*.58,top:48+(p.top-48)*.57};
    }
    const p=jjSeatPos(actual);
    return {left:50+(p.left-50)*.53,top:46+(p.top-46)*.53};
  };
  jjPortraitPokerMq.addEventListener?.('change',()=>{
    if(currentTableId&&tableState){renderPokerRoom();requestAnimationFrame(()=>{try{jjFitPokerWorkspace()}catch{}})}
  });
'''
    s = s[:pos] + addon + s[pos:]
    p.write_text(s, encoding='utf-8')


def _styles(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    if 'v1.18.4 portrait poker table' in s:
        return
    s += r'''

/* v1.18.4 portrait poker table — modeled on established one-hand mobile poker
   patterns: tall oval felt, hero anchored at 6 o'clock, board/pot in the middle,
   and a stable bottom thumb zone for actions. Landscape and desktop are untouched. */
@media (max-width:760px) and (orientation:portrait){
  body.jj-mobile-table-open #pokerRoom .room-head{
    flex-basis:calc(46px + env(safe-area-inset-top))!important;
    height:calc(46px + env(safe-area-inset-top))!important;
    padding:env(safe-area-inset-top) 9px 0!important;
    gap:8px!important;
  }
  body.jj-mobile-table-open #backLobby{min-height:34px!important;height:34px!important;padding:0 10px!important}
  body.jj-mobile-table-open #roomTitle{font-size:.82rem!important}
  body.jj-mobile-table-open #roomMeta{font-size:.61rem!important}

  /* Keep the outer stage dark and let the felt read as an unmistakably vertical
     poker table rather than a landscape table squeezed into a phone. */
  body.jj-mobile-table-open #pokerRoom .poker-zone{padding:0!important;background:linear-gradient(180deg,#07100d 0%,#040907 100%)!important}
  body.jj-mobile-table-open #pokerTable{
    height:calc(100dvh - 46px - env(safe-area-inset-top) - 108px)!important;
    min-height:470px!important;
    width:100%!important;
    margin:0!important;
    border-radius:0!important;
    background:radial-gradient(ellipse at 50% 43%,rgba(19,48,37,.42),rgba(5,12,9,0) 58%),#050b09!important;
  }
  body.jj-mobile-table-open.jj-mobile-poker-hand #pokerTable{
    height:calc(100dvh - 46px - env(safe-area-inset-top) - 184px)!important;
    min-height:430px!important;
  }
  body.jj-mobile-table-open.jj-mobile-poker-observer #pokerTable{
    height:calc(100dvh - 46px - env(safe-area-inset-top))!important;
    min-height:500px!important;
  }

  /* The felt itself is a tall ellipse. The surrounding dark gutter gives side
     seats room without flattening the table. */
  body.jj-mobile-table-open #pokerTable:before{
    left:9%!important;
    right:9%!important;
    top:2.5%!important;
    bottom:4.5%!important;
    border-radius:48% / 37%!important;
    border-width:7px!important;
    outline-width:1px!important;
    outline-offset:-3px!important;
    box-shadow:0 16px 44px rgba(0,0,0,.34),inset 0 0 34px rgba(0,0,0,.16)!important;
  }
  body.jj-mobile-table-open #pokerTable:after{top:55%!important;font-size:1.1rem!important;opacity:.34!important}
  body.jj-mobile-table-open #pokerTable .felt-center{top:43%!important;width:70%!important;max-width:70%!important}

  /* Six-max portrait orbit: hero is visually dominant at the bottom, opponents
     remain compact at the sides/top, and no seat is placed over the board. */
  body.jj-mobile-table-open #pokerRoom .jj-seat{width:82px!important;max-width:82px!important}
  body.jj-mobile-table-open #pokerRoom .jj-seat-box{padding:4px 5px!important;border-radius:9px!important}
  body.jj-mobile-table-open #pokerRoom .jj-seat-box .name{max-width:70px!important;font-size:.57rem!important}
  body.jj-mobile-table-open #pokerRoom .jj-seat-box .stack{font-size:.64rem!important}
  body.jj-mobile-table-open #pokerRoom .jj-seat.is-hero{width:104px!important;max-width:104px!important}
  body.jj-mobile-table-open #pokerRoom .jj-seat.is-hero .jj-seat-box{padding:5px 7px!important;border-radius:10px!important}
  body.jj-mobile-table-open #pokerRoom .jj-seat.is-hero .jj-hole{top:-58px!important;gap:4px!important}
  body.jj-mobile-table-open #pokerRoom .jj-seat.is-hero .jj-hole .card-face{width:41px!important;height:57px!important;font-size:1rem!important}
  body.jj-mobile-table-open #pokerRoom .jj-hole{top:-35px!important}
  body.jj-mobile-table-open #pokerRoom .jj-hole .card-face{width:25px!important;height:35px!important;font-size:.64rem!important}
  body.jj-mobile-table-open #pokerRoom .dealer{transform:scale(.72)!important}
  body.jj-mobile-table-open #pokerRoom .jj-bet-marker{padding:3px 6px!important}
  body.jj-mobile-table-open #pokerRoom .jj-bet-marker b{font-size:.65rem!important}

  /* Central information is deliberately sparse and high-contrast, following the
     common portrait pattern where board + pot form one visual cluster. */
  body.jj-mobile-table-open .jj-board-card{width:39px!important;height:54px!important;font-size:.96rem!important}
  body.jj-mobile-table-open .cards.board{gap:3px!important;justify-content:center!important}
  body.jj-mobile-table-open .pot-display{margin-top:6px!important;padding:4px 9px!important;border-radius:999px!important}
  body.jj-mobile-table-open .pot-display span{font-size:.54rem!important}
  body.jj-mobile-table-open .pot-display b{font-size:.88rem!important}
  body.jj-mobile-table-open .hand-status{margin-top:4px!important}

  /* Stable thumb zone. The table no longer changes orientation when action is
     required; betting controls occupy a dedicated bottom sheet. */
  body.jj-mobile-table-open.jj-mobile-poker-can-act #actionBar{
    max-height:184px!important;
    min-height:154px!important;
    padding:7px 8px calc(9px + env(safe-area-inset-bottom))!important;
    border-radius:18px 18px 0 0!important;
    background:rgba(7,13,11,.99)!important;
    box-shadow:0 -10px 28px rgba(0,0,0,.42)!important;
  }
  body.jj-mobile-table-open #tableControls{height:54px!important;min-height:54px!important}

  /* Very short phones need compression, not a return to landscape geometry. */
  @media (max-height:700px){
    body.jj-mobile-table-open #pokerTable{min-height:390px!important}
    body.jj-mobile-table-open.jj-mobile-poker-hand #pokerTable{min-height:350px!important}
    body.jj-mobile-table-open #pokerRoom .jj-seat{width:76px!important;max-width:76px!important}
    body.jj-mobile-table-open #pokerRoom .jj-seat.is-hero{width:96px!important;max-width:96px!important}
    body.jj-mobile-table-open .jj-board-card{width:35px!important;height:49px!important}
  }
}
'''
    p.write_text(s, encoding='utf-8')


def _index(p: Path) -> None:
    s = p.read_text(encoding='utf-8').replace('?v=35', '?v=36')
    p.write_text(s, encoding='utf-8')


def _sw(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    s = re.sub(r'jj-arena-live-v\d+', 'jj-arena-live-v36', s)
    p.write_text(s, encoding='utf-8')
