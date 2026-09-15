const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const source=fs.readFileSync('admin_static/ops_dashboard.js','utf8');
async function render(p95,waiting=0,errors=0,fail=false){
  const nodes=new Map();
  const document={querySelector(s){if(s==='#dashboardView'||s==='#pointsView')return null;if(!nodes.has(s))nodes.set(s,{});return nodes.get(s)},querySelectorAll(){return []},addEventListener(_,fn){this.ready=fn}};
  const data={errors_24h:errors,recent_errors:[],runtime:{api_latency:{p95_ms:p95,samples:p95==null?0:20},db_pool:{backend:'postgres',active:true,requests_waiting:waiting}}};
  const context={document,Intl,Date,Number,String,Object,setTimeout,setInterval(){},fetch:async()=>{if(fail)throw Error('offline');return {ok:true,json:async()=>data}}};
  vm.runInNewContext(source,context);
  document.ready();
  await new Promise(resolve=>setImmediate(resolve));
  return nodes;
}
(async()=>{
 for(const [value,level] of [[null,'unknown'],[0,'ok'],[500,'ok'],[500.01,'warning'],[1000,'warning'],[1000.01,'critical']]){
  const n=await render(value);assert.equal(n.get('#opsStatus').className,`ops-status ops-${level}`);
  if(value===null)assert.match(n.get('#opsHealth').innerHTML,/P95 —/);
 }
 assert.match((await render(10,1)).get('#opsStatus').textContent,/DB接続待ち 1件/);
 assert.match((await render(10,0,1)).get('#opsStatus').textContent,/過去24時間のエラー 1件/);
 assert.match((await render(10,0,0,true)).get('#opsStatus').textContent,/最新ではありません/);
 console.log('OPS_ALERTS_OK: thresholds, missing data, pool, errors, stale fetch');
})().catch(e=>{console.error(e);process.exit(1)});
