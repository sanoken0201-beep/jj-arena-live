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


def _chrome() -> str:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
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
    assert marker in proc.stdout, f"responsive parity failed {width}x{height}: {proc.stdout[-2200:]}"
    return proc.stdout


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

    chrome = _chrome()
    with tempfile.TemporaryDirectory(prefix="jj-responsive-parity-") as td:
        root = Path(td)
        (root / "styles.css").write_text(final_css, encoding="utf-8")
        main_fixture = root / "main.html"
        main_fixture.write_text(MAIN_FIXTURE, encoding="utf-8")

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

    print("JJ_RESPONSIVE_PARITY_OK phone/boundary/tablet/landscape")


if __name__ == "__main__":
    main()
