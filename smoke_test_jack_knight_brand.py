from __future__ import annotations

"""Static contract and real Chromium screenshot checks for the Jack knight.

Runs against the *compiled* site CSS and Home HTML. Does not need a backend,
session, database or JavaScript; uses fonts already present on CI runners.
"""

import gzip
import re
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import served_assets
from jack_knight_brand import CSS, KNIGHT_SVG, MARKER, transform_index, transform_styles

ROOT = Path(__file__).resolve().parent
SCREENSHOT_DIR = ROOT / "test-artifacts" / "jack-knight"

def contract() -> tuple[str, str]:
    with (
        patch.object(served_assets, "transform_jack_knight_index", lambda s: s),
        patch.object(served_assets, "transform_jack_knight_styles", lambda s: s),
        patch.object(served_assets, "JACK_KNIGHT_MARKER", ""),
    ):
        previous_html, previous_css = served_assets.build_index(), served_assets.build_styles()

    html, css = served_assets.build_index(), served_assets.build_styles()
    assert transform_index(html) == html
    assert transform_styles(css) == css
    assert html.count('class="jj-jack-knight"') == 1
    assert html.count("jj-jack-hero") == 1
    assert MARKER in html and MARKER in css
    assert len(KNIGHT_SVG.encode("utf-8")) <= 4300
    assert "<image" not in KNIGHT_SVG and "<script" not in KNIGHT_SVG
    assert "<animate" not in KNIGHT_SVG and "http" not in KNIGHT_SVG.split("viewBox")[1]
    assert not re.search(r"[♠♥♦♣]", KNIGHT_SVG), "Knight clothes must not repeat card suit patterns"
    svg = ET.fromstring(KNIGHT_SVG)
    assert svg.tag.endswith("svg")
    assert len(list(svg.iter())) <= 35
    assert svg.attrib["aria-hidden"] == "true"
    assert 'focusable="false"' in KNIGHT_SVG

    # All markup except the home-art element, one heading, and hero class
    # must be byte-identical. No poker, ranking, nav or member UI mutation.
    cleaned = html.replace(KNIGHT_SVG, "").replace(
        '<article class="hero card jj-jack-hero">', '<article class="hero card">'
    ).replace("<h3>JJ Arena</h3>", "<h3>次の1ハンドを、<br>みんなで。</h3>")
    cleaned = cleaned.replace("\n<!-- " + MARKER + " -->\n", "")
    assert cleaned == previous_html, "non-Home markup changed"
    assert css.startswith(previous_css), "existing stylesheet changed instead of being kept intact"
    assert css.endswith(CSS + "\n/* " + MARKER + " */\n")
    assert "transition:" not in CSS and "animation:" not in CSS
    assert css.count("@font-face") == previous_css.count("@font-face")
    assert css.count("@import") == previous_css.count("@import")
    gzip_delta = len(gzip.compress(css.encode("utf-8"),mtime=0)) - len(gzip.compress(previous_css.encode("utf-8"),mtime=0))
    assert gzip_delta <= 900, f"CSS transfer grew excessively: {gzip_delta} bytes"
    assert "<h3>JJ Arena</h3>" in html
    assert "<h3>次の1ハンドを" not in html
    print(f"JJ_JACK_KNIGHT_STATIC_OK SVG={len(KNIGHT_SVG.encode())}B CSS_gzip_delta={gzip_delta}B",flush=True)
    return html, css


def browser_check(html: str, css: str) -> None:
    from playwright.sync_api import sync_playwright

    match = re.search(r'(<section id="homeView".*?</section>)\s*<section id="rankingView"', html, re.S)
    assert match, "Home section no longer present"
    fixture = '<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>' + css + '</style></head><body><main class="main" style="margin-left:0;max-width:none">' + match.group(1) + '</main></body></html>'
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True,args=["--no-sandbox","--disable-dev-shm-usage"])
        SCREENSHOT_DIR.mkdir(parents=True,exist_ok=True)
        for w,h in ((320,640),(390,844),(760,1024),(1024,768),(1440,900)):
            page = browser.new_page(viewport={"width":w,"height":h},device_scale_factor=1)
            page.set_content(fixture)
            page.wait_for_timeout(250)
            info = page.evaluate("""() => {
              const by=s=>document.querySelector(s);
              const rect=s=>by(s).getBoundingClientRect();
              const overlap=(a,b)=>a.left<b.right && a.right>b.left && a.top<b.bottom && a.bottom>b.top;
              const img=rect('.jj-jack-knight'), hero=rect('.jj-jack-hero'),
                    title=rect('.jj-jack-hero h3'), primary=rect('.jj-jack-hero .primary');
              const v={
                art:img.width>40&&img.height>40,
                inset:img.left>=hero.left-2 && img.right<=hero.right+2,
                titleClear:!overlap(img,title),
                actionClear:!overlap(img,primary),
                noPageOverflow:document.documentElement.scrollWidth<=innerWidth+2,
                title:by('.jj-jack-hero h3').textContent,
                buttons:by('.jj-jack-hero .button-row').children.length,
                artWidth:Math.round(img.width),
                browserWidth:innerWidth
              };
              return v;
            }""")
            page.screenshot(path=str(SCREENSHOT_DIR/f"home-{w}.png"),full_page=True)
            assert all(info[k] for k in ("art","inset","titleClear","actionClear","noPageOverflow")), f"{w}px: {info}"
            assert info["title"]=="JJ Arena" and info["buttons"]==2
            print(f"JJ_JACK_KNIGHT_BROWSER_OK width={w} art={info['artWidth']}px",flush=True)
            page.close()
        browser.close()


if __name__ == "__main__":
    html,css = contract()
    import sys
    if "--browser" in sys.argv:
        browser_check(html, css)
