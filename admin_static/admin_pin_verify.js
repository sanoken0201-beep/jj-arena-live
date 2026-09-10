(()=>{
  const $=(s,r=document)=>r.querySelector(s);
  const safe=v=>String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

  function notice(message,ok=true){
    const toast=$('#toast');
    if(toast){
      toast.textContent=message;
      toast.classList.add('show');
      toast.dataset.pinResult=ok?'ok':'error';
      clearTimeout(toast._pinTimer);
      toast._pinTimer=setTimeout(()=>{toast.classList.remove('show');delete toast.dataset.pinResult},3000);
      return;
    }
    window.alert(message);
  }

  async function api(path,options={}){
    const res=await fetch('/api'+path,{
      credentials:'include',
      ...options,
      headers:{'Content-Type':'application/json',...(options.headers||{})},
    });
    let data=null;
    try{data=await res.json()}catch{}
    if(!res.ok){
      if(res.status===401){location.href='/';throw new Error('ログインが必要です')}
      throw new Error(data?.detail||`HTTP ${res.status}`);
    }
    return data;
  }

  function decorateUserDialog(){
    const body=$('#userDialogBody');
    if(!body)return;
    const editForm=$('#userEditForm',body);
    const actions=$('.dialog-actions',body);
    const uid=editForm?.dataset?.userId;
    if(!uid||!actions)return;

    const existing=$('[data-admin-pin-verify-panel]',body);
    if(existing?.dataset.adminPinVerifyPanel===String(uid))return;
    existing?.remove();

    const panel=document.createElement('section');
    panel.className='admin-pin-verify-panel';
    panel.dataset.adminPinVerifyPanel=String(uid);
    panel.innerHTML=`
      <div class="admin-pin-verify-copy">
        <div class="eyebrow">LOGIN SECURITY</div>
        <strong>PIN確認</strong>
        <p>現在のPINそのものは表示できません。プレイヤーから申告された6桁PINが登録内容と一致するか、管理者だけが照合できます。</p>
      </div>
      <form class="admin-pin-verify-form" data-admin-pin-verify-form="${safe(uid)}" autocomplete="off">
        <label>確認する6桁PIN
          <input name="pin" type="password" inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" autocomplete="new-password" required placeholder="••••••">
        </label>
        <button class="soft" type="submit">一致を確認</button>
      </form>
      <div class="admin-pin-verify-result" data-admin-pin-verify-result aria-live="polite"></div>`;
    actions.insertAdjacentElement('afterend',panel);
  }

  const target=$('#userDialogBody');
  if(target){
    new MutationObserver(decorateUserDialog).observe(target,{childList:true,subtree:true});
    decorateUserDialog();
  }

  document.addEventListener('submit',async event=>{
    const form=event.target.closest('[data-admin-pin-verify-form]');
    if(!form)return;
    event.preventDefault();
    event.stopImmediatePropagation();

    const uid=Number(form.dataset.adminPinVerifyForm||0);
    const input=$('input[name="pin"]',form);
    const button=$('button[type="submit"]',form);
    const result=$('[data-admin-pin-verify-result]',form.parentElement);
    const pin=String(input?.value||'').trim();
    if(!/^\d{6}$/.test(pin))return notice('PINは6桁の数字で入力してください',false);

    try{
      if(button){button.disabled=true;button.textContent='確認中…'}
      if(result){result.textContent='';result.classList.remove('match','mismatch')}
      const data=await api(`/admin/console/users/${uid}/verify-pin`,{
        method:'POST',
        body:JSON.stringify({pin}),
      });
      if(input)input.value='';
      const message=data.matches?'一致しました。このPINでログインできます。':'一致しません。登録中のPINとは異なります。';
      if(result){result.textContent=message;result.classList.add(data.matches?'match':'mismatch')}
      notice(message,Boolean(data.matches));
    }catch(err){
      if(input)input.value='';
      if(result){result.textContent=err.message;result.classList.add('mismatch')}
      notice(err.message,false);
    }finally{
      if(button){button.disabled=false;button.textContent='一致を確認'}
    }
  },true);
})();
