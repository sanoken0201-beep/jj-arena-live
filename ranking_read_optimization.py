"""Deterministic, fail-closed read orchestration after the season transform.

Only GET ownership and rendering change; no accounting or poker mutations.
"""
import hashlib
from pathlib import Path

MARKER = 'JJ_RANKING_READS_V1'

HELPERS = r'''
  // JJ_RANKING_READS_V1: cache only metadata, never settled ranking responses.
  let jjRankGeneration=0,jjReadNavigation=0,jjRankSnapshot=null;
  let jjSeasonMemo=null,jjSeasonPending=null;
  let jjRankPending=new Map();
  let jjHomeContext=null,jjHomePending=null;
  function jjInvalidateReads(){
    jjReadNavigation++;jjRankGeneration++;jjRankSnapshot=null;
    // Season metadata is not user-specific and remains fresh for its short TTL.
    // Preserve it across views so reopening ranking skips a serial GET roundtrip.
    jjSeasonPending=null;jjRankPending=new Map();
    jjHomeContext=null;jjHomePending=null;
  }
  function jjReadSeasons(){
    if(jjSeasonMemo&&Date.now()-jjSeasonMemo.at<15000)return Promise.resolve(jjSeasonMemo.rows);
    if(jjSeasonPending)return jjSeasonPending;
    const nav=jjReadNavigation;
    const p=api('/seasons').then(rows=>{
      if(nav===jjReadNavigation&&jjSeasonPending===p)jjSeasonMemo={rows,at:Date.now()};
      return rows;
    }).finally(()=>{if(jjSeasonPending===p)jjSeasonPending=null});
    jjSeasonPending=p;return p;
  }
  function jjReadRanking(month=null,season='fall',pool=jjRankPending){
    const q=new URLSearchParams({season});if(month)q.set('month',month);
    const path='/rankings?'+q.toString();
    if(pool.has(path))return pool.get(path);
    const p=api(path).finally(()=>{if(pool.get(path)===p)pool.delete(path)});
    pool.set(path,p);return p;
  }
  async function jjHomeOverview(){
    const ctx=jjHomeContext;
    if(!ctx||!ctx.rows)return api('/home/overview');
    const d=await api('/home/overview?include_points=false');
    const name=String(ctx.user.ranking_name||ctx.user.name||'');
    const mine=ctx.rows.find(r=>String(r.name)===name);
    return {...d,points:{season_total:mine?.points||0,rank:mine?.rank||null}};
  }
'''


def replace_once(js, old, new):
    if js.count(old) != 1:
        raise RuntimeError('ranking read contract drift: ' + old[:90])
    return js.replace(old, new, 1)


def transform_app_js(js):
    if MARKER in js:
        return js
    js = replace_once(js, "  async function renderRanking(){", HELPERS + "  async function renderRanking(force=false){")
    js = replace_once(js, "const jjSeasons=await api('/seasons');", """if(!me||currentView!=='ranking')return;
    if(force){jjSeasonMemo=null;jjSeasonPending=null;jjRankPending=new Map()}
    const generation=++jjRankGeneration,nav=jjReadNavigation,user=me,mode=rankMode;
    const valid=()=>generation===jjRankGeneration&&nav===jjReadNavigation&&user===me&&currentView==='ranking';
    const jjSeasons=await jjReadSeasons();if(!valid())return;""")
    js = replace_once(js, "<span>後期シーズン</span>", "<span>${safe(jjCurrentSeason?.name||'シーズン総合')}</span>")
    js = replace_once(js, "'あなたの表示名に一致する後期ランキングがまだありません。ポイントが反映されるとここに表示されます。'", "'あなたの表示名に一致するランキングがまだありません。ポイントが反映されるとここに表示されます。','<button class=\"soft\" data-jj-v1243-retry=\"ranking\">更新</button>'")
    # Rendering is a pure operation over the completed display snapshot.
    start = js.index("    await loadRankings(month,season);", js.index('async function renderRanking('))
    end = js.index('\n\n  async function renderPoints()', start)
    draw = js[start:end].removeprefix('    await loadRankings(month,season);')
    draw = draw.replace("rankings.filter", "displayRows.filter").replace('rankMode', 'mode')
    draw = draw.replace('jjCurrentSeason?.name', 'activeSeason?.name')
    js = js[:start] + """
    const pool=jjRankPending,summaryMonth=jjV1243MonthKey();
    // Start all consumers together so identical table/summary keys share a Promise.
    const displayPromise=season?jjReadRanking(month,season,pool):Promise.resolve([]);
    const summaryPromise=Promise.all([
      jjReadRanking(null,'fall',pool),
      summaryMonth?jjReadRanking(summaryMonth,'fall',pool):Promise.resolve([])
    ]).then(rows=>({rows}),error=>({error}));
    try{
      const displayRows=await displayPromise;
      if(!valid())return;
      jjRankSnapshot={displayRows,jjSeasons,season,activeSeason:jjCurrentSeason,mode};
      // The detailed table is authoritative and must not wait for monthly cards.
      jjDrawRanking();
      const summary=await summaryPromise;
      if(!valid())return;
      if(summary.error){
        const box=jjV1243EnsureRanking();
        if(box)box.innerHTML=jjV1243State('error','ランキング詳細を更新できませんでした',summary.error.message||'通信状態を確認してください。','<button class="soft" data-jj-v1243-retry="ranking">再試行</button>');
        return;
      }
      await jjV1243LoadRanking(...summary.rows);
    }catch(err){if(valid())toast(err.message)}
  }
  function jjDrawRanking(){
    if(!jjRankSnapshot||currentView!=='ranking'||jjRankSnapshot.mode!==rankMode)return;
    const {displayRows,jjSeasons,season,activeSeason,mode}=jjRankSnapshot;
    """ + draw + js[end:]
    js = replace_once(js, "$('#rankSearch').addEventListener('input',()=>renderRanking())", "$('#rankSearch').addEventListener('input',jjDrawRanking)")
    js = replace_once(js, 'async function jjV1243LoadRanking(){', 'async function jjV1243LoadRanking(seasonRows,monthRows){')
    js = replace_once(js, "      const month=jjV1243MonthKey();\n      const [seasonRows,monthRows]=await Promise.all([api('/rankings?season=fall'),month?api(`/rankings?season=fall&month=${encodeURIComponent(month)}`):Promise.resolve([])]);", '')
    js = replace_once(js, "if(v==='ranking')await jjV1243LoadRanking();", '')
    js = replace_once(js, "else if(target==='ranking')jjV1243LoadRanking();", "else if(target==='ranking')renderRanking(true).catch(e=>toast(e.message));")
    js = replace_once(js, 'function switchView(v){', 'function switchView(v){jjInvalidateReads();')
    js = replace_once(js, 'async function logout(remote=true){', 'async function logout(remote=true){jjInvalidateReads();')
    js = replace_once(js, 'async function refreshAll(){await Promise.all([loadRankings(),renderHome()]);}', 'async function refreshAll(){await renderHome();}')
    js = replace_once(js, "const jjActivePoints=(await api('/seasons')).find", "const jjActivePoints=(await jjReadSeasons()).find")
    # Preserve the existing hub and table layout, reuse the core's ranking rows.
    js = replace_once(js, "async function renderHome(){const [r,s,n,t]", "async function renderHome(){const ctx=jjHomeContext,nav=jjReadNavigation;const [r,s,n,t]")
    js = replace_once(js, ");rankings=r;const top=r[0];", ");if(nav!==jjReadNavigation||!me||currentView!=='home')return;if(ctx)ctx.rows=r;const top=r[0];")
    js = replace_once(js, "    await jjSubBaseRenderHome();", "    const nav=jjReadNavigation;await jjSubBaseRenderHome();if(nav!==jjReadNavigation)return;")
    js = replace_once(js, "      const announcements=await api('/announcements'),today=", "      const announcements=jjHomeContext?.announcements||await api('/announcements'),today=")
    js = js.replace("if(ctx)ctx.rows=r;", "if(ctx){ctx.rows=r;ctx.announcements=n;}")
    js = replace_once(js, "    const result=await jjV192BaseRenderHome();", "    const nav=jjReadNavigation;const result=await jjV192BaseRenderHome();if(nav!==jjReadNavigation)return result;")
    js = replace_once(js, "const r=await jjV121OldRenderHome();await jjV121LoadHomeHub();", "const nav=jjReadNavigation;const r=await jjV121OldRenderHome();if(nav===jjReadNavigation)await jjV121LoadHomeHub();")
    # Only the final active home renderer; the earlier compatibility renderer stays intact.
    needle="const d=await api('/home/overview'),q=d.quiz||{},p=d.points||{},perf=d.performance||{},learn=d.learning||{},hands=d.recent_hands||[],articles=d.articles||[];"
    js = replace_once(js, needle, needle.replace("const d=await api('/home/overview')", 'const nav=jjReadNavigation,user=me,d=await jjHomeOverview()') + "\n        if(nav!==jjReadNavigation||user!==me||currentView!=='home'||!me)return;")
    anchor='  // v1.24.4 analysis focus and decision-first review.'
    js = replace_once(js, anchor, """
  const jjReadBaseRenderHome=renderHome;
  renderHome=function(){
    if(jjHomePending)return jjHomePending;
    const ctx={user:me,rows:null};jjHomeContext=ctx;
    const p=jjReadBaseRenderHome().finally(()=>{
      if(jjHomeContext===ctx)jjHomeContext=null;
      if(jjHomePending===p)jjHomePending=null;
    });
    jjHomePending=p;return p;
  };
  document.addEventListener('visibilitychange',()=>{
    if(!document.hidden&&me&&currentView==='ranking')renderRanking(true).catch(e=>toast(e.message));
  });
""" + anchor)
    return js


def apply_to_build(output_root, manifest):
    path=Path(output_root)/'static/app.js'
    content=transform_app_js(path.read_text(encoding='utf-8'))
    path.write_text(content,encoding='utf-8')
    manifest['outputs']['static/app.js']=hashlib.sha256(content.encode()).hexdigest()
    manifest.setdefault('post_transforms',{})['ranking_read_optimization']=MARKER
    return manifest
