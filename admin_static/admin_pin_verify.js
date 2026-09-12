(()=>{
  const $=(s,r=document)=>r.querySelector(s);

  function decorateUserDialog(){
    const body=$('#userDialogBody');
    if(!body)return;
    const editForm=$('#userEditForm',body);
    const actions=$('.dialog-actions',body);
    const uid=editForm?.dataset?.userId;
    if(!uid||!actions)return;

    const existing=$('[data-admin-pin-security-note]',body);
    if(existing?.dataset.adminPinSecurityNote===String(uid))return;
    existing?.remove();

    const panel=document.createElement('section');
    panel.className='admin-pin-verify-panel';
    panel.dataset.adminPinSecurityNote=String(uid);
    panel.innerHTML=`
      <div class="admin-pin-verify-copy">
        <div class="eyebrow">LOGIN SECURITY</div>
        <strong>PINは照合できません</strong>
        <p>管理者を含め、登録済みPINの候補照合はできません。本人がPINを利用できない場合は、管理画面のPINリセットを利用してください。</p>
      </div>`;
    actions.insertAdjacentElement('afterend',panel);
  }

  const target=$('#userDialogBody');
  if(target){
    new MutationObserver(decorateUserDialog).observe(target,{childList:true,subtree:true});
    decorateUserDialog();
  }
})();