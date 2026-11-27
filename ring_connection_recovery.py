"""Bounded browser Ring connection recovery, applied to compiled assets only."""

import hashlib
from pathlib import Path

MARKER = "jj-ring-connection-recovery-20261127"
RECOVERY = r'''
  // jj-ring-connection-recovery-20261127
  let jjRingRecovery=null;
  function jjRingClearPoll(ctx){
    if(tablePoll){clearInterval(tablePoll);tablePoll=null}
    if(ctx?.request){ctx.request.abort();ctx.request=null}
  }
  function jjRingClearSocket(ctx){
    if(ctx?.deadline){clearTimeout(ctx.deadline);ctx.deadline=null}
    if(ctx?.initialSync){clearTimeout(ctx.initialSync);ctx.initialSync=null}
    if(tableHeartbeat){clearInterval(tableHeartbeat);tableHeartbeat=null}
    const old=tableWS;tableWS=null;
    if(old){old.onclose=old.onopen=old.onmessage=old.onerror=null;try{old.close()}catch{}}
  }
  function jjRingActive(ctx){return jjRingRecovery===ctx&&currentTableId===ctx.id}
  function jjRingStop(){
    const ctx=jjRingRecovery;jjRingRecovery=null;
    jjRingClearPoll(ctx);jjRingClearSocket(ctx);
    if(tableReconnect){clearTimeout(tableReconnect);tableReconnect=null}
  }
  function jjRingPoll(ctx){
    if(!jjRingActive(ctx)||ctx.wsReady||ctx.request||jjV121ActionPending||navigator.onLine===false)return;
    const before=tableState,request=new AbortController();ctx.request=request;
    const timer=setTimeout(()=>request.abort(),5000);
    (async()=>{
      try{
        const d=await api('/tables/'+encodeURIComponent(ctx.id),{signal:request.signal});
        // A newer socket state or action response always wins.
        if(!jjRingActive(ctx)||ctx.request!==request||request.signal.aborted||ctx.wsReady||jjV121ActionPending||tableState!==before||!d?.state)return;
        tableState=d.state;tableMessages=d.messages||[];
        jjV2AcceptState('poll',before);renderPokerRoom();
      }catch{
        if(jjRingActive(ctx)&&ctx.request===request&&!ctx.wsReady&&!jjV121ActionPending&&tableState===before){jjV2SetConnection('syncing',false);renderPokerRoom()}
      }finally{
        clearTimeout(timer);
        if(ctx.request===request)ctx.request=null;
      }
    })();
  }
  function jjRingFallback(ctx){
    if(!jjRingActive(ctx))return;
    jjRingPoll(ctx);
    if(!tablePoll)tablePoll=setInterval(()=>jjRingPoll(ctx),3000);
  }
  function jjRingRetry(ctx){
    if(!jjRingActive(ctx)||navigator.onLine===false||tableReconnect)return;
    const delay=Math.min(8000,1000*2**Math.min(ctx.attempts++,3));
    tableReconnect=setTimeout(()=>{tableReconnect=null;if(jjRingActive(ctx))connectTable(ctx.id)},delay);
  }
  function jjRingLost(ctx,socket){
    if(!jjRingActive(ctx)||tableWS!==socket)return;
    jjRingClearSocket(ctx);ctx.wsReady=false;
    jjV6ConnectionClosed();jjV2SetConnection('reconnecting',false);
    jjRingFallback(ctx);jjRingRetry(ctx);
  }
  function connectTable(id){
    if(currentTableId!==id)return;
    if(!jjRingRecovery||jjRingRecovery.id!==id){
      jjRingStop();jjRingRecovery={id,request:null,deadline:null,initialSync:null,attempts:0,wsReady:false};
    }
    const ctx=jjRingRecovery;
    if(tableReconnect){clearTimeout(tableReconnect);tableReconnect=null}
    jjRingClearSocket(ctx);ctx.wsReady=false;
    if(navigator.onLine===false){jjV2SetConnection('reconnecting',false);jjRingFallback(ctx);return}
    jjV2SetConnection('connecting',jjV2Connection.fresh);
    const proto=location.protocol==='https:'?'wss':'ws';
    let socket;
    try{socket=new WebSocket(`${proto}://${location.host}/ws/tables/${encodeURIComponent(id)}`)}
    catch{jjV2SetConnection('reconnecting',false);jjRingFallback(ctx);jjRingRetry(ctx);return}
    tableWS=socket;
    // A handshake alone is not synchronization. Preserve HTTP fallback until state arrives.
    ctx.deadline=setTimeout(()=>jjRingLost(ctx,socket),5000);
    socket.onopen=()=>{
      if(!jjRingActive(ctx)||tableWS!==socket)return;
      jjV6ConnectionOpen();
      jjV2SetConnection('syncing',!!tableState&&jjV2Connection.fresh);
      // Preserve the previous 700ms authoritative resync watchdog, but use
      // the same single-flight fallback rather than a competing request.
      ctx.initialSync=setTimeout(()=>{ctx.initialSync=null;if(jjRingActive(ctx)&&tableWS===socket&&!ctx.wsReady)jjRingFallback(ctx)},700);
      tableHeartbeat=setInterval(()=>{
        if(jjRingActive(ctx)&&tableWS===socket&&socket.readyState===WebSocket.OPEN){
          try{socket.send('ping')}catch{jjRingLost(ctx,socket)}
        }
      },15000);
    };
    socket.onmessage=e=>{
      if(!jjRingActive(ctx)||tableWS!==socket)return;
      try{
        const m=JSON.parse(e.data);
        if(m.type==='state'&&m.state){
          const previous=tableState;
          if(!ctx.wsReady){
            ctx.wsReady=true;ctx.attempts=0;
            clearTimeout(ctx.deadline);ctx.deadline=null;
            if(ctx.initialSync){clearTimeout(ctx.initialSync);ctx.initialSync=null}
            jjRingClearPoll(ctx);
          }
          tableState=m.state;
          if(Array.isArray(m.messages))tableMessages=m.messages;
          jjV2AcceptState('ws',previous);renderPokerRoom();
        }else if(m.type==='chat'&&ctx.wsReady){tableMessages=m.messages||[];renderTableChat()}
      }catch{}
    };
    socket.onclose=()=>jjRingLost(ctx,socket);
    socket.onerror=()=>jjRingLost(ctx,socket);
  }
  function jjRingWake(force=false){
    const ctx=jjRingRecovery;
    if(!ctx||!jjRingActive(ctx)||navigator.onLine===false)return;
    if(!force&&ctx.wsReady&&tableWS?.readyState===WebSocket.OPEN)return;
    jjRingClearSocket(ctx);ctx.wsReady=false;ctx.attempts=0;
    jjV2SetConnection('reconnecting',false);
    jjRingFallback(ctx);connectTable(ctx.id);
  }
  let jjRingHiddenAt=null;
  window.addEventListener('online',()=>jjRingWake(true));
  window.addEventListener('offline',()=>{
    const ctx=jjRingRecovery;if(!ctx||!jjRingActive(ctx))return;
    if(tableWS)jjRingLost(ctx,tableWS);
    else{jjV2SetConnection('reconnecting',false);jjRingFallback(ctx)}
  });
  document.addEventListener('visibilitychange',()=>{
    if(document.hidden){jjRingHiddenAt=Date.now();return}
    const force=jjRingHiddenAt!==null&&Date.now()-jjRingHiddenAt>=15000;
    jjRingHiddenAt=null;jjRingWake(force);
  });
  window.addEventListener('pageshow',e=>{if(e.persisted)jjRingWake(true)});
'''

def transform_app_js(source: str) -> str:
    if MARKER in source:
        return source
    start = "  function connectTable(id){"
    end = "\n  function suitChar("
    if source.count(start) != 1 or source.count(end) != 1:
        raise RuntimeError("Ring recovery function boundary drift")
    a, b = source.index(start), source.index(end)
    if b <= a or "jjV6ConnectionClosed()" not in source[a:b] or "jjV2AcceptState('poll',previous)" not in source[a:b]:
        raise RuntimeError("Ring recovery compiled contract drift")
    if "jjV71SocketOpen(id)" not in source[a:b]:
        raise RuntimeError("Ring recovery must follow existing freshness transform")
    if "\n  function " in source[a:b][len(start):]:
        raise RuntimeError("Ring recovery would remove adjacent functions")
    source = source[:a] + RECOVERY + source[b:]
    anchor = "  function disconnectTable(){\n"
    if source.count(anchor) != 1:
        raise RuntimeError("Ring recovery disconnect boundary drift")
    return source.replace(anchor, anchor + "    jjRingStop();\n", 1)


def apply_to_build(output_root: Path | str, manifest: dict) -> dict:
    path = Path(output_root) / "static/app.js"
    source = transform_app_js(path.read_text(encoding="utf-8"))
    path.write_text(source, encoding="utf-8", newline="\n")
    manifest["outputs"]["static/app.js"] = hashlib.sha256(source.encode("utf-8")).hexdigest()
    manifest.setdefault("post_transforms", {})["ring_connection_recovery"] = MARKER
    return manifest
