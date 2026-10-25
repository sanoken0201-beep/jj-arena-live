"""Lazy point-economy panel on the ranking screen; no new dependencies."""
from __future__ import annotations

import hashlib
from pathlib import Path

MARKER = "JJ_POINT_ECONOMY_V1"

PANEL = r'''
        <details id="jjPointEconomy" class="card jj-economy admin-only">
          <summary><span><b>ポイント履歴・インフレ分析</b><small>入力・オンライン卓・今日の問題の推移を確認</small></span><span class="jj-economy-open">分析を開く ▾</span></summary>
          <div class="jj-economy-body">
            <p class="hint">ランキングに算入されるポイントの純増減を日別に集計します。分析は開いたときだけ読み込みます。</p>
            <div class="jj-economy-tools">
              <label>期間<select id="jjEconomySeason"><option value="fall">現在のシーズン</option></select></label>
              <label>履歴の種類<select id="jjEconomySource"><option value="all">すべて</option><option value="club">入力</option><option value="online">オンライン卓</option><option value="quiz">今日の問題</option><option value="other">その他・補正</option></select></label>
              <button id="jjEconomyRefresh" class="soft" type="button">更新</button>
            </div>
            <div id="jjEconomyStatus" class="hint" role="status" aria-live="polite"></div>
            <div id="jjEconomyNumbers" class="jj-economy-numbers"></div>
            <div class="jj-economy-chart"><div class="jj-economy-chart-head"><b>累積ポイント総量</b><span>日本時間 · シーズン開始から</span></div><div id="jjEconomyChart"></div><div class="jj-economy-legend"><span><i class="jj-legend-total"></i>合計</span><span><i class="jj-legend-quiz"></i>今日の問題の累積</span></div></div>
            <div class="jj-economy-grid"><div><h4>日別の増減</h4><div class="jj-economy-table-wrap"><table><thead><tr><th>日付</th><th>入力</th><th>オンライン</th><th>今日の問題</th><th>その他</th><th>純増減</th><th>累積</th></tr></thead><tbody id="jjEconomyDaily"></tbody></table></div></div><div><h4>取引履歴</h4><div id="jjEconomyHistory" class="jj-economy-history"></div><div class="jj-economy-pages"><button id="jjEconomyPrevious" type="button" class="soft" disabled>新しい履歴</button><span id="jjEconomyPageLabel"></span><button id="jjEconomyNext" type="button" class="soft" disabled>古い履歴</button></div></div></div>
            <p id="jjEconomyFootnote" class="hint"></p>
          </div>
        </details>
'''

CSS = r'''

/* JJ_POINT_ECONOMY_V1: intentionally outside the time-sensitive poker UI. */
.jj-economy{margin-top:20px;padding:0;overflow:hidden}
.jj-economy>summary{list-style:none;cursor:pointer;padding:20px 22px;display:flex;justify-content:space-between;align-items:center;gap:12px;background:linear-gradient(110deg,#faf8f1,#f0f8f5)}
.jj-economy>summary::-webkit-details-marker{display:none}
.jj-economy>summary b{display:block;font-size:1rem;color:var(--green)}
.jj-economy>summary small{display:block;margin-top:6px;color:var(--muted);font-size:.72rem}
.jj-economy-open{font-weight:850;color:var(--green);font-size:.72rem;white-space:nowrap}
.jj-economy[open] .jj-economy-open{font-size:0}
.jj-economy[open] .jj-economy-open:after{content:'閉じる ▴';font-size:.72rem}
.jj-economy-body{padding:22px;border-top:1px solid var(--line)}
.jj-economy-tools{display:flex;align-items:end;gap:10px;flex-wrap:wrap;margin:16px 0}
.jj-economy-tools label{min-width:170px;flex:1 1 180px}
.jj-economy-tools button{min-height:46px}
.jj-economy-numbers{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:14px 0}
.jj-economy-kpi{padding:15px;border:1px solid var(--line);border-radius:14px;background:#fbfcfa;min-width:0}
.jj-economy-kpi span{display:block;color:var(--muted);font-size:.7rem;margin-bottom:8px}
.jj-economy-kpi strong{display:block;color:var(--green);font-size:clamp(1rem,2vw,1.4rem);overflow-wrap:anywhere;font-variant-numeric:tabular-nums}
.jj-economy-chart{border:1px solid var(--line);border-radius:14px;padding:16px;background:#fff}
.jj-economy-chart-head{display:flex;justify-content:space-between;gap:8px;align-items:center;margin-bottom:8px}.jj-economy-chart-head span{color:var(--muted);font-size:.72rem}
#jjEconomyChart svg{width:100%;height:auto;display:block;min-height:130px}
.jj-economy-legend{display:flex;gap:15px;color:var(--muted);font-size:.7rem}.jj-economy-legend span{display:flex;align-items:center;gap:6px}.jj-economy-legend i{width:13px;height:3px;display:inline-block}
.jj-legend-total{background:#0c7550}.jj-legend-quiz{background:#db7a55}
.jj-economy-grid{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:18px;margin-top:20px;min-width:0}
.jj-economy-grid>div{min-width:0}.jj-economy-grid h4{font-size:.9rem;margin:0 0 10px}
.jj-economy-table-wrap{overflow:auto;max-height:400px;border:1px solid var(--line);border-radius:12px}
.jj-economy-table-wrap th,.jj-economy-table-wrap td{font-size:.72rem;padding:9px 11px;white-space:nowrap;font-variant-numeric:tabular-nums}
.jj-economy-history{max-height:400px;overflow-y:auto;border:1px solid var(--line);border-radius:12px;padding:0 12px}
.jj-economy-event{padding:10px 2px;border-bottom:1px solid var(--line)}.jj-economy-event:last-child{border-bottom:0}
.jj-economy-event-top{display:flex;justify-content:space-between;gap:8px;align-items:center;font-size:.78rem}.jj-economy-event .hint{margin-top:5px;overflow-wrap:anywhere;font-size:.68rem}
.jj-economy-tag{display:inline-block;background:#edf5f0;color:#086044;padding:3px 7px;border-radius:6px;font-size:.65rem;margin-right:7px}
.jj-economy-pages{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:10px}.jj-economy-pages button{min-height:36px;font-size:.7rem;padding:7px 10px}.jj-economy-pages span{color:var(--muted);font-size:.68rem}
#jjEconomyFootnote{margin-top:16px}
@media(max-width:950px){.jj-economy-grid{grid-template-columns:1fr}.jj-economy-numbers{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:600px){.jj-economy>summary{padding:16px}.jj-economy-body{padding:14px}.jj-economy-tools label{flex-basis:100%}.jj-economy-chart{padding:10px}.jj-economy-numbers{gap:7px}.jj-economy-kpi{padding:11px}.jj-economy-kpi strong{font-size:1.05rem}}
'''

JS = r'''
  // JJ_POINT_ECONOMY_V1: fetch only on explicit expansion/filter/page change.
  let jjEconomyRequest=0,jjEconomyOffset=0,jjEconomyNextOffset=null;
  const jjEconomyPanel=$('#jjPointEconomy');
  const jjEconomySigned=n=>`${Number(n)>=0?'+':''}${fmt(n)}`;
  const jjEconomyLabels={club:'入力',online:'オンライン卓',quiz:'今日の問題',other:'その他・補正'};
  function jjEconomyLineChart(rows){
    if(!rows.length)return '<div class="empty">推移データはありません</div>';
    const width=720,height=214,left=58,right=18,top=14,bottom=30;
    const all=rows.flatMap(r=>[Number(r.cumulative),Number(r.quiz_cumulative)]);
    const low=Math.min(0,...all),high=Math.max(0,...all);
    const range=high-low||1,n=rows.length;
    const x=i=>left+(width-left-right)*(n===1?.5:i/(n-1));
    const y=v=>top+(height-top-bottom)*(high-Number(v))/range;
    const line=key=>rows.map((r,i)=>`${x(i).toFixed(2)},${y(r[key]).toFixed(2)}`).join(' ');
    const grid=[0,.5,1].map(t=>{const yy=top+t*(height-top-bottom),value=high-range*t;return `<line x1="${left}" y1="${yy}" x2="${width-right}" y2="${yy}" stroke="#e1e9e3"/><text x="${left-7}" y="${yy+4}" text-anchor="end" font-size="11" fill="#67776b">${safe(fmt(value.toFixed(1)))}</text>`}).join('');
    return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="日別累積ポイント総量の推移。シーズン開始から${safe(rows[rows.length-1].date)}まで"><title>ポイント総量の推移</title>${grid}<polyline points="${line('cumulative')}" fill="none" stroke="#0c7550" stroke-width="3" stroke-linejoin="round"/><polyline points="${line('quiz_cumulative')}" fill="none" stroke="#db7a55" stroke-width="2.5" stroke-linejoin="round"/><text x="${left}" y="${height-7}" font-size="11" fill="#67776b">${safe(rows[0].date)}</text><text x="${width-right}" y="${height-7}" text-anchor="end" font-size="11" fill="#67776b">${safe(rows[n-1].date)}</text></svg>`;
  }
  function jjEconomyDraw(data,offset){
    const total=data.totals||{},prev=Number(total.total||0)-Number(data.last_7_days||0);
    const rate=prev>0?` (${jjEconomySigned((Number(data.last_7_days)/prev*100).toFixed(1))}%)`:'';
    const stats=[['現在の累積総量',fmt(total.total)+' pt'],['直近7日間の純増減',jjEconomySigned(data.last_7_days)+rate+' pt'],['直近30日間の純増減',jjEconomySigned(data.last_30_days)+' pt'],['今日の問題による累積',jjEconomySigned(total.quiz)+' pt']];
    $('#jjEconomyNumbers').innerHTML=stats.map(([label,value])=>`<div class="jj-economy-kpi"><span>${safe(label)}</span><strong>${safe(value)}</strong></div>`).join('');
    $('#jjEconomyChart').innerHTML=jjEconomyLineChart(data.daily||[]);
    const active=(data.daily||[]).filter(r=>r.change||r.club||r.online||r.quiz||r.other).reverse();
    $('#jjEconomyDaily').innerHTML=active.map(r=>`<tr><td>${safe(r.date)}</td><td>${jjEconomySigned(r.club)}</td><td>${jjEconomySigned(r.online)}</td><td>${jjEconomySigned(r.quiz)}</td><td>${jjEconomySigned(r.other)}</td><td><b>${jjEconomySigned(r.change)}</b></td><td>${fmt(r.cumulative)}</td></tr>`).join('')||'<tr><td colspan="7">まだ記録がありません</td></tr>';
    const history=data.history||[];
    $('#jjEconomyHistory').innerHTML=history.map(r=>`<div class="jj-economy-event"><div class="jj-economy-event-top"><span><span class="jj-economy-tag">${safe(jjEconomyLabels[r.source]||r.source)}</span><b>${safe(r.player)}</b></span><strong class="${r.points>=0?'positive':'negative'}">${jjEconomySigned(r.points)}</strong></div><div class="hint">${safe(r.date)} · ${safe(r.detail)}</div></div>`).join('')||'<div class="empty">該当する履歴はありません</div>';
    jjEconomyOffset=offset;jjEconomyNextOffset=data.next_offset;
    $('#jjEconomyPrevious').disabled=offset===0;
    $('#jjEconomyNext').disabled=data.next_offset==null;
    $('#jjEconomyPageLabel').textContent=history.length?`${offset+1}〜${offset+history.length}件目`:'0件';
    $('#jjEconomyFootnote').textContent=`入力 ${jjEconomySigned(total.club)} pt / オンライン ${jjEconomySigned(total.online)} pt / 今日の問題 ${jjEconomySigned(total.quiz)} pt / その他 ${jjEconomySigned(total.other)} pt。${data.definition||''} 記録の反映日時を基準に、日本時間で日別集計しています。`;
  }
  async function jjEconomySeasons(){
    const rows=await jjReadSeasons();
    if(!jjEconomyPanel?.open)return;
    const selected=$('#jjEconomySeason').value;
    const active=rows.find(r=>r.status==='active');
    const options=[{value:'fall',name:active?.name||'現在のシーズン'},...rows.filter(r=>r.status==='archived').map(r=>({value:r.season_id==='fall'?'archive:fall':r.season_id,name:r.name}))];
    $('#jjEconomySeason').innerHTML=options.map(r=>`<option value="${safe(r.value)}">${safe(r.name)}</option>`).join('');
    if(options.some(r=>r.value===selected))$('#jjEconomySeason').value=selected;
  }
  async function jjEconomyLoad(offset=0){
    if(!me||me.role!=='admin'||currentView!=='ranking'||!jjEconomyPanel?.open)return;
    const sequence=++jjEconomyRequest;
    $('#jjEconomyStatus').textContent='ポイント履歴を集計中…';
    const query=new URLSearchParams({season:$('#jjEconomySeason').value,source:$('#jjEconomySource').value,offset:String(offset),limit:'50'});
    try{
      const data=await api('/admin/point-economy?'+query.toString());
      if(sequence!==jjEconomyRequest||!jjEconomyPanel.open||currentView!=='ranking')return;
      jjEconomyDraw(data,offset);$('#jjEconomyStatus').textContent='集計完了 · '+safe(data.as_of)+'（日本時間）';
    }catch(error){if(sequence===jjEconomyRequest)$('#jjEconomyStatus').textContent='読み込みできません: '+error.message;}
  }
  document.addEventListener('toggle',event=>{
    if(event.target!==jjEconomyPanel)return;
    ++jjEconomyRequest;
    if(jjEconomyPanel.open&&me?.role==='admin'){
      jjEconomySeasons().then(()=>jjEconomyLoad(0)).catch(err=>{$('#jjEconomyStatus').textContent=err.message});
    }
  },true);
  $('#jjEconomySeason').addEventListener('change',()=>jjEconomyLoad(0));
  $('#jjEconomySource').addEventListener('change',()=>jjEconomyLoad(0));
  $('#jjEconomyRefresh').addEventListener('click',()=>jjEconomyLoad(jjEconomyOffset));
  $('#jjEconomyPrevious').addEventListener('click',()=>jjEconomyLoad(Math.max(0,jjEconomyOffset-50)));
  $('#jjEconomyNext').addEventListener('click',()=>{if(jjEconomyNextOffset!=null)jjEconomyLoad(jjEconomyNextOffset)});
'''


def _replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError(f"point economy asset anchor drift: {old[:90]}")
    return text.replace(old, new, 1)


def apply_to_build(output_root, manifest):
    root = Path(output_root)
    index_path = root / "index.html"
    js_path = root / "static/app.js"
    css_path = root / "static/styles.css"
    index = index_path.read_text(encoding="utf-8")
    js = js_path.read_text(encoding="utf-8")
    css = css_path.read_text(encoding="utf-8")
    if MARKER not in js:
        index = _replace_once(index, '      </section>\n\n      <section id="tablesView"', PANEL + '      </section>\n\n      <section id="tablesView"')
        js = _replace_once(js, '  // v1.24.4 analysis focus and decision-first review.', JS + '\n  // v1.24.4 analysis focus and decision-first review.')
        css += CSS
    for path, value in ((index_path, index), (js_path, js), (css_path, css)):
        path.write_text(value, encoding="utf-8")
        manifest["outputs"][str(path.relative_to(root))] = hashlib.sha256(value.encode()).hexdigest()
    manifest.setdefault("post_transforms", {})["point_economy_ui"] = MARKER
    return manifest
