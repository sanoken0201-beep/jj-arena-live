(()=>{
  const dialog=document.querySelector('#userDialog');
  const body=document.querySelector('#userDialogBody');
  const list=document.querySelector('#permanentBanList');
  if(!dialog||!body||!list)return;
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let active=[];
  let loading=null;

  async function request(path,options={}){
    const res=await fetch('/api/admin/console/'+path,{credentials:'include',headers:{'Content-Type':'application/json'},...options});
    const data=await res.json().catch(()=>({}));
    if(!res.ok)throw new Error(data?.detail||'操作できません (HTTP '+res.status+')');
    return data;
  }
  async function bans(){
    if(!loading)loading=request('permanent-bans').finally(()=>{loading=null});
    active=await loading;
    return active;
  }
  async function refresh(){
    try {
      const items=await bans();
      list.innerHTML=items.length ? items.map(b=>
        `<div class="ledger-item"><div><strong>${esc(b.display_name)}</strong>
        <p>ID ${Number(b.user_id)} · 登録名: ${esc(b.ranking_name)}${b.account_deleted_at?' · 削除済み':''}</p>
        <p>理由: ${esc(b.reason)}</p><p>BAN日時: ${esc(b.banned_at)} · 実施: ${esc(b.banned_by_name||'管理者')}</p></div>
        <div><button type="button" class="soft" data-lift-permanent-ban="${Number(b.id)}">BAN解除</button></div></div>`
      ).join('') : '<div class="empty-state">永久BAN中のアカウントはありません。</div>';
    } catch(err){list.textContent=err.message}
  }
  async function enhance(){
    const form=body.querySelector('#userEditForm');
    const actions=body.querySelector('.dialog-actions');
    const meta=body.querySelector('.dialog-meta');
    if(!form||!actions||actions.querySelector('[data-permanent-ban-controls]'))return;
    if((meta?.textContent||'').trim().toUpperCase().startsWith('ADMIN'))return;
    const uid=Number(form.dataset.userId||0);
    if(!uid)return;
    const container=document.createElement('div');
    container.dataset.permanentBanControls='1';
    container.style.width='100%';
    container.textContent='永久BAN状況を確認中…';
    actions.appendChild(container);
    try{
      const found=(await bans()).find(b=>Number(b.user_id)===uid);
      if(!body.contains(container))return;
      const resume=actions.querySelector('[data-toggle-disabled]');
      if(found){
        if(resume){resume.disabled=true;resume.textContent='永久BANのため通常の利用再開不可';}
        container.innerHTML=`<p class="field-note">永久BAN中 · 理由: ${esc(found.reason)}</p>
          <button class="ok-btn" type="button" data-lift-permanent-ban="${Number(found.id)}">永久BAN解除（管理者のみ）</button>
          <p class="field-note">解除してもアカウントは自動的に利用再開されません。</p>`;
      }else{
        container.innerHTML=`<button class="danger-btn" type="button" data-permanent-ban="${uid}">永久BAN</button>
          <p class="field-note">理由が必要です。既存セッションを失効させ、削除後も登録名・ランキング名の再利用を拒否します。異なる名前による再登録は本人審査が必要です。</p>`;
      }
    }catch(err){container.textContent=err.message}
  }
  new MutationObserver(enhance).observe(body,{childList:true,subtree:true});
  enhance();
  document.querySelector('#refreshPermanentBans')?.addEventListener('click',refresh);
  document.querySelectorAll('[data-view="users"]').forEach(b=>b.addEventListener('click',refresh));

  document.addEventListener('click',async e=>{
    const ban=e.target.closest('[data-permanent-ban]');
    if(ban){
      e.preventDefault();e.stopPropagation();
      const uid=Number(ban.dataset.permanentBan);
      const name=body.querySelector('h3')?.textContent?.trim()||'';
      if(!uid||!name)return;
      const match=prompt(`永久BANの対象「${name}」を確認します。対象のアカウント名をそのまま入力してください。`);
      if(match!==name)return;
      const reason=prompt('永久BANの理由を3文字以上入力してください（管理者の監査ログに保存）。');
      if(reason===null)return;
      if(reason.trim().length<3){alert('理由を3文字以上入力してください。');return}
      if(!confirm(`「${name}」を永久BANにします。セッションを失効させ、削除後も再登録名を禁止します。続行しますか？`))return;
      ban.disabled=true;
      try{
        await request('users/'+uid+'/permanent-ban',{method:'POST',body:JSON.stringify({reason:reason.trim()})});
        alert('永久BANを適用しました。');
        location.hash='#users';location.reload();
      }catch(err){ban.disabled=false;alert(err.message)}
      return;
    }
    const lift=e.target.closest('[data-lift-permanent-ban]');
    if(lift){
      e.preventDefault();e.stopPropagation();
      const id=Number(lift.dataset.liftPermanentBan);
      const target=active.find(b=>Number(b.id)===id);
      if(!target)return;
      const reason=prompt(`「${target.display_name}」の永久BAN解除理由を入力してください（3文字以上）。`);
      if(reason===null)return;
      if(reason.trim().length<3){alert('理由を3文字以上入力してください。');return}
      if(!confirm('永久BANを解除します。通常のアカウント停止は解除されません。よろしいですか？'))return;
      lift.disabled=true;
      try{
        await request('permanent-bans/'+id+'/lift',{method:'POST',body:JSON.stringify({reason:reason.trim()})});
        alert('永久BANを解除しました。アカウントの利用停止は維持されています。');
        location.hash='#users';location.reload();
      }catch(err){lift.disabled=false;alert(err.message)}
    }
  },true);
  refresh();
})();
