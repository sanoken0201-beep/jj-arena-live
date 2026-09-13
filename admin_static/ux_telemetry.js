(()=>{
  const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
  const safe=v=>String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const fmt=n=>new Intl.NumberFormat('ja-JP',{maximumFractionDigits:1}).format(Number(n||0));
  const labels={fold:'フォールド',check:'チェック',call:'コール',raise:'ベット/レイズ',allin:'オールイン',preset:'プリセット',slider:'スライダー',step:'±0.5BB',input:'直接入力',check_fold:'チェック/フォールド',settings:'設定',focus:'卓を広く表示',history:'ハンド履歴',chat:'チャット',mobile:'モバイル',tablet:'タブレット',desktop:'デスクトップ',unknown:'不明'};
  let currentDays=7;
  async function fetchSummary(days){const res=await fetch(`/api/admin/console/ux-telemetry?days=${days}`,{credentials:'include'});if(res.status===401){location.href='/';throw new Error('ログインが必要です')}let data=null;try{data=await res.json()}catch{}if(!res.ok)throw new Error(data?.detail||`HTTP ${res.status}`);return data}
  function ensureUi(){
    if($('#telemetryView'))return;
    const side=$('.side-nav'),mobile=$('.mobile-nav');
    if(side){const b=document.createElement('button');b.className='nav';b.dataset.view='telemetry';b.innerHTML='<span>⌁</span>UX計測';side.appendChild(b)}
    if(mobile){const b=document.createElement('button');b.dataset.view='telemetry';b.textContent='UX';mobile.appendChild(b)}
    const view=document.createElement('section');view.id='telemetryView';view.className='view';view.innerHTML=`
      <div class="section-head"><div><div class="eyebrow">PLAYER EXPERIENCE</div><h2>オンラインポーカー UX計測</h2><p>操作の遅さ・時間切れ・接続復旧・UI利用状況を匿名集計します。</p></div><div class="ux-range"><button class="soft active" data-ux-days="7">7日</button><button class="soft" data-ux-days="30">30日</button><button class="soft" id="uxRefresh">更新</button></div></div>
      <div class="ux-telemetry-note"><b>PRIVACY FIRST</b><span>ユーザーID・名前・ハンドID・カード・ベット額・チャット・自由入力文は保存しません。生イベントは30日で自動削除されます。</span></div>
      <div class="ux-kpi-grid">
        <article class="ux-kpi"><span>手動アクション選択</span><strong id="uxDecisions">—</strong><small>自分の手番→ボタン選択</small></article>
        <article class="ux-kpi"><span>平均選択時間</span><strong id="uxAverage">—</strong><small id="uxMedian">P50 —</small></article>
        <article class="ux-kpi"><span>P90選択時間</span><strong id="uxP90">—</strong><small>遅い10%の境界</small></article>
        <article class="ux-kpi"><span>時間切れ率</span><strong id="uxTimeoutRate">—</strong><small id="uxTimeoutCount">—</small></article>
        <article class="ux-kpi"><span>接続フォールバック</span><strong id="uxFallbacks">—</strong><small id="uxReconnects">—</small></article>
      </div>
      <div class="ux-grid">
        <article class="panel"><div class="panel-head"><div><div class="eyebrow">TREND</div><h3>日別プレイ状況</h3></div><span class="ux-live-dot">集計のみ</span></div><div id="uxTrend" class="ux-trend"></div></article>
        <article class="panel"><div class="panel-head"><div><div class="eyebrow">ACTIONS</div><h3>手動アクション構成</h3></div></div><div id="uxActions" class="ux-dist"></div></article>
      </div>
      <div class="ux-subgrid">
        <article class="panel"><div class="eyebrow">SIZING</div><h3>サイズ入力の使われ方</h3><div id="uxSizing" class="ux-dist"></div></article>
        <article class="panel"><div class="eyebrow">TOOLS</div><h3>補助UIの利用</h3><div id="uxTools" class="ux-dist"></div></article>
        <article class="panel"><div class="eyebrow">DEVICE</div><h3>端末区分</h3><div id="uxDevices" class="ux-dist"></div><div class="ux-privacy-list"><div><span>個人識別</span><b>保存しない</b></div><div><span>カード/ハンド</span><b>保存しない</b></div><div><span>保存期間</span><b>30日</b></div></div></article>
      </div>`;
    $('.main')?.appendChild(view);
  }
  function dist(el,rows){if(!el)return;const list=rows||[],max=Math.max(1,...list.map(x=>Number(x.count||0)));el.innerHTML=list.length?list.map(x=>`<div class="ux-dist-row"><span>${safe(labels[x.name]||x.name)}</span><span class="ux-dist-bar"><i style="width:${Math.max(4,Math.round(Number(x.count||0)/max*100))}%"></i></span><b>${fmt(x.count)}</b></div>`).join(''):'<div class="ux-empty">まだデータがありません。</div>'}
  function render(data){
    $('#uxDecisions').textContent=fmt(data.totals?.decisions||0);$('#uxAverage').textContent=data.decision_ms?.average==null?'—':`${fmt(data.decision_ms.average/1000)}秒`;$('#uxMedian').textContent=data.decision_ms?.p50==null?'P50 —':`P50 ${fmt(data.decision_ms.p50/1000)}秒`;$('#uxP90').textContent=data.decision_ms?.p90==null?'—':`${fmt(data.decision_ms.p90/1000)}秒`;$('#uxTimeoutRate').textContent=`${fmt(data.totals?.timeout_rate_pct||0)}%`;$('#uxTimeoutCount').textContent=`時間切れ ${fmt(data.totals?.timeouts||0)}件`;$('#uxFallbacks').textContent=fmt(data.totals?.fallbacks||0);$('#uxReconnects').textContent=`復旧 ${fmt(data.totals?.reconnects||0)}回`;
    dist($('#uxActions'),data.actions);dist($('#uxSizing'),data.sizing);
    const tools=[...(data.preactions||[]).map(x=>({...x,name:`pre:${x.name}`})),...(data.ui||[])],toolLabels={...labels,'pre:check':'先行: チェックのみ','pre:check_fold':'先行: チェック/フォールド'},box=$('#uxTools'),maxTools=Math.max(1,...tools.map(x=>Number(x.count||0)));
    box.innerHTML=tools.length?tools.map(x=>`<div class="ux-dist-row"><span>${safe(toolLabels[x.name]||x.name)}</span><span class="ux-dist-bar"><i style="width:${Math.max(4,Math.round(Number(x.count||0)/maxTools*100))}%"></i></span><b>${fmt(x.count)}</b></div>`).join(''):'<div class="ux-empty">まだデータがありません。</div>';
    dist($('#uxDevices'),data.devices);
    const trend=data.trend||[],max=Math.max(1,...trend.map(x=>Number(x.decisions||0)+Number(x.timeouts||0)));$('#uxTrend').innerHTML=trend.map(x=>{const n=Number(x.decisions||0)+Number(x.timeouts||0),label=x.date.slice(5).replace('-','/');return `<div class="ux-trend-row"><span>${safe(label)}</span><span class="ux-trend-track"><i style="width:${Math.round(n/max*100)}%"></i></span><b>${n}判断${x.timeouts?` · TO ${x.timeouts}`:''}</b></div>`}).join('')||'<div class="ux-empty">まだデータがありません。</div>';
  }
  async function load(){$('#uxRefresh')?.setAttribute('disabled','');try{render(await fetchSummary(currentDays))}catch(err){$('#uxTrend').innerHTML=`<div class="ux-empty">${safe(err.message)}</div>`}finally{$('#uxRefresh')?.removeAttribute('disabled')}}
  function activate(){$$('.view').forEach(v=>v.classList.toggle('active',v.id==='telemetryView'));$$('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view==='telemetry'));const title=$('#pageTitle');if(title)title.textContent='オンラインポーカー UX計測';history.replaceState(null,'','#telemetry');window.scrollTo({top:0,behavior:'smooth'});load()}
  ensureUi();document.addEventListener('click',e=>{const nav=e.target.closest('[data-view="telemetry"]');if(nav){e.preventDefault();activate();return}const range=e.target.closest('[data-ux-days]');if(range){currentDays=Number(range.dataset.uxDays||7);$$('[data-ux-days]').forEach(b=>b.classList.toggle('active',Number(b.dataset.uxDays)===currentDays));load();return}if(e.target.closest('#uxRefresh'))load()});if(location.hash==='#telemetry')activate();
})();
