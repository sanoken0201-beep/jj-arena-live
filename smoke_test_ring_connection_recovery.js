// Execute the exact compiled Ring recovery block with deterministic transport/timer fakes.
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(process.argv[2]||'.jj_build/static/app.js','utf8');
const start=source.indexOf('  // jj-ring-connection-recovery-20261127');
const end=source.indexOf('\n  function jjV2HandLogText(',start);
assert(start>=0&&end>start,'compiled recovery block not found');
assert(source.includes('function disconnectTable(){\n    jjRingStop();'));
const harness=`
let currentTableId='A',tableState={v:0},tableMessages=[],tableWS=null,tablePoll=null,tableHeartbeat=null,tableReconnect=null;
let jjV121ActionPending=false;
const jjV2Connection={fresh:true,mode:'http'};
const events=[],sockets=[],requests=[],timers=new Map(),listeners={},docListeners={};
let serial=0,now=0;
const navigator={onLine:true},location={protocol:'https:',host:'test.invalid'};
const window={addEventListener:(n,f)=>listeners[n]=f};
const document={hidden:false,addEventListener:(n,f)=>docListeners[n]=f};
const Date={now:()=>now};
function setTimeout(f,ms){const id=++serial;timers.set(id,{f,ms,repeat:false});return id}
function setInterval(f,ms){const id=++serial;timers.set(id,{f,ms,repeat:true});return id}
function clearTimeout(id){timers.delete(id)}
const clearInterval=clearTimeout;
function fire(ms,repeat=false){const t=[...timers].find(([id,t])=>t.ms===ms&&t.repeat===repeat);if(!t)throw Error('timer missing '+ms);if(!repeat)timers.delete(t[0]);t[1].f()}
class WebSocket{
  static OPEN=1;
  constructor(url){this.url=url;this.readyState=0;sockets.push(this)}
  open(){this.readyState=1;this.onopen?.()}
  message(state){this.onmessage?.({data:JSON.stringify({type:'state',state})})}
  close(){this.readyState=3}
  send(){}
}
function api(path,opts){return new Promise(resolve=>requests.push({path,signal:opts.signal,resolve}))}
function jjV2SetConnection(mode,fresh){Object.assign(jjV2Connection,{mode,fresh})}
function jjV2AcceptState(source){jjV2SetConnection(source,true);events.push(source)}
function jjV6ConnectionClosed(){events.push('closed')}
function jjV6ConnectionOpen(){events.push('reconnected')}
function renderPokerRoom(){}
function renderTableChat(){}
`;
const ctx=vm.createContext({assert,AbortController});
vm.runInContext(harness+source.slice(start,end),ctx);
const evaluate=js=>vm.runInContext(js,ctx);
(async()=>{
  evaluate(`
    connectTable('A');sockets[0].open();sockets[0].message({v:1});
    assert.equal(jjV2Connection.mode,'ws');
    const oldClose=sockets[0].onclose, oldMessage=sockets[0].onmessage;
    oldClose();assert.equal(requests.length,1);assert.equal(jjV2Connection.fresh,false);
    fire(3000,true);assert.equal(requests.length,1,'overlapping poll');
    fire(1000);assert.equal(sockets.length,2);sockets[1].open();
    assert(tablePoll,'fallback stopped before first state');
    oldClose();oldMessage({data:JSON.stringify({type:'state',state:{v:-1}})});
    assert.equal(tableWS,sockets[1]);assert.equal(tableState.v,1);
    sockets[1].message({v:2});assert.equal(tablePoll,null);assert(requests[0].signal.aborted);
    requests[0].resolve({state:{v:-2}});
  `);
  await Promise.resolve();await Promise.resolve();
  evaluate(`
    assert.equal(tableState.v,2,'late HTTP overwrote socket state');
    sockets[1].onclose();assert.equal(requests.length,2);
    jjV121ActionPending=true;requests[1].resolve({state:{v:-3}});
  `);
  await Promise.resolve();await Promise.resolve();
  evaluate(`
    assert.equal(tableState.v,2,'poll overwrote pending action');
    jjV121ActionPending=false;fire(3000,true);
    assert.equal(requests.length,3);
    requests[2].resolve({state:{v:3}});
  `);
  await Promise.resolve();await Promise.resolve();
  evaluate(`
    assert.equal(tableState.v,3);assert.equal(jjV2Connection.mode,'poll');
    fire(1000);sockets[2].open();
    fire(5000);assert.equal(sockets[2].readyState,3,'missing first state was not bounded');
    assert(tablePoll);assert.equal(jjV2Connection.fresh,false);
    navigator.onLine=false;listeners.offline();navigator.onLine=true;
    listeners.online();assert.equal(sockets.length,4);
    sockets[3].open();sockets[3].message({v:4});
    document.hidden=true;docListeners.visibilitychange();now=16000;
    document.hidden=false;docListeners.visibilitychange();
    assert.equal(sockets.length,5,'foreground did not recover stale transport');
    const detached=sockets[4].onmessage;
    jjRingStop();currentTableId=null;
    detached({data:JSON.stringify({type:'state',state:{v:-4}})});
    assert.equal(tableState.v,4);assert.equal(tableWS,null);assert.equal(tablePoll,null);assert.equal(tableReconnect,null);
  `);
  console.log('JJ_RING_CONNECTION_RECOVERY_OK');
})().catch(e=>{console.error(e);process.exitCode=1});
