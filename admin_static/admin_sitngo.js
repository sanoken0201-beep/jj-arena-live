(()=>{
  const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
  const safe=v=>String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const fmt=n=>new Intl.NumberFormat('ja-JP').format(Number(n||0));
  const dt=v=>{if(!v)return '—';const d=new Date(v);return Number.isNaN(d.getTime())?String(v):new Intl.DateTimeFormat('ja-JP',{year:'numeric',month:'2-digit',day:'2-digit',weekday:'short',hour:'2-digit',minute:'2-digit'}).format(d)};
  const localInput=v=>{const d=new Date(v);if(Number.isNaN(d.getTime()))return '';d.setMinutes(d.getMinutes()-d.getTimezoneOffset());return d.toISOString().slice(0,16)};
  const statusText={scheduled:'受付前',registration_open:'受付中',starting:'開始処理中',running:'開催中',finished:'終了',cancelled:'中止'};
  let data={events:[],defaults:null},poll=null,toastTimer=null;
  function toast(msg){const el=$('#toast');if(!el)return;el.textContent=msg;el.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.remove('show'),2800)}
  async function api(path,options={}){const opts={credentials:'include',...options,headers:{...(options.body?{'Content-Type':'application/json'}:{}),...(options.headers||{})}};const res=await fetch('/api'+path,opts);let body=null;try{body=await res.json()}catch{}if(!res.ok){if(res.status===401){location.href='/';throw new Error('ログインが必要です')}throw new Error(body?.detail||`HTTP ${res.status}`)}return body}
  const post=(p,b)=>api(p,{method:'POST',body:JSON.stringify(b??{})}),patch=(p,b)=>api(p,{method:'PATCH',body:JSON.stringify(b??{})});
  function defaultStart(){const d=new Date(Date.now()+2*60*60*1000);d.setMinutes(Math.ceil(d.getMinutes()/10)*10,0,0);return localInput(d)}
  function activate(){
    $$('.view').forEach(v=>v.classList.toggle('active',v.id==='sitngoView'));
    $$('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view==='sitngo'));
    const title=$('#pageTitle');if(title)title.textContent='Sit&Go開催管理';
    history.replaceState(null,'','#sitngo');
    load().catch(e=>toast(e.message));
    clearInterval(poll);poll=setInterval(()=>{if(location.hash==='#sitngo')load().catch(()=>{})},15000);
    window.scrollTo({top:0,behavior:'smooth'});
  }
  function renderStructure(levels){return `<details class="sng-structure-admin"><summary>固定ブラインドストラクチャー</summary><div class="sng-structure-grid">${(levels||[]).map(x=>`<div><b>Lv.${x.level} · ${fmt(x.small_blind)}/${fmt(x.big_blind)}</b><small>BBA ${fmt(x.bb_ante)} · ${x.minutes}分${Number(x.level)===9?' · 90分':''}</small></div>`).join('')}</div></details>`}
  function statusClass(status){return status==='registration_open'?'open':status==='running'?'running':status==='cancelled'?'cancelled':''}
  function render(){
    const host=$('#sngEventList');if(!host)return;
    const events=data.events||[];
    host.innerHTML=events.length?events.map(e=>{
      const editable=['scheduled','registration_open'].includes(e.status),deletable=['scheduled','cancelled'].includes(e.status)&&!(e.participants||[]).length;
      const participants=(e.participants||[]).filter(x=>x.status!=='cancelled');
      return `<article class="sng-event"><div class="sng-event-head"><div><div class="eyebrow">${safe(e.id.slice(0,12))}</div><h4>${safe(e.name)}</h4></div><span class="sng-status ${statusClass(e.status)}">${safe(statusText[e.status]||e.status)}</span></div><div class="sng-event-meta"><span>開始 ${safe(dt(e.starts_at))}</span><span>受付 ${safe(dt(e.registration_opens_at))}</span><span>参加 ${e.participant_count}/${e.max_players}</span></div>${participants.length?`<div class="sng-participants">${participants.map(p=>`<span>${p.seat===null||p.seat===undefined?`#${p.registration_order}`:`Seat ${Number(p.seat)+1}`} · ${safe(p.name)}</span>`).join('')}</div>`:''}<div class="sng-event-actions">${editable?`<button type="button" class="soft" data-sng-edit="${safe(e.id)}">日時・名称を変更</button><button type="button" class="danger-btn" data-sng-admin-cancel="${safe(e.id)}">大会を中止</button>`:''}${deletable?`<button type="button" class="soft" data-sng-delete="${safe(e.id)}">削除</button>`:''}</div></article>`;
    }).join(''):'<div class="empty-state">まだSit&Goは設定されていません。</div>';
    const d=data.defaults;if(d){
      const rules=$('#sngFixedRules');if(rules)rules.innerHTML=`<div><span>定員</span><b>${d.max_players}人 / 最少${d.min_players}人</b></div><div><span>スタック</span><b>${fmt(d.starting_stack)}点</b></div><div><span>レベル</span><b>${d.level_minutes}分固定</b></div><div><span>アンティ</span><b>BB Ante</b></div><div><span>受付</span><b>開始1時間前</b></div><div><span>終了目標</span><b>${d.target_minutes}分</b></div>`;
      const structure=$('#sngStructure');if(structure)structure.innerHTML=renderStructure(d.structure);
    }
  }
  async function load(){data=await api('/admin/sitngo');render()}
  async function editEvent(id){
    const e=(data.events||[]).find(x=>x.id===id);if(!e)return;
    const name=prompt('大会名',e.name);if(name===null)return;
    const starts=prompt('開催日時（YYYY-MM-DDTHH:MM）',localInput(e.starts_at));if(starts===null)return;
    const d=new Date(starts);if(Number.isNaN(d.getTime()))return toast('開催日時の形式が不正です');
    await patch(`/admin/sitngo/${encodeURIComponent(id)}`,{name:name.trim()||'JJ Sit&Go',starts_at:d.toISOString()});toast('開催設定を更新しました');await load();
  }
  document.addEventListener('click',async e=>{
    const view=e.target.closest('[data-view]');if(view){if(view.dataset.view==='sitngo'){e.preventDefault();activate();return}if($('#sitngoView')?.classList.contains('active')){$('#sitngoView').classList.remove('active');clearInterval(poll);poll=null}}
    const edit=e.target.closest('[data-sng-edit]');if(edit){try{await editEvent(edit.dataset.sngEdit)}catch(err){toast(err.message)}return}
    const cancel=e.target.closest('[data-sng-admin-cancel]');if(cancel){if(!confirm('このSit&Goを中止しますか？ 参加登録もすべて取消扱いになります。'))return;const reason=prompt('中止理由','運営により中止')||'運営により中止';try{await post(`/admin/sitngo/${encodeURIComponent(cancel.dataset.sngAdminCancel)}/cancel`,{reason});toast('大会を中止しました');await load()}catch(err){toast(err.message)}return}
    const del=e.target.closest('[data-sng-delete]');if(del){if(!confirm('参加履歴のない開催設定を削除します。続行しますか？'))return;try{await api(`/admin/sitngo/${encodeURIComponent(del.dataset.sngDelete)}`,{method:'DELETE'});toast('開催設定を削除しました');await load()}catch(err){toast(err.message)}}
  });
  document.addEventListener('DOMContentLoaded',()=>{
    const form=$('#sngCreateForm');if(!form)return;
    const starts=$('#sngStartsAt');if(starts&&!starts.value)starts.value=defaultStart();
    form.addEventListener('submit',async e=>{e.preventDefault();const name=$('#sngName').value.trim()||'JJ Sit&Go',raw=$('#sngStartsAt').value,d=new Date(raw);if(Number.isNaN(d.getTime()))return toast('開催日時を入力してください');const button=form.querySelector('button[type="submit"]');button.disabled=true;try{await post('/admin/sitngo',{name,starts_at:d.toISOString()});toast('Sit&Goを設定しました');form.reset();$('#sngName').value='JJ Sit&Go';$('#sngStartsAt').value=defaultStart();await load()}catch(err){toast(err.message)}finally{button.disabled=false}});
    if(location.hash==='#sitngo')activate();
  });
})();
