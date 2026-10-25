"""Chrome regression: the Japanese home headline must use only its intended break."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from served_assets import build_index, build_styles


def main() -> None:
    chrome = next((shutil.which(name) for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser") if shutil.which(name)), None)
    if not chrome:
        raise AssertionError("Chrome/Chromium is required for headline layout verification")

    index = build_index()
    start = '<article class="hero card">'
    end = '</article>'
    assert index.count(start) == 1
    hero = start + index.split(start, 1)[1].split(end, 1)[0] + end
    assert '<h3>次の1ハンドを、<br>みんなで。</h3>' in hero

    markup = '''<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="styles.css">
<style>#appView.hidden{display:block!important}#homeView.view{display:block!important}</style></head>
<body><div id="appView" class="app-shell"><aside class="sidebar"><div class="side-brand">JJ Arena</div></aside>
<main class="main"><header class="topbar"><h2>今日のJJ</h2></header>
<section id="homeView" class="view active-view"><div class="hero-grid">''' + hero + '''
<article class="card kpi"><strong>150</strong><span>BB START</span></article>
</div></section></main></div>
<script>addEventListener('load',()=>setTimeout(()=>{
 const hero=document.querySelector('#homeView .hero'),h=hero.querySelector('h3');
 const first=document.createRange(),second=document.createRange();
 first.selectNodeContents(h.firstChild);second.selectNodeContents(h.lastChild);
 const hRect=h.getBoundingClientRect(),heroRect=hero.getBoundingClientRect();
 const firstRect=first.getBoundingClientRect(),secondRect=second.getBoundingClientRect();
 const lineHeight=parseFloat(getComputedStyle(h).lineHeight);
 const checks={
  firstLineIntact:first.getClientRects().length===1,
  secondLineIntact:second.getClientRects().length===1,
  exactlyTwoLines:Math.abs(hRect.height-2*lineHeight)<=3,
  titleInsideHero:firstRect.right<=heroRect.right-10&&secondRect.right<=heroRect.right-10,
  noHorizontalOverflow:document.documentElement.scrollWidth<=innerWidth+2
 };
 document.body.insertAdjacentHTML('beforeend',`<pre data-hero-ok="${Object.values(checks).every(Boolean)?'1':'0'}">${JSON.stringify(checks)}</pre>`);
},100));</script></body></html>'''

    with tempfile.TemporaryDirectory(prefix="jj-hero-layout-") as work:
        root = Path(work)
        (root / "styles.css").write_text(build_styles(), encoding="utf-8")
        fixture = root / "hero.html"
        fixture.write_text(markup, encoding="utf-8")
        for width in (320, 390, 760, 960, 1240, 1440, 1920):
            result = subprocess.run(
                [chrome, "--headless", "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files",
                 "--virtual-time-budget=3000", f"--window-size={width},900", "--dump-dom", fixture.resolve().as_uri()],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30, check=True,
            )
            assert 'data-hero-ok="1"' in result.stdout, f"hero wraps at {width}px: {result.stdout[-1200:]}"
    print("JJ_ILLUMINATED_HERO_LAYOUT_OK")


if __name__ == "__main__":
    main()
