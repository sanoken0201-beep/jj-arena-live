from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from build_served_assets import main as build_assets
from served_assets import BUILD_ROOT


FIXTURE = r'''<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<link rel="stylesheet" href="styles.css">
<style>
html,body{margin:0;background:#07100d}.fixture{max-width:1280px;margin:0 auto;padding:12px}.poker-zone{position:relative}.fixture #pokerTable{height:590px!important}.fixture #seatLayer{position:absolute;inset:0}.fixture .jj-seat.is-hero{left:50%;top:83%}.fixture #actionBar{display:block!important}.fixture .board{display:flex;justify-content:center}.fixture .felt-center{position:absolute;left:50%;top:45%;transform:translate(-50%,-50%)}
</style>
</head>
<body>
<div class="fixture">
  <div id="pokerRoom" class="jj-focus-hand-live jj-focus-seated jj-focus-can-act">
    <div class="room-head"><button id="backLobby">← ロビー</button><div><div class="eyebrow">LIVE TABLE</div><h3 id="roomTitle">JJ Table A</h3></div><div id="roomMeta">6-max · 0.5/1bb · 150bb<span class="jj-connection-status">リアルタイム接続</span></div></div>
    <div class="poker-zone card">
      <div id="pokerTable" class="poker-table">
        <div class="felt-center"><div id="boardCards" class="cards board"><span class="card-face jj-four-suit suit-spade">A♠</span><span class="card-face jj-four-suit suit-heart">10♥</span><span class="card-face jj-four-suit suit-club">7♣</span></div><div id="potDisplay" class="pot-display">Pot 8.5bb</div><div id="handStatus" class="hand-status">FLOP · YOUR TURN · 28s</div></div>
        <div id="seatLayer"><div class="seat jj-seat is-hero"><div class="hole jj-hole"><span class="card-face">A♣</span><span class="card-face">K♦</span></div><div class="seat-box jj-seat-box"><div class="name">YOU</div><div class="stack">142bb</div></div></div></div>
        <div id="jjHeroHandDock" class="jj-hero-hand-dock"><div class="jj-hero-hand-cards"><span class="card-face jj-four-suit suit-club">A♣</span><span class="card-face jj-four-suit suit-diamond">K♦</span></div><span>YOU</span></div>
      </div>
      <div id="tableControls" class="table-controls"><button>一時離席</button></div>
      <div id="actionBar" class="action-bar">
        <div id="jjV123ActionStatus">あなたの番です</div>
        <div id="jjV123DisabledHints">補助説明</div>
        <div class="jj-v124-decision-meta"><div>STREET</div><div>POT</div><div>TO CALL</div></div>
        <div class="jj-v5-preactions"><button>チェックのみ</button><button>チェック / フォールド</button></div>
        <div class="jj-v124-sizing"><div class="jj-v124-stepper"><label><input id="raiseTo" value="6"><span>BB</span></label></div></div>
        <div class="jj-main-actions"><button type="button" class="jj-action-btn jj-fold" data-action="fold">フォールド</button><button type="button" class="jj-action-btn jj-call" data-action="call">コール 3bb</button><button type="button" class="jj-action-btn jj-raise" data-action="raise">レイズ</button></div>
      </div>
    </div>
  </div>
</div>
<script>
function intersects(a,b){return !(a.right<=b.left||a.left>=b.right||a.bottom<=b.top||a.top>=b.bottom)}
function check(){
  const mobile=new URLSearchParams(location.search).get('mobile')==='1';
  if(mobile){document.body.classList.add('jj-mobile-table-open','jj-mobile-poker-can-act');}
  const table=document.getElementById('pokerTable');
  const dock=document.getElementById('jjHeroHandDock');
  const board=document.getElementById('boardCards');
  const seatHole=document.querySelector('.jj-seat.is-hero .jj-hole');
  const pre=document.querySelector('.jj-v5-preactions');
  const meta=document.querySelector('.jj-v124-decision-meta');
  const status=document.getElementById('jjV123ActionStatus');
  const controls=document.getElementById('tableControls');
  const buttons=[...document.querySelectorAll('#actionBar .jj-action-btn')];
  const tr=table.getBoundingClientRect(),dr=dock.getBoundingClientRect(),br=board.getBoundingClientRect();
  const checks={
    heroDockVisible:dr.width>70&&dr.height>45&&getComputedStyle(dock).visibility!=='hidden'&&getComputedStyle(dock).display!=='none',
    heroDockInsideFelt:dr.left>=tr.left-1&&dr.right<=tr.right+1&&dr.top>=tr.top-1&&dr.bottom<=tr.bottom+1,
    heroDockClearOfBoard:!intersects(dr,br),
    oldHeroHoleHidden:getComputedStyle(seatHole).display==='none',
    preactionsHidden:getComputedStyle(pre).display==='none',
    decisionMetaHidden:getComputedStyle(meta).display==='none',
    actionStatusHidden:getComputedStyle(status).display==='none',
    controlsHiddenWhileActing:getComputedStyle(controls).display==='none',
    actionButtonsInteractive:buttons.length===3&&buttons.every(b=>getComputedStyle(b).pointerEvents==='auto'&&b.getBoundingClientRect().height>=44),
  };
  const ok=Object.values(checks).every(Boolean);
  document.body.insertAdjacentHTML('beforeend',`<pre id="focusResult" data-focus-ok="${ok?'1':'0'}">${JSON.stringify(checks)}</pre>`);
}
addEventListener('load',()=>requestAnimationFrame(check));
</script>
</body></html>'''


def _chrome() -> str:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    raise AssertionError("Chrome/Chromium is required for poker focus layout regression")


def _run(chrome: str, fixture: Path, width: int, height: int, mobile: bool) -> str:
    url = fixture.resolve().as_uri() + ("?mobile=1" if mobile else "")
    proc = subprocess.run(
        [
            chrome,
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--allow-file-access-from-files",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=2500",
            f"--window-size={width},{height}",
            "--dump-dom",
            url,
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )
    return proc.stdout


def main() -> None:
    build_assets()
    chrome = _chrome()
    with tempfile.TemporaryDirectory(prefix="jj-poker-focus-layout-") as directory:
        root = Path(directory)
        shutil.copy2(BUILD_ROOT / "static/styles.css", root / "styles.css")
        fixture = root / "focus.html"
        fixture.write_text(FIXTURE, encoding="utf-8")
        desktop = _run(chrome, fixture, 1440, 900, False)
        mobile = _run(chrome, fixture, 390, 844, True)
        assert 'data-focus-ok="1"' in desktop, desktop[-1800:]
        assert 'data-focus-ok="1"' in mobile, mobile[-1800:]
    print("JJ_POKER_TABLE_FOCUS_LAYOUT_OK")


if __name__ == "__main__":
    main()
