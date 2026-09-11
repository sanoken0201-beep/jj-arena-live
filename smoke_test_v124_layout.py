from __future__ import annotations

import html
import shutil
import subprocess
import tempfile
from pathlib import Path

from runtime_builder import build_runtime


FIXTURE = r'''<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<link rel="stylesheet" href="styles.css">
<style>
html,body{margin:0;background:#07100d}.fixture{width:100%;max-width:1400px;margin:0 auto}.poker-zone{position:relative}.fixture #pokerTable{height:610px!important}.fixture #seatLayer{position:absolute;inset:0}.fixture .jj-seat{left:50%;top:83%}.fixture .jj-bet-marker{left:61%;top:68%}.fixture #actionBar{position:relative!important;left:auto!important;right:auto!important;bottom:auto!important;display:block!important}.fixture-mobile #actionBar{position:fixed!important;left:0!important;right:0!important;bottom:0!important}.fixture-mobile #pokerTable{height:560px!important}.fixture-mobile .jj-seat{left:50%;top:82%}.fixture-mobile .jj-bet-marker{left:50%;top:56.5%}
</style>
</head>
<body>
<div id="fixture" class="fixture">
  <div id="pokerRoom">
    <div class="room-head"><button>ロビー</button><div><h3>JJ TABLE A</h3></div><div id="roomMeta">150bb · 2/6</div></div>
    <div class="poker-zone">
      <div id="pokerTable">
        <div class="felt-center"><div class="cards board"><span class="card-face jj-four-suit suit-spade"><span class="jj-card-rank">A</span><span class="jj-card-suit">♠</span></span><span class="card-face jj-four-suit suit-heart"><span class="jj-card-rank">10</span><span class="jj-card-suit">♥</span></span></div></div>
        <div id="seatLayer"><div class="jj-seat is-hero"><div class="jj-hole"><span class="card-face jj-four-suit suit-club"><span class="jj-card-rank" id="rankQ">Q</span><span class="jj-card-suit">♣</span></span><span class="card-face jj-four-suit suit-heart"><span class="jj-card-rank">9</span><span class="jj-card-suit">♥</span></span></div><div class="jj-seat-box"><div class="name">YOU</div><div class="stack">150bb</div></div></div></div>
        <div class="jj-bet-marker" id="heroBet"><i></i><b>0.5bb</b></div>
      </div>
      <div class="table-controls"><div class="jj-table-control-left"><span class="jj-ready-count">次ハンド参加予定 2/6</span></div><div class="jj-table-control-right"><button>一時離席</button></div></div>
      <div id="actionBar" class="action-bar">
        <div class="jj-v123-action-status is-turn">あなたの番です</div>
        <div class="jj-v124-decision-meta"><div><span>STREET</span><strong>PREFLOP</strong></div><div><span>POT</span><strong>1.5bb</strong></div><div><span>TO CALL</span><strong id="jjV124CallAmount">0.5bb</strong></div><div><span>STACK</span><strong>150bb</strong></div><div><span>EFFECTIVE</span><strong>149bb</strong></div><div class="jj-v124-time"><span>TIME</span><strong id="jjActionClock" class="jj-action-clock">18秒</strong></div></div>
        <div class="jj-sizing jj-v124-sizing"><div class="jj-size-row"><button class="jj-size-btn">2.5x</button><button class="jj-size-btn">3x</button><button class="jj-size-btn">4x</button><button class="jj-size-btn jj-allin-size">ALL-IN</button></div><div class="jj-raise-editor jj-v124-raise-editor"><input id="raiseSlider" type="range" min="2" max="150" value="2"><div class="jj-v124-stepper"><button>−</button><label><input id="raiseTo" type="number" value="2"><span id="bbUnit">BB</span></label><button>＋</button></div></div></div>
        <div class="jj-main-actions jj-actions-3"><button class="jj-action-btn jj-fold"><small>FOLD</small><b>フォールド</b></button><button class="jj-action-btn jj-call"><small>CALL</small><b id="callText">コール 0.5bb</b></button><button class="jj-action-btn jj-raise"><small>RAISE</small><b>レイズ 2bb</b></button></div>
      </div>
    </div>
  </div>
</div>
<script>
function intersects(a,b){return !(a.right<=b.left||a.left>=b.right||a.bottom<=b.top||a.top>=b.bottom)}
function check(){
  const mobile=new URLSearchParams(location.search).get('mobile')==='1';
  document.body.classList.toggle('jj-mobile-table-open',mobile);
  document.body.classList.toggle('jj-mobile-poker-can-act',mobile);
  document.body.classList.toggle('jj-v124-desktop-poker',!mobile);
  document.getElementById('fixture').classList.toggle('fixture-mobile',mobile);
  requestAnimationFrame(()=>requestAnimationFrame(()=>{
    const action=document.getElementById('actionBar'),cards=document.querySelector('.jj-seat.is-hero .jj-hole'),bet=document.getElementById('heroBet'),rank=document.getElementById('rankQ'),unit=document.getElementById('bbUnit'),call=document.getElementById('callText');
    const buttons=[...document.querySelectorAll('.jj-main-actions .jj-action-btn')];
    const widths=buttons.map(x=>x.getBoundingClientRect().width);
    const maxW=Math.max(...widths),minW=Math.min(...widths);
    const cardRect=cards.getBoundingClientRect(),betRect=bet.getBoundingClientRect(),rankRect=rank.getBoundingClientRect(),unitRect=unit.getBoundingClientRect(),actionRect=action.getBoundingClientRect();
    const unitStyle=getComputedStyle(unit),callStyle=getComputedStyle(call);
    const checks={
      actionNoHorizontalOverflow:action.scrollWidth<=action.clientWidth+2,
      equalPrimaryActions:maxW-minW<3,
      cardBetSeparated:mobile?true:!intersects(cardRect,betRect),
      rankVisible:rankRect.width>8&&rankRect.height>8&&rankRect.left>=cardRect.left-1&&rankRect.right<=cardRect.right+1,
      bbHorizontal:unitStyle.writingMode==='horizontal-tb'&&unitRect.width>8&&unitRect.height<30,
      callReadable:parseFloat(callStyle.fontSize)>=12,
      actionWithinViewport:actionRect.left>=-1&&actionRect.right<=innerWidth+1,
      threeActions:buttons.length===3,
    };
    const ok=Object.values(checks).every(Boolean);
    document.body.insertAdjacentHTML('beforeend',`<pre id="layoutResult" data-layout-ok="${ok?'1':'0'}">${JSON.stringify(checks)}</pre>`);
  }));
}
addEventListener('load',check);
</script>
</body></html>'''


def _chrome() -> str:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    raise AssertionError("Chrome/Chromium is required for v1.24 layout regression")


def _run(chrome: str, fixture: Path, width: int, height: int, mobile: bool) -> str:
    url = fixture.resolve().as_uri() + ("?mobile=1" if mobile else "")
    last = ""
    for _ in range(2):
        proc = subprocess.run(
            [chrome, "--headless", "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files", "--run-all-compositor-stages-before-draw", "--virtual-time-budget=3000", f"--window-size={width},{height}", "--dump-dom", url],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        last = proc.stdout
        if 'data-layout-ok=' in last:
            return last
    return last


def main() -> None:
    chrome = _chrome()
    with tempfile.TemporaryDirectory() as td:
        root = build_runtime(Path(td) / "runtime")
        fixture = root / "static" / "v124-layout-fixture.html"
        fixture.write_text(FIXTURE, encoding="utf-8")
        desktop = _run(chrome, fixture, 1440, 900, False)
        mobile = _run(chrome, fixture, 390, 844, True)
        assert 'data-layout-ok="1"' in desktop, desktop[-1500:]
        assert 'data-layout-ok="1"' in mobile, mobile[-1500:]
    print("v1.24 real-browser layout regression: ok")


if __name__ == "__main__":
    main()
