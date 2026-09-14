(()=>{
  const $=s=>document.querySelector(s);
  const fmt=n=>new Intl.NumberFormat('ja-JP',{maximumFractionDigits:2}).format(Number(n||0));
  const safe=v=>String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const dt=v=>{if(!v)return '—';const d=new Date(v);return Number.isNaN(d.getTime())?String(v):new Intl.DateTimeFormat('ja-JP',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}).format(d)};
  const bytes=n=>{n=Number(n);if(!Number.isFinite(n)||n<0)return '—';const units=['B','KB','MB','GB'];let i=0;while(n>=1024&&i<units.length-1){n/=1024;i++}return `${n.toFixed(i?1:0)} ${units[i]}`};
  const known=v=>v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v));
  const metric=v=>known(v)?fmt(v):'—';
  const ms=v=>known(v)?`${fmt(v)} ms`:'—';
  const level=(v,yellow,red)=>!known(v)?'unknown':Number(v)>red?'critical':Number(v)>yellow?'warning':'ok';
  const badge=s=>`<em class="ops-status">${({ok:'正常',warning:'注意',critical:'警告',unknown:'未計測',info:'参考'})[s]}</em>`;
  async function api(path){const r=await fetch('/api'+path,{credentials:'include',headers:{'Accept':'application/json'}});let d=null;try{d=await r.json()}catch{}if(!r.ok)throw new Error(d?.detail||`HTTP ${r.status}`);return d}

  function ensure(){
    const dash=$('#dashboardView');
    if(dash&&!$('#opsDashboard')){
      const box=document.createElement('div');box.id='opsDashboard';box.innerHTML=`
        <div class="ops-section-title"><div><div class="eyebrow">LIVE OPERATIONS</div><h3>利用状況・監査</h3></div><button id="opsRefresh" class="soft">更新</button></div>
        <div class="ops-kpis"><article class="panel ops-kpi"><span>7日アクティブ</span><strong id="opsActive">—</strong><small id="opsActiveRate">—</small></article><article class="panel ops-kpi"><span>今日のQuiz</span><strong id="opsQuiz">—</strong><small id="opsQuizUsers">—</small></article><article class="panel ops-kpi"><span>Online Poker</span><strong id="opsOnline">—</strong><small id="opsSeated">—</small></article><article class="panel ops-kpi"><span>異常ポイント</span><strong id="opsAnomaly">—</strong><small>直近8日を自動監査</small></article></div>
        <div class="ops-grid"><article class="panel"><div class="panel-head"><div><div class="eyebrow">POINT WATCH</div><h3>ポイント異常検知</h3></div><span class="immutable">AUTO AUDIT</span></div><div id="opsAnomalies" class="ops-list"></div></article><article class="panel"><div class="panel-head"><div><div class="eyebrow">SYSTEM</div><h3>システム状態</h3></div></div><div id="opsHealth" class="ops-health"></div><div class="panel-head" style="margin-top:16px"><div><div class="eyebrow">RECENT ERRORS</div><h3>直近エラー</h3></div></div><div id="opsErrors" class="ops-list"></div></article></div>`;
      const old=dash.querySelector('.dashboard-grid');old?.insertAdjacentElement('afterend',box);
      $('#opsRefresh')?.addEventListener('click',loadAll);
    }
    const points=$('#pointsView');
    if(points&&!$('#opsLedgerAudit')){
      const panel=document.createElement('article');panel.id='opsLedgerAudit';panel.className='panel ops-ledger-audit';panel.innerHTML=`<div class="panel-head"><div><div class="eyebrow">COMPLETE LEDGER</div><h3>全ポイント監査台帳</h3><p>クイズ報酬を含む、全てのポイント変動を表示します。</p></div><div class="ops-ledger-toolbar"><select id="opsLedgerKind"><option value="">全種類</option><option value="quiz_reward">quiz_reward</option><option value="credit">credit</option><option value="collection">collection</option><option value="reversal">reversal</option></select><button id="opsLedgerRefresh" class="soft">更新</button></div></div><div id="opsLedgerRows"></div>`;
      points.appendChild(panel);$('#opsLedgerRefresh')?.addEventListener('click',loadLedger);$('#opsLedgerKind')?.addEventListener('change',loadLedger);
    }
  }

  function renderOps(o,r){
    $('#opsActive').textContent=fmt(o.activity?.active_7d||0);$('#opsActiveRate').textContent=`有効アカウントの ${fmt(o.activity?.active_rate_7d||0)}%`;
    $('#opsQuiz').textContent=fmt(o.quiz?.answers_today||0);$('#opsQuizUsers').textContent=`${fmt(o.quiz?.users_today||0)}人 · 7日 ${fmt(o.quiz?.answers_7d||0)}回答`;
    $('#opsOnline').textContent=`${fmt(o.online?.hands_7d||0)} hands`;$('#opsSeated').textContent=`7日 ${fmt(o.online?.users_7d||0)}人 · 現在着席 ${fmt(o.online?.seated_now||0)}人`;
    const a=o.anomalies||[];$('#opsAnomaly').textContent=fmt(a.length);
    $('#opsAnomalies').innerHTML=a.length?a.map(x=>`<div class="ops-row"><strong><span class="ops-severity ${safe(x.severity)}">${safe(x.severity)}</span>${safe(x.user_name)}</strong><p>${safe(x.detail)}<br><span class="ops-muted">${safe(x.code)}</span></p><time>${dt(x.detected_at)}</time></div>`).join(''):'<div class="ops-empty">現在、quiz_rewardの異常は検出されていません。</div>';
    const db=o.database||{},acc=o.accounts||{},pt=o.points||{},rt=r?.runtime||{},lat=rt.api_latency||{},ws=rt.websocket||{},pool=rt.db_pool||{};
    const latencyLevel=Number(lat.samples)>0?level(lat.p95_ms,500,1000):'unknown';
    const poolLevel=pool.backend==='sqlite'?'info':pool.active?level(pool.requests_waiting,0,Infinity):'unknown';
    const errorLevel=level(r?.errors_24h,0,Infinity);
    const wsLevel=known(ws.connections)?'info':'unknown';
    const wsTables=Object.entries(ws.by_table||{}).map(([k,v])=>`${safe(k)} ${fmt(v)}`).join(' · ')||'接続なし';
    const poolTitle=pool.backend==='sqlite'?'SQLite':pool.active?`${metric(pool.pool_available)} / ${metric(pool.pool_size)} available`:'初期化待ち';
    const poolDetail=pool.backend==='sqlite'?'ローカルDB':pool.active?`待機 ${metric(pool.requests_waiting)} · max ${metric(pool.pool_max)}`:'PostgreSQL pool';
    $('#opsHealth').innerHTML=`<div><span>アカウント</span><b>${fmt(acc.enabled)} 利用中</b><small>停止 ${fmt(acc.disabled)} · 削除済 ${fmt(acc.deleted)}</small></div><div><span>7日ポイント変動</span><b>${Number(pt.net_7d||0)>=0?'+':''}${fmt(pt.net_7d)} pt</b><small>Quiz +${fmt(pt.quiz_points_7d)} · ${fmt(pt.transactions_7d)}件</small></div><div class="${db.warning?'ops-db-warning':''}"><span>Database</span><b>${bytes(db.size_bytes)}</b><small>${db.usage_percent==null?`${safe(db.engine||'db')} · 容量上限未設定`:`使用率 ${fmt(db.usage_percent)}%`}</small></div><div><span>Table backups</span><b>${fmt(r?.backups||0)} copies</b><small>${fmt(r?.keep_per_table||0)}世代 / table</small></div><div class="ops-state-${latencyLevel}"><span>API latency ${badge(latencyLevel)}</span><b>P95 ${ms(lat.p95_ms)}</b><small>P50 ${ms(lat.p50_ms)} · ${fmt(lat.samples||0)}/${fmt(lat.window||0)} samples · 500ms超で注意 / 1000ms超で警告</small></div><div class="ops-state-${wsLevel}"><span>WebSocket ${badge(wsLevel)}</span><b>${metric(ws.connections)} connections</b><small>${wsTables}</small></div><div class="ops-state-${poolLevel}"><span>DB pool ${badge(poolLevel)}</span><b>${poolTitle}</b><small>${poolDetail} · 待機1件以上で注意</small></div><div class="ops-state-${errorLevel}"><span>24時間エラー ${badge(errorLevel)}</span><b>${metric(r?.errors_24h)} 件</b><small>1件以上で注意 · 下の履歴を確認</small></div><div><span>Event loop</span><b>${ms(rt.event_loop_probe_ms)}</b><small>現在の yield probe</small></div>`;
    const errors=r?.recent_errors||[];$('#opsErrors').innerHTML=errors.length?errors.map(x=>`<div class="ops-row"><strong>${safe(x.event_type)}</strong><p>${safe((x.path||'')+(x.detail?` · ${x.detail}`:''))}</p><time>${dt(x.created_at)}</time></div>`).join(''):'<div class="ops-empty">記録された直近エラーはありません。</div>';
  }

  async function loadAll(){ensure();if(!$('#opsDashboard'))return;try{const [o,r]=await Promise.all([api('/admin/console/operations'),api('/admin/console/resilience')]);renderOps(o,r)}catch(e){if($('#opsHealth'))$('#opsHealth').innerHTML=`<div class="ops-state-warning" role="status"><b>監視情報を更新できません</b><small>現在の状態は不明です。再取得してください。</small></div>`;if($('#opsAnomalies'))$('#opsAnomalies').innerHTML=`<div class="ops-empty">${safe(e.message)}</div>`}}
  async function loadLedger(){ensure();if(!$('#opsLedgerRows'))return;const kind=$('#opsLedgerKind')?.value||'';try{const rows=await api(`/admin/console/ledger-audit?limit=200${kind?`&kind=${encodeURIComponent(kind)}`:''}`);$('#opsLedgerRows').innerHTML=rows.length?rows.map(x=>`<div class="ops-ledger-item"><div><strong>${safe(x.user_name)}${x.deleted_at?' · 削除済':''}</strong><p>${safe(x.ranking_name||'')} · ${safe(x.kind)}</p></div><div><strong>${safe(x.reason)}</strong><p>反映 ${dt(x.effective_at)} · 記録 ${dt(x.created_at)} · ${safe(x.actor_name||'system')}</p></div><div class="amount ${Number(x.amount)>=0?'positive':'negative'}">${Number(x.amount)>=0?'+':''}${fmt(x.amount)} pt</div></div>`).join(''):'<div class="ops-empty">該当する台帳記録はありません。</div>'}catch(e){$('#opsLedgerRows').innerHTML=`<div class="ops-empty">${safe(e.message)}</div>`}}

  document.addEventListener('DOMContentLoaded',()=>{ensure();loadAll();document.querySelectorAll('[data-view="dashboard"]').forEach(b=>b.addEventListener('click',()=>setTimeout(loadAll,0)));document.querySelectorAll('[data-view="points"]').forEach(b=>b.addEventListener('click',()=>setTimeout(loadLedger,0)));setInterval(()=>{if($('#dashboardView')?.classList.contains('active'))loadAll()},60000)});
})();
