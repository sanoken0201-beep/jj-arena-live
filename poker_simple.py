from __future__ import annotations

"""Simple live-table presentation and client action acknowledgement recovery.
Applied only to compiled assets, after all existing transforms.
"""
MARKER = "v70 simple poker table and action recovery"
HELPERS = r'''  // v70 simple poker table and action recovery
  function jjV7HeroMarkup(hero,l){
    const cards=(hero?.cards||[]).map(cardHTML).join('');
    const timebank=Math.max(0,Number(hero?.timebank_cards_remaining??3));
    return '<div class="jj-v7-hero-strip"><div class="jj-v7-hand" aria-label="自分の手札">'+(cards||'<span class="hint">手札待ち</span>')+'</div><div class="jj-v7-stack"><span>持ち点</span><strong>'+safe(bb(hero?.stack||0))+'</strong></div><div class="jj-v7-timebank" aria-label="タイムバンク残り"><span>TIME BANK</span><strong>×'+timebank+'</strong></div><strong id="jjActionClock" class="jj-action-clock" aria-live="polite"></strong></div>';
  }
  function jjV7Chrome(){
    const active=!!currentTableId&&!!tableState;
    document.body.classList.toggle('jj-poker-simple',active);
    if(!active)return;
    const head=$('#pokerRoom .room-head');if(!head)return;
    let menu=$('#jjV7Menu',head);
    if(!menu){head.insertAdjacentHTML('beforeend','<details id="jjV7Menu" class="jj-v7-menu"><summary aria-label="卓メニュー">メニュー</summary><div class="jj-v7-menu-items"></div></details>');menu=$('#jjV7Menu',head)}
    const items=$('.jj-v7-menu-items',menu);
    ['#jjPokerSettings','#jjV4MobileTools','#jjSoundToggle','#jjFocusModeToggle'].forEach(selector=>{
      const el=$(selector);if(el&&!items.contains(el))items.appendChild(el);
    });
  }
  document.addEventListener('click',e=>{
    const menu=$('#jjV7Menu');
    if(menu?.open&&(!menu.contains(e.target)||e.target.closest('button')))menu.open=false;
  });
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){const menu=$('#jjV7Menu');if(menu)menu.open=false;jjV4CloseSide()}});
'''
CSS = r'''
/* v70 simple poker table and action recovery */
body.jj-poker-simple .sidebar,body.jj-poker-simple .topbar{display:none!important}
body.jj-poker-simple .main{margin-left:0!important;max-width:none!important}
body.jj-poker-simple #pokerRoom .room-head{display:flex!important;align-items:center!important;flex-wrap:nowrap!important;gap:10px!important;height:auto!important;min-height:44px!important;margin:0!important;padding:4px 10px!important;background:#07100d!important;color:#eef5f1!important}
body.jj-poker-simple #pokerRoom .room-head>.room-meta{margin-left:auto!important;font-size:11px!important}
body.jj-poker-simple #pokerRoom .room-head .eyebrow{display:none!important}
body.jj-poker-simple #pokerRoom .room-head h3{font-size:15px!important;margin:0!important}
body.jj-poker-simple #pokerRoom #backLobby{min-height:36px!important;padding:0 10px!important;font-size:12px!important}
body.jj-poker-simple #pokerRoom .jj-v7-menu{position:relative;margin-left:auto;flex:0 0 auto;color:#eaf2ee}
body.jj-poker-simple #pokerRoom .jj-v7-menu summary{cursor:pointer;min-height:36px;display:flex;align-items:center;padding:0 10px;border:1px solid #43564c;border-radius:8px;font-size:12px;list-style:none}
body.jj-poker-simple #pokerRoom .jj-v7-menu-items{position:absolute;right:0;top:calc(100% + 6px);width:230px;max-height:65dvh;overflow:auto;z-index:220;display:grid;gap:8px;padding:12px;background:#14231b;border:1px solid #43564c;border-radius:12px;box-shadow:0 8px 30px #0008}
body.jj-poker-simple #pokerRoom .jj-v7-menu:not([open]) .jj-v7-menu-items{display:none!important}
body.jj-poker-simple #pokerRoom .jj-v7-menu button{margin:0!important;min-height:40px!important;width:100%;color:#eaf2ee!important;background:#23352b!important;font-size:12px!important}
body.jj-poker-simple #pokerRoom .jj-v4-mobile-tools{display:flex!important;gap:6px!important;margin:0!important}
body.jj-poker-simple #pokerRoom .poker-layout{display:block!important}
body.jj-poker-simple #pokerRoom .table-side{display:none!important}
body.jj-poker-simple.jj-v4-side-open #pokerRoom .table-side{display:flex!important;position:fixed!important;z-index:230!important;left:auto!important;right:12px!important;top:64px!important;bottom:auto!important;width:min(380px,calc(100vw - 24px))!important;max-height:70dvh!important;height:auto!important;overflow:auto!important;background:#14231b!important}
body.jj-poker-simple.jj-v4-side-open:after{display:none!important}
body.jj-poker-simple.jj-v4-side-open #pokerRoom:after{content:'';position:fixed;inset:0;z-index:205;background:#02070599}
body.jj-poker-simple #pokerRoom .jj-v4-side-head{display:flex!important;justify-content:space-between;align-items:center}
body.jj-poker-simple #pokerRoom .jj-seat.is-hero .jj-hole{display:none!important}
body.jj-poker-simple #actionBar{position:relative!important;inset:auto!important;overflow:visible!important;max-height:none!important;box-shadow:none!important}
body.jj-poker-simple #actionBar .jj-v123-action-status:not(.is-pending),
body.jj-poker-simple #actionBar .jj-v123-disabled-hints,
body.jj-poker-simple #actionBar .jj-v124-waiting,
body.jj-poker-simple #actionBar .jj-v5-preactions>span,
body.jj-poker-simple #actionBar .jj-v5-preactions>small{display:none!important}
body.jj-poker-simple #actionBar .jj-v7-hero-strip{display:flex!important;align-items:center;gap:12px;min-height:54px;margin:0 0 5px;color:#eaf2ee}
body.jj-poker-simple #actionBar .jj-v7-hand{display:flex;align-items:center;gap:4px;flex:0 0 auto}
body.jj-poker-simple #actionBar .jj-v7-hand .card-face{display:inline-flex!important;position:relative!important;inset:auto!important;transform:none!important;opacity:1!important;width:36px!important;height:48px!important;min-height:48px!important;font-size:17px!important;border-radius:6px!important}
body.jj-poker-simple #actionBar .jj-v7-stack span{display:block;color:#a9bbb1;font-size:10px}
body.jj-poker-simple #actionBar .jj-v7-stack strong{font-size:15px}
body.jj-poker-simple #actionBar .jj-v7-timebank{display:flex;align-items:baseline;gap:5px;padding:4px 7px;border:1px solid #43564c;border-radius:8px}
body.jj-poker-simple #actionBar .jj-v7-timebank span{font-size:9px;color:#a9bbb1;letter-spacing:.04em}
body.jj-poker-simple #actionBar .jj-v7-timebank strong{font-size:14px}
body.jj-poker-simple #actionBar .jj-action-clock{margin-left:auto!important;font-size:12px!important}
body.jj-poker-simple #actionBar .jj-main-actions .jj-action-btn>small{display:none!important}
body.jj-poker-simple #actionBar .jj-main-actions .jj-confirm-allin>small{display:block!important}
body.jj-poker-simple #actionBar .jj-v124-stepper input{width:100%!important;min-width:0!important;min-height:36px!important;height:36px!important;border:0!important;background:transparent!important;color:white!important;font-size:16px!important;text-align:center!important;padding:0 3px!important}
body.jj-poker-simple #actionBar #jjV124SizingError:empty{display:none!important}
body.jj-poker-simple #jjConnectionStatus:not(.is-degraded){display:none!important}
body.jj-poker-simple #tableControls .jj-ready-count{display:none!important}
body.jj-poker-simple #resultBanner:not(.hidden){position:relative!important;inset:auto!important;margin:0!important;max-width:none!important;width:auto!important;flex:0 0 auto!important}
@media(min-width:761px){
 body.jj-poker-simple .main{padding:8px 16px!important}
 body.jj-poker-simple #pokerRoom{max-width:1120px!important;margin:0 auto!important}
 body.jj-poker-simple #pokerTable{height:clamp(290px,calc(100dvh - 310px),560px)!important}
 body.jj-poker-simple #pokerRoom .room-head{position:relative!important;z-index:220!important}
 body.jj-poker-simple #actionBar{padding:8px 12px!important;margin:0!important}
 body.jj-poker-simple #actionBar .jj-action-btn{height:48px!important;min-height:48px!important}
}
@media(max-width:760px){
 body.jj-poker-simple.jj-mobile-table-open #pokerRoom{position:fixed!important;inset:0!important;height:100dvh!important;min-height:0!important;overflow-y:auto!important}
 body.jj-poker-simple.jj-mobile-table-open #pokerRoom .room-head{flex:0 0 auto!important;z-index:220!important;padding-top:max(4px,env(safe-area-inset-top))!important}
 body.jj-poker-simple.jj-mobile-table-open #roomMeta{display:none!important}
 body.jj-poker-simple.jj-mobile-table-open #roomMeta:has(.is-degraded){display:block!important;position:absolute;top:100%;left:0;right:0;background:#392d13;white-space:normal!important;z-index:201}
 body.jj-poker-simple.jj-mobile-table-open #pokerRoom .poker-layout{flex:1 0 auto!important;display:flex!important;min-height:0!important;overflow:visible!important}
 body.jj-poker-simple.jj-mobile-table-open #pokerRoom .poker-zone{display:flex!important;flex-direction:column!important;flex:1!important;height:auto!important;min-height:0!important;padding:0!important;overflow:visible!important}
 body.jj-poker-simple.jj-mobile-table-open #pokerTable{flex:1 0 250px!important;height:auto!important;min-height:250px!important;width:100%!important}
 body.jj-poker-simple.jj-mobile-table-open #pokerTable .felt-center{top:43%!important}
 body.jj-poker-simple.jj-mobile-table-open #tableControls{display:flex!important;flex:0 0 auto!important;height:auto!important;min-height:32px!important;padding:2px 6px!important;position:relative!important;inset:auto!important;overflow:visible!important}
 body.jj-poker-simple.jj-mobile-table-open #tableControls button{min-height:30px!important;height:30px!important;max-height:none!important;padding:0 8px!important;font-size:11px!important}
 body.jj-poker-simple.jj-mobile-table-open #actionBar{display:block!important;position:relative!important;inset:auto!important;flex:0 0 auto!important;min-height:222px!important;max-height:none!important;overflow:visible!important;margin:0!important;padding:5px 8px max(6px,env(safe-area-inset-bottom))!important;border-radius:12px 12px 0 0!important;z-index:120!important}
 body.jj-poker-simple.jj-mobile-table-open.jj-mobile-poker-observer #actionBar{display:none!important}
 body.jj-poker-simple.jj-mobile-table-open #actionBar .jj-v124-sizing{margin-bottom:4px!important}
 body.jj-poker-simple.jj-mobile-table-open #actionBar .jj-v124-sizing .jj-size-btn{height:36px!important;min-height:36px!important}
 body.jj-poker-simple.jj-mobile-table-open #actionBar .jj-v124-sizing .jj-size-row{grid-template-columns:repeat(auto-fit,minmax(42px,1fr))!important;gap:4px!important;margin-bottom:3px!important}
 body.jj-poker-simple.jj-mobile-table-open #actionBar .jj-v124-raise-editor>input[type=range]{height:36px!important}
 body.jj-poker-simple.jj-mobile-table-open #actionBar .jj-v124-stepper,body.jj-poker-simple.jj-mobile-table-open #actionBar .jj-v124-stepper label{height:36px!important;min-height:36px!important}
 body.jj-poker-simple.jj-mobile-table-open #actionBar .jj-action-btn{height:48px!important;min-height:48px!important}
 body.jj-poker-simple.jj-mobile-table-open #actionBar .jj-action-btn b{font-size:12px!important;white-space:normal!important}
 body.jj-poker-simple.jj-mobile-table-open #actionBar .jj-v5-preactions{border:0!important;padding-top:8px!important}
 body.jj-poker-simple.jj-mobile-table-open #actionBar .jj-v5-preactions button{min-height:40px!important}
}
'''
ACTION = r'''  doAction=async function(action){
    if(!currentTableId||jjV121ActionPending)return;
    if(!jjV2Connection.fresh)return toast('最新の卓状態を同期中です');
    const legal=tableState?.legal||{};
    const allowed={check:legal.can_check,fold:!legal.can_check,call:legal.can_call,raise:legal.can_raise,allin:legal.can_all_in};
    if(!legal.can_act||!allowed[action])return;
    const tableId=currentTableId,before=tableState,decisionKey=jjV124DecisionKey();
    const body={action,action_id:jjV121ActionId()};
    body.hand_id=tableState.hand?.id;
    body.turn_id=tableState.turn_id||tableState.hand?.turn_id;
    if(action==='raise'){
      const raw=String($('#raiseTo')?.value??'').trim().replace(',','.');
      const entered=raw===''?NaN:Number(raw),bounds=jjRaiseBounds(),big=Number(tableState.big_blind||100);
      if(!Number.isFinite(entered))return toast('ベット／レイズ額を入力してください');
      const ceil1=value=>typeof jjV124CeilRaiseBb==='function'?jjV124CeilRaiseBb(value):Math.ceil((Number(value)-1e-9)*10)/10;
      const value=ceil1(entered),displayMin=ceil1(bounds.min),displayMax=ceil1(bounds.max);
      if(value<Number(displayMin)-0.001||value>Number(displayMax)+0.001)return toast('ベット／レイズ額が利用可能な範囲外です');
      const roundedMaxAllin=legal.can_all_in&&Number(bounds.max||0)>0&&Math.abs(value-Number(displayMax))<0.011;
      if(roundedMaxAllin){
        body.action='allin';
      }else{
        const exactBb=tableState?.tournament&&typeof jjSngSnapRaiseBb==='function'?jjSngSnapRaiseBb(value):value;
        const exactAmount=Math.round(Number(exactBb)*big);
        const minChips=Math.round(Number(bounds.min||0)*big),maxChips=Math.round(Number(bounds.max||0)*big);
        if(exactAmount<minChips||exactAmount>maxChips)return toast('ベット／レイズ額が利用可能な範囲外です');
        body.amount=exactAmount;
      }
    }
    jjV121ActionPending=true;jjV123ActionState();
    try{
      let next;
      try{next=await post('/tables/'+tableId+'/action',body)}
      catch(err){
        if(!(err instanceof TypeError))throw err;
        await new Promise(r=>setTimeout(r,450));
        if(currentTableId!==tableId||jjV124DecisionKey()!==decisionKey)throw err;
        next=await post('/tables/'+tableId+'/action',body);
      }
      // A newer WS snapshot wins over an older HTTP response.
      if(currentTableId===tableId&&tableState===before&&next?.legal){
        tableState=next;jjV2AcceptState('http',before);
      }
    }catch(err){
      toast(err.message);
      if(currentTableId===tableId){
        const beforeRefresh=tableState;
        jjV2SetConnection('syncing',false);
        try{
          const latest=await api('/tables/'+tableId);
          if(currentTableId===tableId&&tableState===beforeRefresh){
            tableState=latest.state;tableMessages=latest.messages||tableMessages;
            jjV2AcceptState('http',beforeRefresh);
          }
        }catch{}
      }
    }finally{
      jjV121ActionPending=false;
      // A WS render during pending disables its new buttons. Rebuild after the
      // flag clears; never blindly enable actions which are no longer legal.
      if(currentTableId===tableId&&tableState){renderPokerRoom();jjV2RenderConnection()}
    }
  };'''


def once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise RuntimeError("simple poker source drift: " + old[:90])
    return source.replace(old, new, 1)


def transform_app_js(source: str) -> str:
    if MARKER in source:
        return source
    start = "  doAction=async function(action){\n    if(!currentTableId||jjV121ActionPending)return;"
    if source.count(start) != 1:
        raise RuntimeError("simple poker action handler drift")
    a = source.index(start)
    b = source.index("\n  };", a) + len("\n  };")
    source = source[:a] + ACTION + source[b:]
    start = "  function jjV124DecisionMeta(hero,l){"
    if source.count(start) != 1:
        raise RuntimeError("simple poker metadata drift")
    a = source.index(start)
    b = source.index("\n  }", a) + len("\n  }")
    source = source[:a] + "  function jjV124DecisionMeta(hero,l){return jjV7HeroMarkup(hero,l)}" + source[b:]
    source = once(source,
        'bar.innerHTML=`<div class="jj-v124-waiting">',
        'bar.innerHTML=`${jjV7HeroMarkup(hero,l)}<div class="jj-v124-waiting">')
    for origin, arg in (("http", "null"), ("ws", "previous"), ("poll", "previous")):
        source = once(source,
            f"renderPokerRoom();jjV2AcceptState('{origin}',{arg})",
            f"jjV2AcceptState('{origin}',{arg});renderPokerRoom()")
    source = once(source,
        "jjV4EnsureMobileTools();jjV3ApplyFocus();jjV3ViewportSync();",
        "jjV4EnsureMobileTools();jjV3ApplyFocus();jjV3ViewportSync();jjV7Chrome();")
    source = once(source,
        "jjV2Connection.mode='idle';jjV2Connection.fresh=false;jjV2Connection.lastStateAt=0;jjV2RenderConnection();",
        "jjV2Connection.mode='idle';jjV2Connection.fresh=false;jjV2Connection.lastStateAt=0;jjV2RenderConnection();document.body.classList.remove('jj-poker-simple');")
    source = once(
        source,
        """  function jjV186TickActionClock(){
    const el=$('#jjActionClock');if(!el)return;
    const deadline=tableState?.hand?.action_deadline;
    if(!deadline){el.textContent='';el.classList.remove('is-urgent');return}
    const sec=Math.max(0,Math.ceil((new Date(deadline)-new Date())/1000));
    el.textContent=`残り ${sec}秒`;
    el.classList.toggle('is-urgent',sec<=10);
  }""",
        """  function jjV186TickActionClock(){
    const el=$('#jjActionClock');if(!el)return;
    const deadline=tableState?.hand?.action_deadline;
    if(!deadline){el.textContent='';el.classList.remove('is-urgent');return}
    const sec=Math.max(0,Math.ceil((new Date(deadline)-new Date())/1000));
    const using=tableState?.hand?.action_clock_source==='timebank';
    el.textContent=using?`TIME BANK · ${sec}秒`:`残り ${sec}秒`;
    el.classList.toggle('is-urgent',sec<=10);
  }""",
    )
    source = once(source,
        "  // Desktop bet markers use explicit poker-table lanes rather than the old\n",
        HELPERS + "\n  // Desktop bet markers use explicit poker-table lanes rather than the old\n")
    return source


def transform_styles(source: str) -> str:
    return source if MARKER in source else source.rstrip() + "\n" + CSS
