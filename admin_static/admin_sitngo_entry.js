(()=>{
  let snapshot={events:[],defaults:null};
  const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
  const originalFetch=window.fetch.bind(window);

  function values(){
    const late=Number($('#sngLateRegistrationMinutes')?.value||0);
    const reentries=Number($('#sngMaxReentries')?.value||0);
    if(!Number.isInteger(late)||late<0||late>60)throw new Error('開始後受付時間は0〜60分の整数で設定してください');
    if(!Number.isInteger(reentries)||reentries<0||reentries>5)throw new Error('リエントリー回数は0〜5回の整数で設定してください');
    if(reentries>0&&late===0)throw new Error('リエントリーを許可する場合は開始後受付時間を1分以上にしてください');
    return {late_registration_minutes:late,max_reentries:reentries};
  }

  function decorate(){
    const cards=$$('#sngEventList .sng-event');
    cards.forEach((card,index)=>{
      const event=(snapshot.events||[])[index];if(!event)return;
      const meta=card.querySelector('.sng-event-meta');
      if(meta&&!meta.querySelector('[data-sng-entry-policy]')){
        const span=document.createElement('span');span.dataset.sngEntryPolicy='1';
        span.textContent=Number(event.late_registration_minutes||0)>0?`開始後受付 ${event.late_registration_minutes}分`:'定刻締切';
        const re=document.createElement('span');re.dataset.sngEntryPolicy='1';
        re.textContent=Number(event.max_reentries||0)>0?`リエントリー ${event.max_reentries}回/人`:'リエントリーなし';
        meta.append(span,re);
      }
    });
  }

  function ensureControls(){
    if($('#sngLateRegistrationMinutes'))return;
    const editor=$('.sng-config-editor');if(!editor)return;
    const structure=editor.querySelector('.sng-structure-head');if(!structure)return;
    structure.insertAdjacentHTML('beforebegin',`<div class="sng-entry-policy-editor"><label>開始後受付（分）<input id="sngLateRegistrationMinutes" type="number" min="0" max="60" step="1" value="0" inputmode="numeric"><small>0なら定刻で締切。1〜60なら空き枠へ途中参加できます。</small></label><label>最大リエントリー / 人<input id="sngMaxReentries" type="number" min="0" max="5" step="1" value="0" inputmode="numeric"><small>0ならfreezeout。敗退後、受付時間内のみ再参加できます。</small></label></div>`);
  }

  window.fetch=async(input,init={})=>{
    const url=typeof input==='string'?input:input?.url||'';
    const method=String(init?.method||'GET').toUpperCase();
    const isAdmin=/\/api\/admin\/sitngo(?:\/[^/?#]+)?(?:[?#]|$)/.test(url);
    if(isAdmin&&(method==='POST'||method==='PATCH')&&init.body){
      const body=JSON.parse(String(init.body));Object.assign(body,values());init={...init,body:JSON.stringify(body)};
    }
    const response=await originalFetch(input,init);
    if(url.includes('/api/admin/sitngo')&&method==='GET'&&response.ok){
      response.clone().json().then(data=>{snapshot=data||snapshot;queueMicrotask(()=>{ensureControls();decorate()})}).catch(()=>{});
    }
    if(isAdmin&&method==='POST'&&response.ok){
      setTimeout(()=>{const a=$('#sngLateRegistrationMinutes'),b=$('#sngMaxReentries');if(a)a.value=String(snapshot.defaults?.late_registration_minutes||0);if(b)b.value=String(snapshot.defaults?.max_reentries||0)},0);
    }
    return response;
  };

  document.addEventListener('click',e=>{
    const edit=e.target.closest('[data-sng-edit]');if(!edit)return;
    const event=(snapshot.events||[]).find(x=>x.id===edit.dataset.sngEdit);if(!event)return;
    setTimeout(()=>{ensureControls();const a=$('#sngLateRegistrationMinutes'),b=$('#sngMaxReentries');if(a)a.value=String(event.late_registration_minutes||0);if(b)b.value=String(event.max_reentries||0)},0);
  },true);

  document.addEventListener('DOMContentLoaded',()=>{
    setTimeout(()=>{ensureControls();const a=$('#sngLateRegistrationMinutes'),b=$('#sngMaxReentries');if(a)a.value=String(snapshot.defaults?.late_registration_minutes||0);if(b)b.value=String(snapshot.defaults?.max_reentries||0);decorate()},0);
    const host=$('#sngEventList');if(host)new MutationObserver(decorate).observe(host,{childList:true,subtree:true});
  });
})();
