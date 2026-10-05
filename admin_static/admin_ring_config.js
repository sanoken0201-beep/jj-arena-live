(()=>{
  const $=s=>document.querySelector(s);
  const safe=v=>String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const fmt=n=>new Intl.NumberFormat('ja-JP',{maximumFractionDigits:2}).format(Number(n||0));
  const dt=v=>{if(!v)return '—';const d=new Date(v);return Number.isNaN(d.getTime())?String(v):new Intl.DateTimeFormat('ja-JP',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}).format(d)};
  async function api(path,options={}){const res=await fetch('/api'+path,{credentials:'include',...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});let data=null;try{data=await res.json()}catch{}if(!res.ok)throw new Error(typeof data?.detail==='string'?data.detail:`HTTP ${res.status}`);return data}

  async function loadConfig(){
    const d=await api('/admin/console/ring-config');
    $('#ringMinBuyin').value=d.min_buyin_bb;
    $('#ringMaxBuyin').value=d.max_buyin_bb;
    $('#ringRakePercent').value=d.rake_percent;
    $('#ringRakeCap').value=d.rake_cap_bb;
    $('#ringReentryLimit').value=d.daily_reentry_limit;
    $('#ringConfigStatus').textContent=`現在: ${d.min_buyin_bb}–${d.max_buyin_bb}bb buy-in · rake ${fmt(d.rake_percent)}% / ${fmt(d.rake_cap_bb)}bb cap · 1日 ${d.daily_reentry_limit}回まで`;
  }

  async function loadUsage(){
    const d=await api('/admin/console/ring-reentries');
    const body=$('#ringReentryBody'); if(!body)return;
    body.innerHTML=(d.items||[]).map(x=>`<tr><td><strong>${safe(x.ranking_name||x.name)}</strong><br><small>ID ${x.user_id}</small></td><td>${x.used} / ${x.limit}</td><td>${x.remaining}</td><td>${dt(x.last_reset_at)}</td><td><button class="row-btn" data-ring-reset="${x.user_id}" data-ring-name="${safe(x.ranking_name||x.name)}">当日回数をリセット</button></td></tr>`).join('')||'<tr><td colspan="5" class="empty-state">本日のオンライン卓参加記録はありません。</td></tr>';
  }

  async function loadRake(){
    const d=await api('/admin/console/ring-rake'),cur=d.current||{},all=d.all_time||{},last=d.last_reset;
    $('#ringRakeCurrentPoints').textContent=fmt(cur.rake_points)+' 点';
    $('#ringRakeCurrentBb').textContent=fmt(cur.rake_bb)+' BB';
    $('#ringRakeAllTimePoints').textContent=fmt(all.rake_points)+' 点';
    $('#ringRakeMeta').textContent=(last?`最終リセット ${dt(last.created_at)} · ${fmt(last.settled_rake_points)}点を精算`:'まだリセット履歴はありません')+` · 未精算 ${fmt(cur.hands)}ハンド`;
    $('#ringRakeReset').disabled=Number(cur.rake_points||0)<=0;
    return d;
  }

  async function refresh(){await Promise.all([loadConfig(),loadUsage(),loadRake()])}

  document.addEventListener('DOMContentLoaded',()=>{
    const form=$('#ringConfigForm');
    if(form)form.addEventListener('submit',async e=>{
      e.preventDefault();
      const button=form.querySelector('button[type="submit"]');
      const body={
        min_buyin_bb:Number($('#ringMinBuyin').value),
        max_buyin_bb:Number($('#ringMaxBuyin').value),
        rake_percent:Number($('#ringRakePercent').value),
        rake_cap_bb:Number($('#ringRakeCap').value),
        daily_reentry_limit:Number($('#ringReentryLimit').value)
      };
      if(body.min_buyin_bb>body.max_buyin_bb){$('#ringConfigStatus').textContent='ミニマムバイインはMAXバイイン以下にしてください';return}
      if(!confirm(`オンライン卓を ${body.min_buyin_bb}–${body.max_buyin_bb}bb / rake ${fmt(body.rake_percent)}%・${fmt(body.rake_cap_bb)}bb cap / 1日${body.daily_reentry_limit}回 に変更しますか？`))return;
      button.disabled=true;
      try{
        const d=await api('/admin/console/ring-config',{method:'PATCH',body:JSON.stringify(body)});
        $('#ringConfigStatus').textContent=`保存済み: ${d.min_buyin_bb}–${d.max_buyin_bb}bb buy-in · rake ${fmt(d.rake_percent)}% / ${fmt(d.rake_cap_bb)}bb cap · 1日 ${d.daily_reentry_limit}回まで。既存スタックは変更しません。`;
        await loadUsage();
      }catch(err){$('#ringConfigStatus').textContent=err.message}finally{button.disabled=false}
    });

    $('#ringRakeReset')?.addEventListener('click',async()=>{
      let d;
      try{d=await loadRake()}catch(err){alert(err.message);return}
      const points=Number(d?.current?.rake_points||0);
      if(points<=0)return alert('未精算のレーキはありません');
      if(!confirm(`未精算レーキ ${fmt(points)}点をオフラインでレーキバック済みとしてリセットしますか？履歴は保持されます。`))return;
      const note=prompt('精算メモ','オフライン活動でレーキバック');
      if(note===null)return;
      const button=$('#ringRakeReset');button.disabled=true;
      try{
        await api('/admin/console/ring-rake/reset',{method:'POST',body:JSON.stringify({note:note.trim()||'オフライン活動でレーキバック'})});
        await loadRake();
      }catch(err){alert(err.message);await loadRake().catch(()=>{})}
    });

    $('#refreshRingReentries')?.addEventListener('click',()=>Promise.all([loadUsage(),loadRake()]).catch(err=>{const el=$('#ringConfigStatus');if(el)el.textContent=err.message}));
    document.addEventListener('click',async e=>{const btn=e.target.closest('[data-ring-reset]');if(!btn)return;const name=btn.dataset.ringName||'このユーザー';if(!confirm(`${name} の本日のリエントリー使用回数を0回に戻しますか？履歴は保持されます。`))return;const reason=prompt('リセット理由','運営判断による当日回数リセット');if(reason===null)return;btn.disabled=true;try{await api(`/admin/console/ring-reentries/${btn.dataset.ringReset}/reset`,{method:'POST',body:JSON.stringify({reason:reason.trim()||'管理者による当日リエントリー回数リセット'})});await loadUsage()}catch(err){alert(err.message)}finally{btn.disabled=false}});
    refresh().catch(err=>{const el=$('#ringConfigStatus');if(el)el.textContent=err.message});
  });
})();