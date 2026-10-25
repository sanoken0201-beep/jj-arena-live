"""Regression checks for cumulative profit / showdown / non-showdown breakdown."""
from __future__ import annotations

import html
import json
import re
import subprocess
import tempfile
from pathlib import Path

from browser_asset_pipeline import finalize_build
from hand_analytics import _aggregate, _trend
from hand_result_trends_ui import CHART_JS, CHART_CSS, MARKER, transform_app_js, transform_styles
from served_assets import build_all, validate_built_assets


def test_accounting() -> None:
    # The second hand reaches showdown, the third does not even though other
    # players may have shown cards (classification is per user, not per table).
    rows = [
        {"hand_id": "steal", "completed_at": "2026-10-01T00:00:00Z", "net_bb": 3.50, "went_showdown": 0},
        {"hand_id": "sd", "completed_at": "2026-10-01T00:01:00Z", "net_bb": -1.25, "went_showdown": 1},
        {"hand_id": "fold", "completed_at": "2026-10-01T00:02:00Z", "net_bb": -2.10, "went_showdown": 0},
        {"hand_id": "split", "completed_at": "2026-10-01T00:03:00Z", "net_bb": 0.40, "went_showdown": 1},
    ]
    points = _trend(rows)
    assert [p["hand_number"] for p in points] == [1, 2, 3, 4]
    assert [(p["cumulative_bb"], p["cumulative_sd_bb"], p["cumulative_nsd_bb"]) for p in points] == [
        (3.5, 0.0, 3.5),
        (2.25, -1.25, 3.5),
        (0.15, -1.25, 1.4),
        (0.55, -0.85, 1.4),
    ]
    assert all(round(p["cumulative_sd_bb"] + p["cumulative_nsd_bb"], 2) == p["cumulative_bb"] for p in points)
    agg = _aggregate(rows)
    assert (agg["net_bb"], agg["sd_bb"], agg["nsd_bb"]) == (0.55, -0.85, 1.4)
    sampled = _trend(rows, max_points=2)
    assert sampled[-1] == points[-1] and sampled[0] == points[0]
    assert _trend([]) == []
    assert (_aggregate([])["net_bb"], _aggregate([])["sd_bb"], _aggregate([])["nsd_bb"]) == (0, 0, 0)


def test_assets() -> None:
    with tempfile.TemporaryDirectory(prefix="jj-hand-result-chart-") as td:
        root = Path(td)
        finalize_build(root, build_all(root))
        validate_built_assets(root)
        js = (root / "static/app.js").read_text(encoding="utf-8")
        css = (root / "static/styles.css").read_text(encoding="utf-8")
        assert js.count(MARKER) == 1
        assert MARKER in css
        assert 'data-jj-result-series' in js and 'cumulative_sd_bb' in js
        assert 'cumulative_nsd_bb' in js and 'jj-result-note' in js
        assert transform_app_js(js) == js
        assert transform_styles(css) == css
        syntax = subprocess.run(["node", "--check"], input=js, text=True, capture_output=True)
        assert syntax.returncode == 0, syntax.stderr


def test_browser() -> None:
    from smoke_test_browser_user_journey import chrome_binary

    script = r'''
      const $=s=>document.querySelector(s);
      const safe=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
      const jjSigned=n=>`${Number(n)>0?'+':''}${Number(n)}bb`;
    ''' + CHART_JS + r'''
      try{
        const points=[
          {hand_number:1,cumulative_bb:2,cumulative_sd_bb:0,cumulative_nsd_bb:2},
          {hand_number:2,cumulative_bb:1,cumulative_sd_bb:-1,cumulative_nsd_bb:2},
          {hand_number:3,cumulative_bb:4,cumulative_sd_bb:2,cumulative_nsd_bb:2}
        ];
        jjRenderTrend(points);
        const box=$('#jjAnalysisTrend');
        const count=()=>box.querySelectorAll('.jj-result-line').length;
        if(count()!==3)throw Error('expected 3 paths');
        if(box.querySelectorAll('[data-jj-result-series]').length!==3)throw Error('expected legend');
        box.querySelector('[data-jj-result-series="nsd"]').click();
        if(count()!==2||box.querySelector('[data-jj-result-series="nsd"]').getAttribute('aria-pressed')!=='false')throw Error('toggle off');
        box.querySelector('[data-jj-result-series="nsd"]').click();
        if(count()!==3)throw Error('toggle on');
        if(!box.textContent.includes('SD（ショーダウン）')||!box.textContent.includes('NSD（非ショーダウン）'))throw Error('legend labels');
        if(document.documentElement.scrollWidth>innerWidth+2)throw Error('mobile overflow');
        document.querySelector('#result').textContent=JSON.stringify({ok:true,paths:count(),width:innerWidth});
      }catch(error){document.querySelector('#result').textContent=JSON.stringify({ok:false,error:error.message});}
    '''
    with tempfile.TemporaryDirectory(prefix="jj-hand-chart-browser-") as td:
        root = Path(td)
        fixture = root / "index.html"
        fixture.write_text('''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>''' + CHART_CSS + '''</style></head><body><div style="width:100%;max-width:900px"><span id="jjAnalysisTrendMeta"></span><div id="jjAnalysisTrend"></div></div><pre id="result"></pre><script>''' + script + '''</script></body></html>''', encoding="utf-8")
        for width, height in ((1440, 900), (390, 844)):
            p = subprocess.run(
                [chrome_binary(), "--headless", "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files",
                 "--virtual-time-budget=2000", f"--window-size={width},{height}", "--dump-dom", fixture.as_uri()],
                capture_output=True, text=True, timeout=35,
            )
            results = re.findall(r'<pre id="result">(.*?)</pre>', p.stdout, flags=re.S)
            assert results, p.stderr[-2000:]
            result = json.loads(html.unescape(results[-1]))
            assert result["ok"], result


if __name__ == "__main__":
    test_accounting()
    test_assets()
    test_browser()
    print("JJ_HAND_RESULT_TRENDS_OK")
