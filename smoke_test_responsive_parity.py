from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from served_assets import build_styles


ROOT = Path(__file__).resolve().parent


MAIN_FIXTURE = r'''<!doctype html>
<html lang="ja"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<link rel="stylesheet" href="styles.css">
</head><body>
<nav id="dock" class="mobile-only mobile-dock"><button><b>⌂</b><span>ホーム</span></button><button><b>♠</b><span>卓</span></button></nav>
<div id="banner" class="jj-update-banner"><span><strong>新しいバージョンがあります</strong><small>ハンド中でない時に更新してください。</small></span><button>更新する</button></div>
<script>
function intersects(a,b){return !(a.right<=b.left||a.left>=b.right||a.bottom<=b.top||a.top>=b.bottom)}
addEventListener('load',()=>setTimeout(()=>{
  const mobile=matchMedia('(max-width:760px)').matches;
  const banner=document.getElementById('banner'),dock=document.getElementById('dock');
  const br=banner.getBoundingClientRect(),dr=dock.getBoundingClientRect(),ds=getComputedStyle(dock);
  const checks={
    mobileBreakpoint: mobile ? ds.display!=='none' : ds.display==='none',
    bannerInViewport: br.left>=-1&&br.right<=innerWidth+1&&br.top>=-1&&br.bottom<=innerHeight+1,
    bannerClearOfDock: !mobile || !intersects(br,dr),
    mobileUpdateTouch: !mobile || banner.querySelector('button').getBoundingClientRect().height>=44,
    noHorizontalOverflow: document.documentElement.scrollWidth<=innerWidth+2
  };
  document.body.insertAdjacentHTML('beforeend',`<pre data-main-ok="${Object.values(checks).every(Boolean)?'1':'0'}">${JSON.stringify(checks)}</pre>`);
},80));
</script></body></html>'''


ADMIN_FIXTURE = r'''<!doctype html>
<html lang="ja"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<link rel="stylesheet" href="admin.css">
</head><body>
<div class="shell"><aside class="sidebar"><nav class="side-nav"><button class="nav active"><span>⌂</span>概要</button></nav></aside>
<main class="main">
<header id="topbar" class="topbar"><div><div class="eyebrow">OPERATIONS</div><h1>管理概要</h1></div><div class="admin-chip"><small>ADMIN</small><strong>TEST</strong></div></header>
<nav class="mobile-nav"><button class="active">概要</button><button>Sit&Go</button></nav>
<section class="panel">
  <div class="sng-structure-head"><div><b>ブラインド構成</b><small>既存設定</small></div><button id="structureButton">レベル追加</button></div>
  <div class="sng-level-editor">
    <div class="sng-level-row"><strong>1</strong>
      <label><span>SB</span><input value="100"></label>
      <label><span>BB</span><input value="200"></label>
      <label><span>BBA</span><input value="200"></label>
      <label><span>Hands</span><input value="12"></label>
      <button id="removeButton" class="sng-remove-level">×</button>
    </div>
  </div>
  <div class="sng-event-actions"><button id="eventButton">大会を開始</button><button>編集</button></div>
</section>
<div id="toast" class="toast show">保存しました</div>
</main></div>
<script>
addEventListener('load',()=>setTimeout(()=>{
  const mobile=matchMedia('(max-width:760px)').matches;
  const top=document.getElementById('topbar').getBoundingClientRect();
  const remove=document.getElementById('removeButton').getBoundingClientRect();
  const structure=document.getElementById('structureButton').getBoundingClientRect();
  const eventButton=document.getElementById('eventButton').getBoundingClientRect();
  const checks={
    noHorizontalOverflow: document.documentElement.scrollWidth<=innerWidth+2,
    topbarUsable: top.height>=70&&top.left>=-1&&top.right<=innerWidth+1,
    mobileStructureTouch: !mobile || structure.height>=44,
    mobileEventTouch: !mobile || eventButton.height>=44,
    mobileRemoveTouch: !mobile || (remove.width>=44&&remove.height>=44),
    mobileInputZoomSafe: !mobile || parseFloat(getComputedStyle(document.querySelector('.sng-level-row input')).fontSize)>=16
  };
  document.body.insertAdjacentHTML('beforeend',`<pre data-admin-ok="${Object.values(checks).every(Boolean)?'1':'0'}">${JSON.stringify(checks)}</pre>`);
},80));
</script></body></html>'''


POKER_FIXTURE = r'''<!doctype html>
<html lang="ja"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<link rel="stylesheet" href="styles.css">
</head><body class="jj-poker-simple jj-mobile-table-open jj-mobile-poker-seated jj-mobile-poker-hand">
<div id="pokerRoom">
  <div class="room-head"><button id="backLobby">← ロビー</button><h3>JJ Table A</h3><details class="jj-v7-menu"><summary>メニュー</summary></details></div>
  <div class="poker-layout"><div class="poker-zone card">
    <div id="pokerTable" class="poker-table">
      <div class="felt-center">
        <div id="boardCards" class="cards board">
          <span class="card-face">6♥</span><span class="card-face">Q♠</span><span class="card-face">4♣</span><span class="card-face">K♠</span><span class="card-face">2♣</span>
        </div>
        <div class="pot-display">POT 9bb</div>
      </div>
      <div id="seatLayer">
        <div class="seat jj-seat" data-jj-visual="1" style="left:16%;top:68%"><div class="seat-box"><div class="jj-hole"><span class="card-face">A♠</span><span class="card-face">J♠</span></div><div class="name">LEFT</div><div class="stack">100bb</div></div></div>
        <div class="seat jj-seat" data-jj-visual="3" style="left:50%;top:12%"><div class="seat-box"><div class="jj-hole"><span class="card-face">Q♣</span><span class="card-face">4♣</span></div><div class="name">TOP</div><div class="stack">250bb</div></div></div>
        <div class="seat jj-seat" data-jj-visual="4" style="left:83%;top:22%"><div class="seat-box"><div class="jj-hole"><span class="card-face">K♦</span><span class="card-face">9♦</span></div><div class="name">UPPER RIGHT</div><div class="stack">276.6bb</div></div></div>
        <div class="seat jj-seat" data-jj-visual="5" style="left:84%;top:68%"><div class="seat-box"><div class="jj-hole"><span class="card-face">7♣</span><span class="card-face">7♥</span></div><div class="name">LOWER RIGHT</div><div class="stack">180bb</div></div></div>
        <div class="seat jj-seat is-hero" data-jj-visual="0" style="left:50%;top:84%"><div class="seat-box"><div class="name">YOU</div><div class="stack">154.5bb</div></div></div>
      </div>
    </div>
    <div id="resultBanner" class="result-banner">ヨシハル +9bb (One Pair) · rake 1bb</div>
    <div id="tableControls" class="table-controls"><button>一時離席する</button><button>今すぐ退席</button></div>
    <div id="actionBar" class="action-bar"><div class="jj-v7-hero-strip">
      <div class="jj-v7-hand"><span class="card-face">K♣</span><span class="card-face">A♣</span></div>
      <div class="jj-v7-stack"><span>持ち点</span><strong>154.5bb</strong></div>
      <div class="jj-v7-timebank"><span>TIME BANK</span><strong>×3</strong></div>
      <strong class="jj-action-clock"></strong>
    </div></div>
  </div></div>
</div>
<script>
function intersects(a,b){return !(a.right<=b.left||a.left>=b.right||a.bottom<=b.top||a.top>=b.bottom)}
addEventListener('load',()=>setTimeout(()=>{
  const table=document.getElementById('pokerTable').getBoundingClientRect();
  const result=document.getElementById('resultBanner').getBoundingClientRect();
  const bar=document.getElementById('actionBar').getBoundingClientRect();
  const hand=document.querySelector('.jj-v7-hand').getBoundingClientRect();
  const board=[...document.querySelectorAll('#boardCards .card-face')].map(x=>x.getBoundingClientRect());
  const topHole=document.querySelector('[data-jj-visual="3"] .jj-hole').getBoundingClientRect();
  const sideHole=document.querySelector('[data-jj-visual="1"] .jj-hole').getBoundingClientRect();
  const opponentSeats=[...document.querySelectorAll('.jj-seat:not(.is-hero)')];
  const opponentCardsClearOwnPlaques=opponentSeats.every(seat=>!intersects(seat.querySelector('.jj-hole').getBoundingClientRect(),seat.querySelector('.seat-box').getBoundingClientRect()));
  const boardBox=document.getElementById('boardCards').getBoundingClientRect();
  const noBoardOverlap=board.every((a,i)=>board.every((b,j)=>i===j||!intersects(a,b)));
  const checks={
    noHorizontalOverflow:document.documentElement.scrollWidth<=innerWidth+2,
    resultClearOfTable:!intersects(result,table),
    compactWaitingBar:bar.height>=60&&bar.height<=148,
    heroHandVisible:hand.left>=0&&hand.right<=innerWidth,
    boardInsideViewport:boardBox.left>=0&&boardBox.right<=innerWidth,
    noBoardCardOverlap:noBoardOverlap,
    topHoleClearOfBoard:!intersects(topHole,boardBox),
    sideHoleClearOfBoard:!intersects(sideHole,boardBox),
    opponentCardsClearOwnPlaques
  };
  const metric=r=>({left:Math.round(r.left),top:Math.round(r.top),right:Math.round(r.right),bottom:Math.round(r.bottom),width:Math.round(r.width),height:Math.round(r.height)});
  const diagnostics={checks,inner:{width:innerWidth,height:innerHeight},table:metric(table),result:metric(result),bar:metric(bar),hand:metric(hand),board:metric(boardBox),topHole:metric(topHole),sideHole:metric(sideHole)};
  document.body.insertAdjacentHTML('beforeend',`<pre data-poker-ok="${Object.values(checks).every(Boolean)?'1':'0'}">${JSON.stringify(diagnostics)}</pre>`);
},120));
</script></body></html>'''


def _chrome() -> str:
    for name in ("google-chrome", "google-chrome-stable", "chrome", "chromium", "chromium-browser", "msedge"):
        path = shutil.which(name)
        if path:
            return path
    raise AssertionError("Chrome/Chromium is required")


def _run(chrome: str, fixture: Path, width: int, height: int, marker: str) -> str:
    proc = subprocess.run(
        [
            chrome,
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--allow-file-access-from-files",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=1800",
            f"--window-size={width},{height}",
            "--dump-dom",
            fixture.resolve().as_uri(),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )
    document = proc.stdout
    if marker not in document:
        # Installed Edge on Windows can exit successfully without writing
        # --dump-dom output. Keep Chromium's dependency-free CI path above,
        # but use the browser harness already required by poker-simple locally.
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=chrome,
                headless=True,
                args=["--no-sandbox", "--allow-file-access-from-files"],
            )
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(fixture.resolve().as_uri())
            page.wait_for_timeout(250)
            document = page.content()
            browser.close()
    assert marker in document, f"responsive parity failed {width}x{height}: {document[-2200:]}"
    return document


def main() -> None:
    foundation = (ROOT / "admin_static" / "admin_ui_foundation.css").read_text(encoding="utf-8")
    sitngo = (ROOT / "admin_static" / "admin_sitngo.css").read_text(encoding="utf-8")
    journey = (ROOT / "smoke_test_fullstack_browser_user_journey.py").read_text(encoding="utf-8")
    final_css = build_styles()

    assert "safe-area-inset-top" in foundation
    assert "bottom:calc(18px + env(safe-area-inset-bottom))" in foundation
    assert ".sng-remove-level{width:44px;height:44px;min-height:44px}" in sitngo
    assert "innerWidth <= 700" not in journey
    assert "matchMedia('(max-width:760px)')" in journey
    assert "top:calc(env(safe-area-inset-top) + 8px)" in final_css
    assert "bottom:auto" in final_css
    assert "width:clamp(40px,11vw,48px)!important" in final_css
    assert "max-width:calc(100% - 92px)!important" in final_css
    assert "#actionBar:not(:has(.jj-v5-preactions))" in final_css
    assert ".jj-mobile-poker-observer #pokerRoom .jj-observer-join>div" in final_css
    assert "left:auto!important;right:8px!important;bottom:8px!important" in final_css
    assert "margin:0!important" in final_css
    assert "top:calc(100% + 8px)!important" in final_css
    assert "bottom:calc(100% + 8px)!important" in final_css

    chrome = _chrome()
    with tempfile.TemporaryDirectory(prefix="jj-responsive-parity-") as td:
        root = Path(td)
        (root / "styles.css").write_text(final_css, encoding="utf-8")
        main_fixture = root / "main.html"
        main_fixture.write_text(MAIN_FIXTURE, encoding="utf-8")
        poker_fixture = root / "poker.html"
        poker_fixture.write_text(POKER_FIXTURE, encoding="utf-8")

        admin_css = "\n".join(
            (ROOT / "admin_static" / name).read_text(encoding="utf-8")
            for name in ("admin.css", "admin_sitngo.css", "admin_ui_foundation.css")
        )
        (root / "admin.css").write_text(admin_css, encoding="utf-8")
        admin_fixture = root / "admin.html"
        admin_fixture.write_text(ADMIN_FIXTURE, encoding="utf-8")

        for width, height in ((390, 844), (760, 1024), (761, 1024), (844, 390)):
            _run(chrome, main_fixture, width, height, 'data-main-ok="1"')
            _run(chrome, admin_fixture, width, height, 'data-admin-ok="1"')

        # Chromium's headless window manager clamps requested widths below
        # ~500 CSS px, which turns 320x568 into an artificial landscape viewport.
        # Exercise the same <=760px portrait rules with dimensions Chrome can
        # represent faithfully; narrow-phone sizing is additionally guarded by
        # the CSS contract assertions above.
        for width, height in ((500, 700), (560, 800), (640, 900), (760, 1024)):
            _run(chrome, poker_fixture, width, height, 'data-poker-ok="1"')

    print("JJ_RESPONSIVE_PARITY_OK phone/boundary/tablet/landscape/mobile-poker")


if __name__ == "__main__":
    main()
