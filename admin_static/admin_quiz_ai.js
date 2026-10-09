(()=>{
  const $=s=>document.querySelector(s);
  const safe=v=>String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  async function api(path,options={}){const res=await fetch('/api'+path,{credentials:'include',...options,headers:{'Content-Type':'application/json',...(options.headers||{})}});let data=null;try{data=await res.json()}catch{}if(!res.ok){const detail=data?.detail;const message=typeof detail==='string'?detail:Array.isArray(detail)?detail.map(item=>item?.msg||'').filter(Boolean).join(' / '):'';throw new Error(message||`HTTP ${res.status}`)}return data}
  async function load(){
    const rows=await api('/admin/console/quiz/questions');
    const box=$('#quizCustomList');if(!box)return;
    box.innerHTML=(rows||[]).map(x=>{const q=x.question||{};return `<div class="quiz-custom-item"><div><strong>${safe(q.prompt||'')}</strong><small>${safe(q.category_label||q.category||'')} · ${safe(x.source||'admin')} · ${x.enabled?'有効':'停止中'}<br>正解: ${safe((q.choices||[]).find(c=>c.value===q.correct)?.label||'—')}</small></div><button class="row-btn" data-quiz-toggle="${safe(x.id)}" data-quiz-enabled="${x.enabled?'1':'0'}">${x.enabled?'停止':'有効化'}</button></div>`}).join('')||'<div class="empty-state">追加問題はまだありません。</div>';
  }
  document.addEventListener('DOMContentLoaded',()=>{
    const form=$('#quizGptForm');
    form?.addEventListener('submit',async e=>{e.preventDefault();const button=form.querySelector('button[type="submit"]'),status=$('#quizGptStatus');button.disabled=true;status.textContent='GPTで問題を作成しています…';try{
      const category=$('#quizGptCategory').value;
      const payload={topic:$('#quizGptTopic').value.trim(),request_id:'quiz-ui-'+crypto.randomUUID()};
      if(category)payload.category=category;
      const d=await api('/admin/console/quiz/gpt-add',{method:'POST',body:JSON.stringify(payload)});
      status.textContent=`追加しました: ${d.question?.prompt||''}`;
      $('#quizGptTopic').value='';
      await load();
    }catch(err){status.textContent=err.message}finally{button.disabled=false}});
    document.addEventListener('click',async e=>{const btn=e.target.closest('[data-quiz-toggle]');if(!btn)return;btn.disabled=true;try{await api(`/admin/console/quiz/questions/${encodeURIComponent(btn.dataset.quizToggle)}`,{method:'PATCH',body:JSON.stringify({enabled:btn.dataset.quizEnabled!=='1'})});await load()}catch(err){$('#quizGptStatus').textContent=err.message}finally{btn.disabled=false}});
    load().catch(err=>{const s=$('#quizGptStatus');if(s)s.textContent=err.message});
  });
})();