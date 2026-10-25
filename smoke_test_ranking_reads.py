"""Exercise the actual compiled SPA in desktop/mobile Chromium, with delayed GETs."""
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from smoke_test_browser_user_journey import STUB, chrome_binary
from served_assets import build_all, validate_built_assets
from browser_asset_pipeline import finalize_build

STUB = STUB.replace('let loggedIn = false;', 'let loggedIn = true;')
STUB = STUB.replace('window.__jjMissingRequests = [];', '''window.__rankDelay=0;window.__monthDelay=0;window.__points=10;window.__seasonName='Winter';window.__jjMissingRequests = [];''')
STUB = STUB.replace('`${method} ${path}`', '`${method} ${path}${url.search}`')
STUB = STUB.replace("if(path === '/api/rankings') return jsonResponse(rankings);", '''if(path === '/api/seasons')return jsonResponse([
      {season_id:'fall',name:window.__seasonName,status:'active',start_date:'2026-09-01',end_exclusive:'2027-04-01'},
      {season_id:'summer',name:'Summer',status:'archived',start_date:'2026-04-01',end_exclusive:'2026-09-01'}]);
    if(path === '/api/home/core') return jsonResponse({rankings,schedules:[],announcements:[],tables});
    if(path === '/api/rankings') {
      const points=url.searchParams.get('season')==='summer'?7:url.searchParams.has('month')?3:window.__points;
      const delay=window.__rankDelay+(url.searchParams.has('month')?window.__monthDelay:0);
      await new Promise(r=>setTimeout(r,delay));
      return jsonResponse(rankings.map(r=>({...r,points})));
    }''')
DRIVER = r'''
<script>
(async()=>{
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const wait=async(fn,label)=>{for(let i=0;i<250;i++){if(fn())return;await sleep(10)}throw Error('timeout '+label)};
const assert=(x,msg)=>{if(!x)throw Error(msg)};
const $=s=>document.querySelector(s);
const counts=()=>window.__jjRequests.filter(x=>/\/api\/(rankings|seasons)/.test(x));
const points=()=>$('#rankBody tr td:nth-child(3)')?.textContent;
const report={};
try{
 await wait(()=>$('#jjHomeHubGrid')?.textContent.includes('今日'),'home');await sleep(40);
 assert(window.__jjRequests.filter(x=>x==='GET /api/home/core').length===1,'one home core');
 assert(window.__jjRequests.includes('GET /api/home/overview?include_points=false'),'overview reuses points');
 report.homeCore=1;
 window.__rankDelay=600;window.__jjRequests=[];
 $('.nav[data-view="ranking"]').click();
 await sleep(20);
 assert(points()==='10','home standings must paint before ranking API response');
 assert($('#jjRankRefreshStatus')?.textContent.includes('最新情報'),'provisional standings must be labeled');
 report.instantHomeStandings=true;
 await wait(()=>$('#jjV1243RankingSummary')?.textContent.includes('TOP 5'),'ranking summary');
 assert(!$('#jjRankRefreshStatus'),'provisional label must clear on authoritative response');
 window.__rankDelay=0;
 report.openRequests=counts();assert(counts().length===3,'open = seasons + two distinct rankings '+counts());
 const before=window.__jjRequests.length;
 for(const value of ['ユ','ユー','not found','']){$('#rankSearch').value=value;$('#rankSearch').dispatchEvent(new Event('input'))}
 await sleep(30);assert(window.__jjRequests.length===before,'search must not request');report.searchRequests=0;
 assert(points()==='10','search restores rows');
 window.__points=24;window.__seasonName='Renamed';window.__jjRequests=[];
 $('[data-jj-v1243-retry="ranking"]').click();
 await wait(()=>points()==='24','refresh points');
 assert($('#jjV1243RankingSummary').textContent.includes('24'),'summary refresh');
 assert($('#podium').textContent.includes('Renamed'),'metadata refresh');
 assert(counts().length===3,'refresh dedup');report.refreshRequests=counts();
 // A slow monthly summary must not block the detailed ranking table.
 window.__monthDelay=700;window.__points=26;
 $('[data-jj-v1243-retry="ranking"]').click();
 await wait(()=>points()==='26','ranking first paint before monthly summary');
 assert($('.jj-v1243-rank-me b')?.textContent.trim()!=='26 pt','monthly request still pending');
 await wait(()=>$('.jj-v1243-rank-me b')?.textContent.trim()==='26 pt','summary follows table');
 report.progressiveTable=true;window.__monthDelay=0;window.__points=24;
 $('[data-jj-v1243-retry="ranking"]').click();
 await wait(()=>points()==='24','restore fixture points');
 window.__rankDelay=180;window.__jjRequests=[];
 $('[data-rank-mode="month"]').click();await sleep(10);
 $('[data-rank-mode="archive"]').click();await sleep(10);
 $('[data-rank-mode="overall"]').click();
 await wait(()=>points()==='24','fast switch');await sleep(220);
 assert(points()==='24','old monthly/archive response cannot overwrite');
 assert(counts().filter(x=>x==='GET /api/rankings?season=fall').length===1,'inflight sharing across switches');
 assert(!counts().some(x=>x.includes('/seasons')),'season reuse');report.fastSwitchRequests=counts();
 window.__rankDelay=0;$('[data-rank-mode="archive"]').click();await wait(()=>points()==='7','archive');
 $('[data-rank-mode="month"]').click();await wait(()=>points()==='3','monthly');
 const last=$('#rankBody').innerHTML;
 window.__rankDelay=150;$('[data-rank-mode="overall"]').click();await sleep(10);
 $('.nav[data-view="home"]').click();await sleep(200);
 assert($('#rankBody').innerHTML===last,'no paint after navigation');
 window.__rankDelay=0;window.__points=35;$('.nav[data-view="ranking"]').click();
 await wait(()=>points()==='35','reentry fresh');
 // A refresh must bypass an older in-flight result, and that result must never repaint.
 window.__points=40;window.__rankDelay=180;$('[data-jj-v1243-retry="ranking"]').click();await sleep(10);
 window.__points=50;window.__rankDelay=0;$('[data-jj-v1243-retry="ranking"]').click();
 await wait(()=>points()==='50','forced refresh bypasses old request');await sleep(220);
 assert(points()==='50','old refresh cannot overwrite');
 assert($('#jjV1243RankingSummary').textContent.includes('Renamed'),'summary uses active season label');
 assert(document.documentElement.scrollWidth<=innerWidth+2,'no horizontal overflow');
 const rect=$('#rankSearch').getBoundingClientRect();assert(rect.width>50&&rect.right<=innerWidth+2,'search visible');
 report.viewport=innerWidth;report.ok=true;
}catch(e){report.error=e.stack;report.requests=window.__jjRequests}
document.body.insertAdjacentHTML('beforeend','<pre id="readResult" data-reads-ok="'+(report.ok?'1':'0')+'"></pre>');
$('#readResult').textContent=JSON.stringify(report);
})();
</script>
'''

def main():
    chrome=chrome_binary()
    with tempfile.TemporaryDirectory(prefix='jj-ranking-reads-') as td:
        root=Path(td)
        manifest=finalize_build(root,build_all(root));validate_built_assets(root)
        first=(root/'static/app.js').read_bytes()
        finalize_build(root,build_all(root))
        assert first==(root/'static/app.js').read_bytes(), 'reproducible build'
        from ranking_read_optimization import transform_app_js
        assert transform_app_js(first.decode())==first.decode(), 'idempotent finalizer'
        html=(root/'index.html').read_text()
        html=re.sub(r'<script[^>]+src="[^"]+"[^>]*></script>', '', html)
        html=html.replace('/static/', 'static/')
        html=html.replace('</head>',STUB+'</head>').replace('</body>', '<script src="static/app.js"></script>'+DRIVER+'</body>')
        fixture=root/'fixture.html';fixture.write_text(html)
        for width,height in [(1440,900),(390,844)]:
            p=subprocess.run([chrome,'--headless','--no-sandbox','--disable-gpu','--allow-file-access-from-files','--virtual-time-budget=9000',f'--window-size={width},{height}','--dump-dom',fixture.as_uri()],capture_output=True,text=True,timeout=45)
            results=re.findall(r'<pre id="readResult"[^>]*>(.*?)</pre>',p.stdout,re.S)
            assert results, p.stderr[-2000:]+p.stdout[-2000:]
            import html as html_module
            data=json.loads(html_module.unescape(results[-1]));assert data.get('ok'),data
            print(json.dumps(data,ensure_ascii=False))
    print('RANKING_READS_BROWSER_OK')

if __name__=='__main__':main()
