(()=>{
  const $=(s,r=document)=>r.querySelector(s);
  const $$=(s,r=document)=>[...r.querySelectorAll(s)];
  let lastUserOpener=null;

  function enhanceToast(){
    const toast=$('#toast');
    if(!toast)return;
    toast.setAttribute('role','status');
    toast.setAttribute('aria-live','polite');
    toast.setAttribute('aria-atomic','true');
  }

  function enhanceMobileNav(){
    const nav=$('.mobile-nav');
    if(nav&&!$('.mobile-back-link',nav)){
      const link=document.createElement('a');
      link.href='/';
      link.className='mobile-back-link';
      link.textContent='← JJ Arena';
      link.setAttribute('aria-label','プレイヤーサイトへ戻る');
      nav.prepend(link);
    }
  }

  function updateNavA11y(){
    $$('[data-view]').forEach(el=>{
      const active=el.classList.contains('active');
      if(active)el.setAttribute('aria-current','page');
      else el.removeAttribute('aria-current');
    });
  }

  function enhanceUserToolbar(){
    const toolbar=$('#usersView .toolbar');
    const search=$('#userSearch');
    if(!toolbar||!search)return;
    search.setAttribute('aria-label','アカウントを検索');
    if(!$('#jjUserCount',toolbar)){
      const count=document.createElement('span');
      count.id='jjUserCount';
      count.className='admin-user-count';
      count.setAttribute('aria-live','polite');
      count.textContent='0件';
      toolbar.appendChild(count);
    }
    if(!$('#jjUserSearchClear',toolbar)){
      const clear=document.createElement('button');
      clear.id='jjUserSearchClear';
      clear.type='button';
      clear.className='admin-search-clear';
      clear.textContent='検索をクリア';
      clear.addEventListener('click',()=>{
        search.value='';
        search.dispatchEvent(new Event('input',{bubbles:true}));
        search.focus();
      });
      toolbar.appendChild(clear);
    }
    updateSearchUi();
  }

  function updateSearchUi(){
    const search=$('#userSearch');
    const clear=$('#jjUserSearchClear');
    if(clear)clear.classList.toggle('is-visible',Boolean(search?.value?.trim()));
  }

  function updateUserCount(){
    const count=$('#jjUserCount');
    if(!count)return;
    const cards=$$('#usersCards .user-card');
    const rows=$$('#usersBody tr').filter(row=>!row.querySelector('.empty-state'));
    const n=cards.length||rows.length;
    count.textContent=`表示 ${n}件`;
  }

  function enhanceDialog(){
    const dialog=$('#userDialog');
    const body=$('#userDialogBody');
    if(!dialog||!body)return;
    const title=$('h3',body);
    if(title){
      title.id='jjAdminUserDialogTitle';
      dialog.setAttribute('aria-labelledby',title.id);
    }
    dialog.setAttribute('aria-modal','true');
  }

  function boot(){
    document.documentElement.lang='ja';
    enhanceToast();
    enhanceMobileNav();
    enhanceUserToolbar();
    updateNavA11y();
    updateUserCount();

    const body=$('#userDialogBody');
    if(body)new MutationObserver(()=>{enhanceDialog();updateUserCount()}).observe(body,{childList:true,subtree:true});
    const users=$('#usersBody');
    if(users)new MutationObserver(updateUserCount).observe(users,{childList:true,subtree:true});
    const cards=$('#usersCards');
    if(cards)new MutationObserver(updateUserCount).observe(cards,{childList:true,subtree:true});

    document.addEventListener('input',e=>{if(e.target?.id==='userSearch')updateSearchUi()});
    document.addEventListener('click',e=>{
      const opener=e.target.closest?.('[data-user-edit]');
      if(opener)lastUserOpener=opener;
      if(e.target.closest?.('[data-view]'))queueMicrotask(updateNavA11y);
    });

    const dialog=$('#userDialog');
    if(dialog)dialog.addEventListener('close',()=>{
      if(lastUserOpener?.isConnected)lastUserOpener.focus({preventScroll:true});
    });
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});
  else boot();
})();
