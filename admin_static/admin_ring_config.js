(()=>{
  const $=s=>document.querySelector(s);
  const safe=v=>String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const fmt=n=>new Intl.NumberFormat('ja-JP',{maximumFractionDigits:2}).format(Number(n||0));
  const dt=v=>{if(!v)return '—';const d=new Date(v);return Number.isNaN(d.getTime())?String(v):new Intl.DateTimeFormat('ja-JP',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}).format(d)};
  async function api(path,options={}){const res=await fetch('/api'+path,{credentials:'include',...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});let data=null;try{data=await res.json()}catch{}if(!res.ok)throw new Error(typeof data?.detail==='string'?data.detail:`HTTP ${res.status}`);return data}
  async function loadConfig(){
    const d=await api('/admin/console/ring-config');
    $('#ringRakePercent').value=d.rake_percent;
    $('#ringRakeCap').value=d.rake_cap_bb;
    $('#ringReentryLimit').value=d.daily_reentry_limit;
    $('#ringConfigStatus').textContent=`現在: rake ${fmt(d.rake_percent)}% / ${fmt(d.rake_cap_bb)}bb cap · 1日 ${d.daily_reentry_limit}回まで`;
  }
  async function loadUsage(){
    const d=await api('/admin/console/ring-reentries');
    const body=$('#ringReentryBody'); if(!body)return;
    body.innerHTML=(d.items||[]).map(x=>`<tr><td><strong>${safe(x.ranking_name||x.name)}</strong><br><small>ID ${x.user_id}</small></td><td>${x.used} / ${x.limit}</td><td>${x.remaining}</td><td>${dt(x.last_reset_at)}</td><td><button class="row-btn" data-ring-reset="${x.user_id}" data-ring-name="${safe(x.ranking_name||x.name)}">当日回数をリセット</button></td></tr>`).join('')||'<tr><td colspan="5" class="empty-state">本日のオンライン卓参加記録はありません。</td></tr>';
  }
  async function refresh(){await Promise.all([loadConfig(),loadUsage()])}
  document.addEventListener('DOMContentLoaded',()=>{
    const form=$('#ringConfigForm');
    if(form)form.addEventListener('submit',async e=>{e.preventDefault();const button=form.querySelector('button[type="submit"]');button.disabled=true;try{
      const d=await api('/admin/console/ring-config',{method:'PATCH',body:JSON.stringify({
        rake_percent:Number($('#ringRakePercent').value),
        rake_cap_bb:Number($('#ringRakeCap').value),
        daily_reentry_limit:Number($('#ringReentryLimit').value)
      })});
      $('#ringConfigStatus').textContent=`保存済み: rake ${fmt(d.rake_percent)}% / ${fmt(d.rake_cap_bb)}bb cap · 1日 ${d.daily_reentry_limit}回まで。進行中ハンドは旧設定のままです。`;
      await loadUsage();
    }catch(err){$('#ringConfigStatus').textContent=err.message}finally{button.disabled=false}});
    $('#refreshRingReentries')?.addEventListener('click',()=>loadUsage().catch(err=>{const el=$('#ringConfigStatus');if(el)el.textContent=err.message}));
    document.addEventListener('click',async e=>{const btn=e.target.closest('[data-ring-reset]');if(!btn)return;const name=btn.dataset.ringName||'このユーザー';if(!confirm(`${name} の本日のリエントリー使用回数を0回に戻しますか？履歴は保持されます。`))return;const reason=prompt('リセット理由','運営判断による当日回数リセット');if(reason===null)return;btn.disabled=true;try{await api(`/admin/console/ring-reentries/${btn.dataset.ringReset}/reset`,{method:'POST',body:JSON.stringify({reason:reason.trim()||'管理者による当日リエントリー回数リセット'})});await loadUsage()}catch(err){alert(err.message)}finally{btn.disabled=false}});
    refresh().catch(err=>{const el=$('#ringConfigStatus');if(el)el.textContent=err.message});
  });
})();