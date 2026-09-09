(()=>{
  const body=document.querySelector('#userDialogBody');
  const dialog=document.querySelector('#userDialog');
  if(!body||!dialog)return;

  function enhance(){
    const form=body.querySelector('#userEditForm');
    const actions=body.querySelector('.dialog-actions');
    const meta=body.querySelector('.dialog-meta');
    if(!form||!actions||actions.querySelector('[data-account-delete]'))return;
    if((meta?.textContent||'').trim().toUpperCase().startsWith('ADMIN'))return;
    const id=Number(form.dataset.userId||0);
    if(!id)return;
    const btn=document.createElement('button');
    btn.type='button';
    btn.className='danger-btn';
    btn.dataset.accountDelete=String(id);
    btn.textContent='アカウント削除';
    actions.appendChild(btn);
    const note=document.createElement('p');
    note.className='field-note';
    note.style.width='100%';
    note.textContent='削除は取り消せません。削除後はユーザー管理一覧から除外され、ログイン情報は無効化されます。ランキング・ポイント・監査履歴は整合性維持のため保存します。同じ名前で再登録した場合は、新しいアカウントIDとそのとき設定したPINで作成されます。';
    actions.appendChild(note);
  }

  new MutationObserver(enhance).observe(body,{childList:true,subtree:true});
  enhance();

  document.addEventListener('click',async e=>{
    const btn=e.target.closest('[data-account-delete]');
    if(!btn)return;
    e.preventDefault();
    e.stopPropagation();
    const id=Number(btn.dataset.accountDelete||0);
    const name=(body.querySelector('h3')?.textContent||'').trim();
    if(!id||!name)return;
    const typed=prompt(`この操作は取り消せません。\n削除確認のため、アカウント名「${name}」をそのまま入力してください。`);
    if(typed===null)return;
    if(typed!==name){alert('アカウント名が一致しないため削除しませんでした。');return;}
    if(!confirm(`「${name}」を削除します。既存セッションは失効し、このアカウントでは再ログインできなくなります。同名で再登録する場合は新しいアカウントとして扱われます。実行しますか？`))return;
    btn.disabled=true;
    btn.textContent='削除中…';
    try{
      const res=await fetch(`/api/admin/console/users/${id}`,{method:'DELETE',credentials:'include',headers:{'Content-Type':'application/json'}});
      let data=null;try{data=await res.json()}catch{}
      if(!res.ok)throw new Error(data?.detail||`HTTP ${res.status}`);
      dialog.close();
      alert('アカウントを削除しました。ユーザー管理一覧から除外されます。ランキング・ポイント・監査履歴は保持されています。');
      location.hash='#users';
      location.reload();
    }catch(err){
      btn.disabled=false;
      btn.textContent='アカウント削除';
      alert(err.message||'削除に失敗しました。');
    }
  },true);
})();
