from __future__ import annotations

"""Phase 4C anonymous UX telemetry transform.

Only coarse interaction metrics are emitted. No user/account identifiers, hand
ids, table ids, cards, chip amounts, chat, or free-form strings are included.
The decision metric is the time until a trusted/manual action selection; an
automatically executed safe pre-action is tracked separately and does not pull
down the manual-decision latency distribution.
"""

PHASE6_MARKER = "v2 player-ux phase4c telemetry 2026-09-13"


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"player UX phase6 drift at {label}: expected 1 source block, found {count}")
    return source.replace(old, new, 1)


def transform_app_js(source: str) -> str:
    if PHASE6_MARKER in source:
        return source

    anchor = "  renderActionBar=function(){\n    const bar=$('#actionBar');if(!bar)return;\n"
    helpers = r'''  // v2 player-ux phase4c telemetry 2026-09-13
  const jjV6Telemetry={queue:[],timer:null,decisionKey:'',decisionStart:0,hadDisconnect:false};
  function jjV6Device(){
    const w=Math.max(0,Number(window.innerWidth||0));
    return w<=760?'mobile':w<=1100?'tablet':'desktop';
  }
  function jjV6Emit(event,detail,durationMs=null){
    const item={event:String(event),detail:String(detail),device:jjV6Device()};
    if(durationMs!=null)item.duration_ms=Math.max(0,Math.min(120000,Math.round(Number(durationMs)||0)));
    jjV6Telemetry.queue.push(item);
    if(jjV6Telemetry.queue.length>=8)return jjV6Flush();
    if(!jjV6Telemetry.timer)jjV6Telemetry.timer=setTimeout(jjV6Flush,3000);
  }
  function jjV6Flush(){
    if(jjV6Telemetry.timer){clearTimeout(jjV6Telemetry.timer);jjV6Telemetry.timer=null}
    if(!jjV6Telemetry.queue.length)return;
    const events=jjV6Telemetry.queue.splice(0,30),body=JSON.stringify({events});
    fetch('/api/ux-telemetry',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body,keepalive:true}).catch(()=>{});
    if(jjV6Telemetry.queue.length)jjV6Telemetry.timer=setTimeout(jjV6Flush,1200);
  }
  function jjV6SyncDecision(l){
    if(!l?.can_act)return;
    if(typeof jjV2Connection!=='undefined'&&!jjV2Connection.fresh)return;
    const key=typeof jjV124DecisionKey==='function'?jjV124DecisionKey():'';
    if(!key||key===jjV6Telemetry.decisionKey)return;
    jjV6Telemetry.decisionKey=key;jjV6Telemetry.decisionStart=performance.now();
  }
  function jjV6FinishDecision(action){
    if(!jjV6Telemetry.decisionKey||!jjV6Telemetry.decisionStart)return;
    const current=typeof jjV124DecisionKey==='function'?jjV124DecisionKey():'';
    if(current!==jjV6Telemetry.decisionKey){jjV6Telemetry.decisionKey='';jjV6Telemetry.decisionStart=0;return}
    const elapsed=performance.now()-jjV6Telemetry.decisionStart;
    jjV6Telemetry.decisionKey='';jjV6Telemetry.decisionStart=0;
    jjV6Emit('decision',action,elapsed);
  }
  function jjV6Timeout(actionLabel){
    const detail=actionLabel==='チェック'?'check':actionLabel==='フォールド'?'fold':'unknown';
    jjV6Telemetry.decisionKey='';jjV6Telemetry.decisionStart=0;
    jjV6Emit('timeout',detail);
  }
  function jjV6ConnectionClosed(){
    jjV6Telemetry.hadDisconnect=true;jjV6Emit('fallback','ws_close');
  }
  function jjV6ConnectionOpen(){
    if(!jjV6Telemetry.hadDisconnect)return;
    jjV6Telemetry.hadDisconnect=false;jjV6Emit('reconnect','ws_open');
  }

'''
    if source.count(anchor) != 1:
        raise RuntimeError("player UX phase6 drift at action renderer anchor")
    source = source.replace(anchor, helpers + anchor, 1)

    source = _replace_once(
        source,
        """    const l=tableState?.legal||{can_act:false},hero=jjV124Hero();
    const active=document.activeElement,focusDraft=active?.id==='raiseTo'?{key:jjV124DecisionKey(),start:active.selectionStart,end:active.selectionEnd}:null;
""",
        """    const l=tableState?.legal||{can_act:false},hero=jjV124Hero();
    jjV6SyncDecision(l);
    const active=document.activeElement,focusDraft=active?.id==='raiseTo'?{key:jjV124DecisionKey(),start:active.selectionStart,end:active.selectionEnd}:null;
""",
        "decision start",
    )

    source = _replace_once(
        source,
        """    jjV2Connection.lastStateAt=Date.now();
    jjV2SetConnection(source==='ws'?'ws':source==='poll'?'fallback':'http',true);
""",
        """    jjV2Connection.lastStateAt=Date.now();
    jjV2SetConnection(source==='ws'?'ws':source==='poll'?'fallback':'http',true);
    jjV6SyncDecision(tableState?.legal||{});
""",
        "decision start after fresh state",
    )

    source = _replace_once(
        source,
        """      if(me?.name&&line.startsWith(`${me.name} timed out`))toast(`時間切れで${jjV2TimeoutAction(logs,i)}しました。次ハンドから一時離席になります`);
""",
        """      if(me?.name&&line.startsWith(`${me.name} timed out`)){
        const timeoutAction=jjV2TimeoutAction(logs,i);jjV6Timeout(timeoutAction);toast(`時間切れで${timeoutAction}しました。次ハンドから一時離席になります`);
      }
""",
        "timeout metric",
    )

    source = _replace_once(
        source,
        """    tableWS.onopen=()=>{
      if(tablePoll){clearInterval(tablePoll);tablePoll=null}
""",
        """    tableWS.onopen=()=>{
      jjV6ConnectionOpen();
      if(tablePoll){clearInterval(tablePoll);tablePoll=null}
""",
        "reconnect metric",
    )

    source = _replace_once(
        source,
        """      if(currentTableId!==id)return;
      jjV2SetConnection('reconnecting',false);
""",
        """      if(currentTableId!==id)return;
      jjV6ConnectionClosed();
      jjV2SetConnection('reconnecting',false);
""",
        "fallback metric",
    )

    listener_anchor = "  // Desktop bet markers use explicit poker-table lanes rather than the old\n"
    listeners = r'''  document.addEventListener('click',e=>{
    const action=e.target.closest('#actionBar [data-action]');
    // Programmatic clicks from a reserved safe pre-action are measured via the
    // preaction event, not as near-zero human decision latency.
    if(e.isTrusted&&action&&['fold','check','call','raise','allin'].includes(action.dataset.action||''))jjV6FinishDecision(action.dataset.action);

    const pre=e.target.closest('[data-jj-preaction]');
    if(pre&&['check','check_fold'].includes(pre.dataset.jjPreaction||''))jjV6Emit('preaction',pre.dataset.jjPreaction);

    const sizing=e.target.closest('#actionBar .jj-size-btn,#actionBar [data-jj-raise-step]');
    if(sizing){
      const detail=sizing.hasAttribute('data-allin-size')?'allin':sizing.hasAttribute('data-jj-raise-step')?'step':'preset';
      jjV6Emit('sizing',detail);
    }

    if(e.target.closest('[data-jj-sizing-settings]'))jjV6Emit('ui','settings');
    if(e.target.closest('#jjFocusModeToggle'))jjV6Emit('ui','focus');
    const side=e.target.closest('[data-jj-mobile-side]');
    if(side&&['log','chat'].includes(side.dataset.jjMobileSide||''))jjV6Emit('ui',side.dataset.jjMobileSide==='log'?'history':'chat');
  });
  document.addEventListener('change',e=>{
    if(e.target?.id==='raiseSlider')jjV6Emit('sizing','slider');
    if(e.target?.id==='raiseTo')jjV6Emit('sizing','input');
  });
  window.addEventListener('pagehide',jjV6Flush);
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden')jjV6Flush()});

'''
    if source.count(listener_anchor) != 1:
        raise RuntimeError("player UX phase6 drift at listener anchor")
    source = source.replace(listener_anchor, listeners + listener_anchor, 1)
    return source


__all__ = ["PHASE6_MARKER", "transform_app_js"]
