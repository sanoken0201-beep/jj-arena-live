"""Three-way actual-profit chart for the existing private hand analysis screen.

The golden-master browser bundle is never edited. This transforms the compiled
asset at build time, after the existing performance/UX pipeline.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

MARKER = "JJ_HAND_RESULT_TRENDS_V1"

CHART_JS = r'''
  // JJ_HAND_RESULT_TRENDS_V1: actual profit, not all-in adjusted EV.
  const jjTrendVisible={net:true,sd:true,nsd:true};
  function jjRenderTrend(points){
    const box=$('#jjAnalysisTrend'),meta=$('#jjAnalysisTrendMeta');
    if(!box)return;
    if(!points.length){
      box.innerHTML='<div class="empty">ハンドが記録されると総収支・SD・NSDの推移を表示します。</div>';
      if(meta)meta.textContent='';
      return;
    }
    const series=[
      {key:'net',field:'cumulative_bb',label:'総収支'},
      {key:'sd',field:'cumulative_sd_bb',label:'SD（ショーダウン）'},
      {key:'nsd',field:'cumulative_nsd_bb',label:'NSD（非ショーダウン）'}
    ];
    const finite=v=>Number.isFinite(Number(v))?Number(v):0;
    const rows=points.map((p,i)=>({
      hand:finite(p.hand_number)||i+1,
      net:finite(p.cumulative_bb),sd:finite(p.cumulative_sd_bb),nsd:finite(p.cumulative_nsd_bb)
    }));
    const last=rows[rows.length-1],totalHands=last.hand;
    const all=[0,...rows.flatMap(p=>[p.net,p.sd,p.nsd])];
    let min=Math.min(...all),max=Math.max(...all);
    if(min===max){min-=1;max+=1}
    const extra=(max-min)*.06;min-=extra;max+=extra;
    const w=900,h=250,left=65,right=22,top=13,bottom=34;
    const x=n=>left+(w-left-right)*n/Math.max(1,totalHands);
    const y=v=>top+(h-top-bottom)*(max-v)/(max-min);
    const line=key=>[
      `M${x(0).toFixed(1)},${y(0).toFixed(1)}`,
      ...rows.map(p=>`L${x(p.hand).toFixed(1)},${y(p[key]).toFixed(1)}`)
    ].join(' ');
    const ticks=Array.from({length:5},(_,i)=>min+(max-min)*i/4);
    const grid=ticks.map(value=>`<g class="jj-result-grid"><line x1="${left}" x2="${w-right}" y1="${y(value).toFixed(1)}" y2="${y(value).toFixed(1)}"/><text x="${left-10}" y="${(y(value)+4).toFixed(1)}" text-anchor="end">${safe(String(Math.round(value*10)/10))}</text></g>`).join('');
    const paths=series.filter(s=>jjTrendVisible[s.key]).map(s=>`<path class="jj-result-line jj-result-${s.key}" d="${line(s.key)}" vector-effect="non-scaling-stroke"/>`).join('');
    const legends=series.map(s=>`<button type="button" class="jj-result-legend jj-result-${s.key}" data-jj-result-series="${s.key}" aria-pressed="${jjTrendVisible[s.key]?'true':'false'}"><i aria-hidden="true"></i><span>${s.label}</span><strong>${safe(jjSigned(last[s.key]))}</strong></button>`).join('');
    box.innerHTML=`<div class="jj-result-legends" aria-label="表示する収支線">${legends}</div>
      <svg viewBox="0 0 ${w} ${h}" role="img" aria-label="ハンド数ごとの総収支・ショーダウン収支・非ショーダウン収支の累積推移。単位bb">
        <title>累積収支（bb）: 総収支、SD、NSD</title>
        ${grid}<line class="jj-result-zero" x1="${left}" x2="${w-right}" y1="${y(0).toFixed(1)}" y2="${y(0).toFixed(1)}"/>
        ${paths}<text x="${left}" y="${h-9}" class="jj-result-axis" text-anchor="start">0</text>
        <text x="${w-right}" y="${h-9}" class="jj-result-axis" text-anchor="end">${safe(String(totalHands))} hands</text>
      </svg>
      <p class="jj-result-note">SDは本人がショーダウンに到達したハンド、NSDは到達しなかったハンド。総収支 = SD + NSD（レーキ反映後・EVではありません）。</p>`;
    const defaultMeta=`${totalHands.toLocaleString()} hands · bb`;
    if(meta)meta.textContent=defaultMeta;
    box.querySelectorAll('[data-jj-result-series]').forEach(button=>button.addEventListener('click',()=>{
      const key=button.dataset.jjResultSeries;
      jjTrendVisible[key]=!jjTrendVisible[key];jjRenderTrend(points);
    }));
    const svg=box.querySelector('svg');
    svg?.addEventListener('pointermove',event=>{
      if(!meta)return;
      const rect=svg.getBoundingClientRect();
      if(!rect.width)return;
      const scaled=(event.clientX-rect.left)/rect.width*w;
      const nearest=rows.reduce((best,p)=>Math.abs(x(p.hand)-scaled)<Math.abs(x(best.hand)-scaled)?p:best,rows[0]);
      meta.textContent=`#${nearest.hand} · Total ${jjSigned(nearest.net)} / SD ${jjSigned(nearest.sd)} / NSD ${jjSigned(nearest.nsd)}`;
    });
    svg?.addEventListener('pointerleave',()=>{if(meta)meta.textContent=defaultMeta});
  }
'''

CHART_CSS = r'''

/* JJ_HAND_RESULT_TRENDS_V1: lightweight SVG chart with mobile-safe controls. */
#jjAnalysisTrend .jj-result-legends{display:flex;flex-wrap:wrap;gap:8px;margin:5px 0 13px}
#jjAnalysisTrend .jj-result-legend{display:inline-flex;align-items:center;gap:7px;flex-wrap:wrap;min-height:38px;border:1px solid var(--line,#d9e2dd);border-radius:10px;background:#fff;padding:7px 11px;font-size:.68rem;color:var(--text,#24372f);cursor:pointer;line-height:1.3}
#jjAnalysisTrend .jj-result-legend strong{font-variant-numeric:tabular-nums;font-size:.76rem}
#jjAnalysisTrend .jj-result-legend i{display:block;width:19px;border-top:3px solid currentColor;border-radius:4px}
#jjAnalysisTrend .jj-result-net{color:#2667b5}
#jjAnalysisTrend .jj-result-sd{color:#0b8052}
#jjAnalysisTrend .jj-result-nsd{color:#bd3b5c}
#jjAnalysisTrend .jj-result-legend[aria-pressed="false"]{opacity:.45}
#jjAnalysisTrend .jj-result-legend:focus-visible{outline:2px solid #2667b5;outline-offset:2px}
#jjAnalysisTrend svg{height:auto;min-height:170px;max-height:260px;overflow:hidden}
#jjAnalysisTrend .jj-result-line{fill:none;stroke:currentColor;stroke-width:2.8;stroke-linecap:round;stroke-linejoin:round}
#jjAnalysisTrend .jj-result-grid line{stroke:rgba(88,104,98,.17);stroke-width:1}
#jjAnalysisTrend .jj-result-grid text,#jjAnalysisTrend .jj-result-axis{fill:#64756c;font:12px sans-serif}
#jjAnalysisTrend .jj-result-zero{stroke:#778980;stroke-dasharray:5 4;stroke-width:1.3}
#jjAnalysisTrend .jj-result-note{color:var(--muted,#63766d);font-size:.65rem;line-height:1.6;margin:9px 0 0}
#jjAnalysisTrendMeta{overflow-wrap:anywhere;min-width:0;max-width:min(100%,380px);text-align:right}
@media(max-width:760px){#jjAnalysisTrend .jj-result-legends{gap:6px}#jjAnalysisTrend .jj-result-legend{flex:1 1 135px;justify-content:center;padding:8px 7px}#jjAnalysisTrend svg{min-height:130px}#jjAnalysisTrendMeta{font-size:.6rem;max-width:48%}}
'''


def transform_app_js(source: str) -> str:
    if MARKER in source:
        return source
    start = source.find("  function jjRenderTrend(points){")
    if start < 0:
        raise RuntimeError("hand result trend drift: renderer not found")
    end = source.find("\n\n  function jjHandQuery()", start)
    if end < 0 or source.count("  function jjRenderTrend(points){") != 1:
        raise RuntimeError("hand result trend drift: renderer boundary not unique")
    original = source[start:end]
    if 'p.cumulative_bb' not in original or 'jj-chart-line' not in original:
        raise RuntimeError("hand result trend drift: unexpected original renderer")
    return source[:start] + CHART_JS.strip("\n") + source[end:]


def transform_styles(source: str) -> str:
    return source if MARKER in source else source + CHART_CSS


def apply_to_build(output_root: Path | str, manifest: dict) -> dict:
    root = Path(output_root)
    for relative, transform in (
        ("static/app.js", transform_app_js),
        ("static/styles.css", transform_styles),
    ):
        path = root / relative
        content = transform(path.read_text(encoding="utf-8"))
        path.write_text(content, encoding="utf-8", newline="\n")
        manifest["outputs"][relative] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    manifest.setdefault("post_transforms", {})["hand_result_trends"] = MARKER
    return manifest
