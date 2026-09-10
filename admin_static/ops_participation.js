(()=>{
  let observer=null;
  async function refresh(){
    const label=document.getElementById('opsActiveRate');
    if(!label)return;
    try{
      const response=await fetch('/api/admin/console/operations',{credentials:'include',headers:{Accept:'application/json'}});
      if(!response.ok)return;
      const data=await response.json();
      const activity=data.activity||{};
      const participants=Number(activity.participants_7d||0);
      const rate=Number(activity.active_rate_7d||0);
      label.textContent=`サークル参加 ${participants.toLocaleString('ja-JP')}人 · 有効アカウントの ${rate.toLocaleString('ja-JP',{maximumFractionDigits:1})}%`;
    }catch{}
  }
  function bind(){
    const active=document.getElementById('opsActive');
    if(!active||active.dataset.participationBound==='1')return;
    active.dataset.participationBound='1';
    observer=new MutationObserver(()=>queueMicrotask(refresh));
    observer.observe(active,{childList:true,characterData:true,subtree:true});
    refresh();
  }
  document.addEventListener('DOMContentLoaded',()=>{setTimeout(bind,0);setInterval(bind,2000)});
})();
