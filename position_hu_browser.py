from __future__ import annotations

"""Build-time, non-invasive split of HU and 3+ player position statistics.

The v1.24.4 browser source is immutable. Extend only the compiled client asset
and keep the original overall-performance and hand-history views unchanged.
"""

HU_POSITION_UI_MARKER = "jj-analysis-hu-section"

_POSITION_PANEL_BEFORE = (
    '<h3>ポジション別</h3></div></div>'
    '<div id="jjAnalysisPositions" class="jj-dimension-table"></div></section>'
)
_POSITION_PANEL_AFTER = (
    '<h3>ポジション別（3人以上）</h3>'
    '<p>HUは別集計です。上部の全体指標にはHUも含まれます。</p></div></div>'
    '<div id="jjAnalysisPositions" class="jj-dimension-table"></div>'
    '<div class="jj-analysis-hu-section">'
    '<div class="jj-analysis-hu-heading"><strong>HU（2人卓）</strong>'
    '<small id="jjAnalysisHuMeta">0 hands</small></div>'
    '<div id="jjAnalysisHuPositions" class="jj-dimension-table"></div>'
    '</div></section>'
)
_RENDER_BEFORE = (
    "jjRenderDimension('#jjAnalysisPositions',data.positions||[],'Position');"
    "jjRenderDimension('#jjAnalysisStacks',data.stack_bands||[],'Stack');"
)
_RENDER_AFTER = (
    "jjRenderDimension('#jjAnalysisPositions',data.positions||[],'Position');"
    "jjRenderDimension('#jjAnalysisHuPositions',data.hu_positions||[],'HU Position');"
    "const hu=data.hu_overall||{};"
    "const huMeta=$('#jjAnalysisHuMeta');"
    "if(huMeta)huMeta.textContent=`${fmt(hu.hands||0)} hands · ${jjSigned(hu.net_bb||0)}`;"
    "jjRenderDimension('#jjAnalysisStacks',data.stack_bands||[],'Stack');"
)
_HU_CSS = """
/* jj-analysis-hu-section: separate heads-up samples from 3+ player positions */
.jj-analysis-hu-section{
  margin-top:20px;
  padding-top:18px;
  border-top:1px solid rgba(150,165,155,.28);
}
.jj-analysis-hu-heading{
  display:flex;
  align-items:baseline;
  justify-content:space-between;
  flex-wrap:wrap;
  gap:8px;
  margin-bottom:10px;
}
.jj-analysis-hu-heading strong{font-size:1rem;font-weight:800}
.jj-analysis-hu-heading small{font-size:.8rem;opacity:.82}
"""


def transform_app_js(js: str) -> str:
    if HU_POSITION_UI_MARKER in js:
        return js
    if js.count(_POSITION_PANEL_BEFORE) != 1:
        raise RuntimeError("HU position panel anchor drift")
    if js.count(_RENDER_BEFORE) != 1:
        raise RuntimeError("HU position render anchor drift")
    return js.replace(_POSITION_PANEL_BEFORE, _POSITION_PANEL_AFTER, 1).replace(
        _RENDER_BEFORE, _RENDER_AFTER, 1
    )


def transform_styles(css: str) -> str:
    return css if "/* jj-analysis-hu-section:" in css else css + "\n" + _HU_CSS
