const assert = require('node:assert/strict');
const vm = require('node:vm');
const {execFileSync} = require('node:child_process');
const helper = execFileSync('python', ['-c', 'from read_efficiency import CLIENT_HELPER; print(CLIENT_HELPER)'], {encoding:'utf8'});

async function main(){
  for(const [path,keys,legacy] of [
    ['/home/core',['rankings','schedules','announcements','tables'],['/rankings','/schedules','/announcements','/tables']],
    ['/points/dashboard',['entries','ranking_names'],['/entries?limit=40','/ranking-names']]
  ]){
    for(const mode of ['success','failure','invalid','signed-out']){
      const calls=[];
      const context={me:{id:1},api:async url=>{
        calls.push(url);
        if(url===path){
          if(mode==='signed-out'){context.me=null;throw Error('login required')}
          if(mode==='failure')throw Error('server unavailable');
          if(mode==='invalid')return {rankings:'invalid'};
          return Object.fromEntries(keys.map((key,i)=>[key,[i]]));
        }
        return [legacy.indexOf(url)];
      }};
      vm.createContext(context);vm.runInContext(helper,context);
      if(mode==='signed-out'){
        await assert.rejects(context.jjReadBundle(path,keys,legacy));
        assert.deepEqual(calls,[path]);continue;
      }
      const result=await context.jjReadBundle(path,keys,legacy);
      assert.deepEqual(JSON.parse(JSON.stringify(result)),keys.map((_,i)=>[i]));
      assert.deepEqual(calls,mode==='success'?[path]:[path,...legacy]);
      if(mode==='success'){
        await context.jjReadBundle(path,keys,legacy);
        assert.deepEqual(calls,[path,path]); // No stale client response cache.
      }
    }
  }
  console.log('READ_BUNDLE_OK: one request normally; fallback only after failure; no stale cache');
}
main().catch(error=>{console.error(error);process.exit(1)});
