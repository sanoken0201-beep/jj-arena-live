(()=>{
  const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
  const safe=v=>String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const fmt=n=>new Intl.NumberFormat('ja-JP').format(Number(n||0));
  const dt=v=>{if(!v)return '—';const d=new Date(v);return Number.isNaN(d.getTime())?String(v):new Intl.DateTimeFormat('ja-JP',{year:'numeric',month:'2-digit',day:'2-digit',weekday:'short',hour:'2-digit',minute:'2-digit'}).format(d)};
  const localInput=v=>{const d=new Date(v);if(Number.isNaN(d.getTime()))return '';d.setMinutes(d.getMinutes()-d.getTimezoneOffset());return d.toISOString().slice(0,16)};
  const statusText={scheduled:'受付前',registration_open:'受付中',starting:'開始処理中',running:'開催中',finished:'終了',cancelled:'中止'};
  const fallbackStructure=[
    {level:1,small_blind:200,big_blind:400,bb_ante:400,minutes:10},{level:2,small_blind:300,big_blind:600,bb_ante:600,minutes:10},
    {level:3,small_blind:500,big_blind:1000,bb_ante:1000,minutes:10},{level:4,small_blind:700,big_blind:1400,bb_ante:1400,minutes:10},
    {level:5,small_blind:1000,big_blind:2000,bb_ante:2000,minutes:10},{level:6,small_blind:1500,big_blind:3000,bb_ante:3000,minutes:10},
    {level:7,small_blind:2000,big_blind:4000,bb_ante:4000,minutes:10},{level:8,small_blind:3000,big_blind:6000,bb_ante:6000,minutes:10},
    {level:9,small_blind:5000,big_blind:10000,bb_ante:10000,minutes:10},{level:10,small_blind:8000,big_blind:16000,bb_ante:16000,minutes:10},
    {level:11,small_blind:10000,big_blind:20000,bb_ante:20000,minutes:10},{level:12,small_blind:15000,big_blind:30000,bb_ante:30000,minutes:10},
    {level:13,small_blind:20000,big_blind:40000,bb_ante:40000,minutes:10},{level:14,small_blind:30000,big_blind:60000,bb_ante:60000,minutes:10},
    {level:15,small_blind:40000,big_blind:80000,bb_ante:80000,minutes:10}
  ];
  let data={events:[],defaults:null},telemetry=null,poll=null,toastTimer=null,editingId=null,editorInitialized=false;
  function toast(msg){const el=$('#toast');if(!el)return;el.textContent=msg;el.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.remove('show'),2800)}
  async function api(path,options={}){const opts={credentials:'include',...options,headers:{...(options.body?{'Content-Type':'application/json'}:{}),...(options.headers||{})}};const res=await fetch('/api'+path,opts);let body=null;try{body=await res.json()}catch{}if(!res.ok){if(res.status===401){location.href='/';throw new Error('ログインが必要です')}throw new Error(Array.isArray(body?.detail)?body.detail.map(x=>x.msg).join(' / '):(body?.detail||`HTTP ${res.status}`))}return body}
  const post=(p,b)=>api(p,{method:'POST',body:JSON.stringify(b??{})}),patch=(p,b)=>api(p,{method:'PATCH',body:JSON.stringify(b??{})});
  function defaultStart(){const d=new Date(Date.now()+2*60*60*1000);d.setMinutes(Math.ceil(d.getMinutes()/10)*10,0,0);return localInput(d)}
  function cloneLevels(levels){return (levels||[]).map((x,i)=>({level:i+1,small_blind:Number(x.small_blind),big_blind:Number(x.big_blind),bb_ante:Number(x.bb_ante),minutes:Number(x.minutes)}))}
  const defaultPayouts=()=>Object.fromEntries([2,3,4,5,6].map(n=>[String(n),Array.from({length:n},(_,i)=>n===6?(i===0?70:i===1?30:0):(i===0?100:0))]));
  function renderPoints(fee=0,rates=defaultPayouts(),locked=false){
    $('#sngPointSettings').innerHTML=`<label>参加費（pt）<input id="sngEntryFee" type="number" min="0" max="1000000" step="0.01" value="${Number(fee)}" ${locked?'disabled':''} required></label><details><summary>開催人数別のプライズ配分（%）</summary>${[2,3,4,5,6].map(n=>`<fieldset><legend>${n}人開催・合計100%</legend><div class="sng-payout-row">${rates[String(n)].map((v,i)=>`<label>${i+1}位<input data-sng-payout="${n}" type="number" min="0" max="100" step="0.01" value="${Number(v)}" ${locked?'disabled':''} required></label>`).join('')}</div></fieldset>`).join('')}</details><p class="field-note">0%は賞金なし。参加費全額を配分します。登録時に徴収、開始前の取消・中止で返却。${locked?'参加履歴があるため参加費・配当率は変更できません。':'参加登録後は参加費・配当率を変更できません。'}</p>`;
  }
  function readPoints(){
    const payout_percentages=Object.fromEntries([2,3,4,5,6].map(n=>[String(n),$$(`[data-sng-payout="${n}"]`).map(x=>x.value)]));
    for(const [n,rates] of Object.entries(payout_percentages))if(rates.some(x=>x===''||!Number.isFinite(Number(x))||Number(x)<0||Number(x)>100)||rates.reduce((a,v)=>a+Math.round(Number(v)*100),0)!==10000)throw new Error(`${n}人開催の配当率を合計100%にしてください`);
    return {entry_fee:$('#sngEntryFee').value,payout_percentages};
  }
  function pointSummary(e){return `<p>参加費 ${fmt(e.entry_fee)} pt · 賞金総額 ${fmt(e.prize_points)} pt</p><details><summary>プライズ配分</summary>${Object.entries(e.payout_percentages||defaultPayouts()).map(([n,r])=>`<p>${safe(n)}人：${r.map((v,i)=>`${i+1}位 ${safe(v)}%`).join(' / ')}</p>`).join('')}</details>`}
  function ensureEditor(){
    const form=$('#sngCreateForm');if(!form||$('#sngStructureEditor'))return;
    const note=form.querySelector('.field-note');
    note.insertAdjacentHTML('beforebegin',`<section class="sng-config-editor"><div class="sng-config-head"><div><b>トーナメント設定</b><small>大会開始後は変更できません</small></div></div><label>初期スタック<input id="sngStartingStack" type="number" min="1000" max="10000000" step="100" inputmode="numeric" value="30000" required></label><div class="sng-structure-head"><div><b>ブラインドストラクチャー</b><small>SB / BB / BBAを大会ごとに設定 · ブラインドは12ハンドごとに上昇</small></div><button id="sngAddLevel" type="button" class="soft">＋ レベル追加</button></div><div class="sng-level-editor-head"><span>Lv</span><span>SB</span><span>BB</span><span>BBA</span><span>進行</span><span></span></div><div id="sngStructureEditor" class="sng-level-editor"></div><p class="field-note compact">各レベル12ハンド固定です。最終レベル到達後は、そのレベルを大会終了まで継続します。チップ値は100点単位です。</p></section>`);
    note.textContent='受付は開始1時間前から自動で開きます。定刻時点で2〜6人なら開始、1人以下なら自動中止します。受付中でも設定変更は可能ですが、開始後は完全にロックされます。';
    note.insertAdjacentHTML('beforebegin','<section id="sngPointSettings"></section>');renderPoints();
    const submit=form.querySelector('button[type="submit"]');submit.id='sngSubmit';
    submit.insertAdjacentHTML('afterend','<button id="sngCancelEdit" class="soft full" type="button" hidden>編集をやめる</button>');
  }
  function renderEditor(levels){
    ensureEditor();const host=$('#sngStructureEditor');if(!host)return;
    const list=cloneLevels(levels?.length?levels:fallbackStructure);
    host.innerHTML=list.map((x,i)=>`<div class="sng-level-row" data-sng-level-row="${i}"><strong>Lv.${i+1}</strong><label><span>SB</span><input type="number" min="100" max="100000000" step="100" value="${x.small_blind}" data-sng-field="small_blind" required></label><label><span>BB</span><input type="number" min="100" max="100000000" step="100" value="${x.big_blind}" data-sng-field="big_blind" required></label><label><span>BBA</span><input type="number" min="0" max="100000000" step="100" value="${x.bb_ante}" data-sng-field="bb_ante" required></label><label><span>進行</span><input type="text" value="12ハンド" disabled aria-label="12ハンド固定"></label><input type="hidden" value="10" data-sng-field="minutes"><button type="button" class="sng-remove-level" data-sng-remove-level="${i}" aria-label="Lv.${i+1}を削除" ${list.length<=1?'disabled':''}>×</button></div>`).join('');
  }
  function addLevel(){
    const current=readEditor(false),last=current[current.length-1]||{small_blind:200,big_blind:400,bb_ante:400,minutes:10};
    if(current.length>=30)return toast('ブラインドレベルは最大30個です');
    current.push({...last,level:current.length+1});renderEditor(current);
  }
  function readEditor(validate=true){
    const rows=$$('[data-sng-level-row]'),levels=rows.map((row,i)=>{const get=k=>Number(row.querySelector(`[data-sng-field="${k}"]`)?.value);return {level:i+1,small_blind:get('small_blind'),big_blind:get('big_blind'),bb_ante:get('bb_ante'),minutes:get('minutes')}});
    if(!validate)return levels;
    if(!levels.length)throw new Error('ブラインドレベルを1つ以上設定してください');
    if(levels.length>30)throw new Error('ブラインドレベルは最大30個です');
    let prior=null,total=0;
    for(const x of levels){
      if(![x.small_blind,x.big_blind,x.bb_ante,x.minutes].every(Number.isFinite))throw new Error(`Lv.${x.level}の値をすべて入力してください`);
      if(x.small_blind<100||x.big_blind<=x.small_blind)throw new Error(`Lv.${x.level}はSB < BBになるよう設定してください`);
      if(x.bb_ante<0)throw new Error(`Lv.${x.level}のBBAは0以上にしてください`);
      if([x.small_blind,x.big_blind,x.bb_ante].some(v=>v%100!==0))throw new Error(`Lv.${x.level}のチップ値は100点単位にしてください`);
      if(x.minutes<1||x.minutes>60||!Number.isInteger(x.minutes))throw new Error(`Lv.${x.level}の時間は1〜60分の整数にしてください`);
      if(prior&&(x.small_blind<prior.small_blind||x.big_blind<prior.big_blind||x.bb_ante<prior.bb_ante))throw new Error(`Lv.${x.level}は前レベルよりブラインド/アンティを下げられません`);
      total+=x.minutes;prior=x;
    }
    if(total>600)throw new Error('ストラクチャー合計は600分以内にしてください');
    return levels;
  }
  function collectConfig(){
    const starting_stack=Number($('#sngStartingStack')?.value);if(!Number.isInteger(starting_stack)||starting_stack<1000||starting_stack>10000000||starting_stack%100!==0)throw new Error('初期スタックは1,000〜10,000,000点の100点単位で設定してください');
    const structure=readEditor(true);if(structure[0].big_blind>=starting_stack)throw new Error('Lv.1のBBは初期スタックより小さくしてください');
    return {starting_stack,structure,...readPoints()};
  }
  function renderStructure(levels,targetMinutes){return `<details class="sng-structure-admin"><summary>ブラインドストラクチャー</summary><div class="sng-structure-grid">${(levels||[]).map(x=>`<div><b>Lv.${x.level} · ${fmt(x.small_blind)}/${fmt(x.big_blind)}</b><small>BBA ${fmt(x.bb_ante)} · 12ハンド</small></div>`).join('')}</div></details>`}
  function statusClass(status){return status==='registration_open'?'open':status==='running'?'running':status==='cancelled'?'cancelled':''}
  const telemetryLabels={missing_tokens:'token不足',duplicate_action:'重複action',stale_hand:'古いhand',stale_turn:'古いturn',late_action:'deadline超過',timeout_boundary_protected:'境界競合を保護',timeout_auto_action:'自動timeout',restart_recovery:'再起動復旧'};
  function renderTelemetry(){
    const host=$('#sngTelemetry');if(!host)return;
    if(!telemetry){host.innerHTML='<div class="empty-state">安全イベントを読み込めませんでした。</div>';return}
    const totals=telemetry.totals||{},days=Number(telemetry.window_days||7);
    host.innerHTML='<div class="sng-telemetry-grid">'+Object.entries(telemetryLabels).map(([key,label])=>'<div><span>'+safe(label)+'</span><b>'+fmt(totals[key]||0)+'</b><small>件 / '+days+'日</small></div>').join('')+'</div><p class="field-note compact">個人ID・大会ID・hand ID・カード・チップ量・IP・session・自由記述は保存しません。</p>';
  }
  async function loadTelemetry(){try{telemetry=await api('/admin/sitngo/telemetry?days=7')}catch{telemetry=null}renderTelemetry()}
  function render(){
    ensureEditor();
    const host=$('#sngEventList');if(!host)return;
    const events=data.events||[];
    host.innerHTML=events.length?events.map(e=>{
      const editable=['scheduled','registration_open'].includes(e.status),deletable=['scheduled','cancelled'].includes(e.status)&&!(e.participants||[]).length;
      const participants=(e.participants||[]).filter(x=>x.status!=='cancelled');
      return `<article class="sng-event ${editingId===e.id?'editing':''}"><div class="sng-event-head"><div><div class="eyebrow">${safe(e.id.slice(0,12))}</div><h4>${safe(e.name)}</h4></div><span class="sng-status ${statusClass(e.status)}">${safe(statusText[e.status]||e.status)}</span></div><div class="sng-event-meta"><span>開始 ${safe(dt(e.starts_at))}</span><span>受付 ${safe(dt(e.registration_opens_at))}</span><span>参加 ${e.participant_count}/${e.max_players}</span><span>初期 ${fmt(e.starting_stack)}点</span><span>進行 12ハンド/Lv</span></div>${participants.length?`<div class="sng-participants">${participants.map(p=>`<span>${p.seat===null||p.seat===undefined?`#${p.registration_order}`:`Seat ${Number(p.seat)+1}`} · ${safe(p.name)}</span>`).join('')}</div>`:''}${pointSummary(e)}${renderStructure(e.structure,e.target_minutes)}<div class="sng-event-actions">${editable?`<button type="button" class="soft" data-sng-edit="${safe(e.id)}">大会設定を編集</button><button type="button" class="danger-btn" data-sng-admin-cancel="${safe(e.id)}">大会を中止</button>`:''}${deletable?`<button type="button" class="soft" data-sng-delete="${safe(e.id)}">削除</button>`:''}</div></article>`;
    }).join(''):'<div class="empty-state">まだSit&Goは設定されていません。</div>';
    const d=data.defaults;if(d){
      const rules=$('#sngFixedRules');if(rules)rules.innerHTML=`<div><span>定員</span><b>${d.max_players}人 / 最少${d.min_players}人</b></div><div><span>新規初期値</span><b>${fmt(d.starting_stack)}点</b></div><div><span>構造</span><b>大会ごとに設定</b></div><div><span>受付</span><b>開始1時間前</b></div><div><span>ブラインド上昇</span><b>12ハンドごと</b></div><div><span>開始後</span><b>設定ロック</b></div>`;
      const structure=$('#sngStructure');if(structure)structure.innerHTML=`<div class="sng-default-label">新規大会の標準ストラクチャー</div>${renderStructure(d.structure,d.target_minutes)}`;
      if(!editorInitialized&&!editingId){$('#sngStartingStack').value=d.starting_stack;renderEditor(d.structure);editorInitialized=true}
    }
  }
  async function load(){const [eventsResult]=await Promise.all([api('/admin/sitngo'),loadTelemetry()]);data=eventsResult;render()}
  function beginEdit(id){
    const e=(data.events||[]).find(x=>x.id===id);if(!e)return;
    editingId=id;ensureEditor();renderPoints(e.entry_fee,e.payout_percentages,!e.points_editable);$('#sngName').value=e.name;$('#sngStartsAt').value=localInput(e.starts_at);$('#sngStartingStack').value=e.starting_stack;renderEditor(e.structure);$('#sngSubmit').textContent='変更を保存';$('#sngCancelEdit').hidden=false;render();$('#sngCreateForm').scrollIntoView({behavior:'smooth',block:'start'});
  }
  function endEdit(reset=true){
    editingId=null;renderPoints();const form=$('#sngCreateForm');if(reset&&form){$('#sngName').value='JJ Sit&Go';$('#sngStartsAt').value=defaultStart();$('#sngStartingStack').value=data.defaults?.starting_stack||30000;renderEditor(data.defaults?.structure||fallbackStructure)}$('#sngSubmit').textContent='開催を設定';$('#sngCancelEdit').hidden=true;render();
  }
  function activate(){
    $$('.view').forEach(v=>v.classList.toggle('active',v.id==='sitngoView'));
    $$('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view==='sitngo'));
    const title=$('#pageTitle');if(title)title.textContent='Sit&Go開催管理';
    history.replaceState(null,'','#sitngo');
    load().catch(e=>toast(e.message));
    clearInterval(poll);poll=setInterval(()=>{if(location.hash==='#sitngo')load().catch(()=>{})},15000);
    window.scrollTo({top:0,behavior:'smooth'});
  }
  document.addEventListener('click',async e=>{
    const view=e.target.closest('[data-view]');if(view){if(view.dataset.view==='sitngo'){e.preventDefault();activate();return}if($('#sitngoView')?.classList.contains('active')){$('#sitngoView').classList.remove('active');clearInterval(poll);poll=null}}
    const refreshTelemetry=e.target.closest('#sngRefreshTelemetry');if(refreshTelemetry){refreshTelemetry.disabled=true;try{await loadTelemetry()}finally{refreshTelemetry.disabled=false}return}
    const add=e.target.closest('#sngAddLevel');if(add){addLevel();return}
    const remove=e.target.closest('[data-sng-remove-level]');if(remove){const levels=readEditor(false);if(levels.length<=1)return;levels.splice(Number(remove.dataset.sngRemoveLevel),1);renderEditor(levels);return}
    const edit=e.target.closest('[data-sng-edit]');if(edit){beginEdit(edit.dataset.sngEdit);return}
    const cancelEdit=e.target.closest('#sngCancelEdit');if(cancelEdit){endEdit(true);return}
    const cancel=e.target.closest('[data-sng-admin-cancel]');if(cancel){if(!confirm('このSit&Goを中止しますか？ 参加登録もすべて取消扱いになります。'))return;const reason=prompt('中止理由','運営により中止')||'運営により中止';try{await post(`/admin/sitngo/${encodeURIComponent(cancel.dataset.sngAdminCancel)}/cancel`,{reason});toast('大会を中止しました');if(editingId===cancel.dataset.sngAdminCancel)endEdit(true);await load()}catch(err){toast(err.message)}return}
    const del=e.target.closest('[data-sng-delete]');if(del){if(!confirm('参加履歴のない開催設定を削除します。続行しますか？'))return;try{await api(`/admin/sitngo/${encodeURIComponent(del.dataset.sngDelete)}`,{method:'DELETE'});toast('開催設定を削除しました');await load()}catch(err){toast(err.message)}}
  });
  document.addEventListener('DOMContentLoaded',()=>{
    const form=$('#sngCreateForm');if(!form)return;ensureEditor();
    const starts=$('#sngStartsAt');if(starts&&!starts.value)starts.value=defaultStart();
    form.addEventListener('submit',async e=>{e.preventDefault();const name=$('#sngName').value.trim()||'JJ Sit&Go',raw=$('#sngStartsAt').value,d=new Date(raw);if(Number.isNaN(d.getTime()))return toast('開催日時を入力してください');let config;try{config=collectConfig()}catch(err){return toast(err.message)}const button=$('#sngSubmit');button.disabled=true;try{const payload={name,starts_at:d.toISOString(),...config};if(editingId){await patch(`/admin/sitngo/${encodeURIComponent(editingId)}`,payload);toast('大会設定を更新しました');endEdit(true)}else{await post('/admin/sitngo',payload);toast('Sit&Goを設定しました');renderPoints();$('#sngName').value='JJ Sit&Go';$('#sngStartsAt').value=defaultStart();$('#sngStartingStack').value=data.defaults?.starting_stack||30000;renderEditor(data.defaults?.structure||fallbackStructure)}await load()}catch(err){toast(err.message)}finally{button.disabled=false}});
    if(location.hash==='#sitngo')activate();
  });
})();

// jj sng admin 12-hand levels 2026-09-18
