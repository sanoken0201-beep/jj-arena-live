"""Keep legacy browser screens aligned to the activated season at build time."""
from __future__ import annotations

MARKER = "JJ_DYNAMIC_SEASON_RANKING_V1"
OLD_RANKING = (
    "const month=rankMode==='month'?$('#rankMonth').value||monthOptions()[0]:null,"
    "season=rankMode==='archive'?'summer':'fall';await loadRankings(month,season);"
)
NEW_RANKING = """const jjSeasons=await api('/seasons');
    jjCurrentSeason=jjSeasons.find(x=>x.status==='active')||null;
    const monthSelect=$('#rankMonth'),months=monthOptions();
    if([...monthSelect.options].map(x=>x.value).join(',')!==months.join(',')){
      const selected=monthSelect.value;
      monthSelect.replaceChildren(...months.map(m=>new Option(m,m)));
      monthSelect.value=months.includes(selected)?selected:(months[0]||'');
    }
    let archiveSelect=$('#jjArchiveSeason');
    if(!archiveSelect){
      archiveSelect=document.createElement('select');
      archiveSelect.id='jjArchiveSeason';
      archiveSelect.setAttribute('aria-label','過去シーズンを選択');
      monthSelect.insertAdjacentElement('afterend',archiveSelect);
      archiveSelect.addEventListener('change',()=>renderRanking().catch(e=>toast(e.message)));
    }
    const archiveItems=jjSeasons.filter(x=>x.status==='archived');
    const archiveChoices=archiveItems.map(x=>({
      key:x.season_id==='fall'?'archive:fall':x.season_id,name:x.name
    }));
    const saved=archiveSelect.value;
    archiveSelect.replaceChildren(...archiveChoices.map(x=>new Option(x.name,x.key)));
    archiveSelect.value=archiveChoices.some(x=>x.key===saved)?saved:(archiveChoices[0]?.key||'');
    archiveSelect.hidden=rankMode!=='archive';
    const month=rankMode==='month'?(monthSelect.value||months[0]||null):null;
    const season=rankMode==='archive'?archiveSelect.value:'fall';
    await loadRankings(month,season);"""
OLD_MONTHS = (
    "function monthOptions(){return ['2026-09','2026-10','2026-11',"
    "'2026-12','2027-01','2027-02','2027-03']}"
)
NEW_MONTHS = """let jjCurrentSeason=null;
  function monthOptions(){
    if(!jjCurrentSeason)return ['2026-09','2026-10','2026-11','2026-12','2027-01','2027-02','2027-03'];
    const months=[],start=jjCurrentSeason.start_date.slice(0,7),
      end=jjCurrentSeason.end_exclusive.slice(0,7);
    let cursor=start;
    for(let i=0;i<38&&cursor<=end;i++){
      const first=cursor+'-01';
      if(first<jjCurrentSeason.end_exclusive)months.push(cursor);
      const d=new Date(first+'T00:00:00Z');
      d.setUTCMonth(d.getUTCMonth()+1);
      cursor=d.toISOString().slice(0,7);
    }
    return months;
  }"""
OLD_LABEL = "const label=rankMode==='archive'?'前期参考':'後期';"
NEW_LABEL = """const label=safe(rankMode==='archive'
      ? jjSeasons.find(x=>x.season_id===(season==='archive:fall'?'fall':season))?.name||'過去シーズン'
      : jjCurrentSeason?.name||'シーズン総合');"""
OLD_DATES = "$('#pointDate').min='2026-09-01T00:00';$('#pointDate').max='2027-03-31T23:59';"
NEW_DATES = """const jjActivePoints=(await api('/seasons')).find(x=>x.status==='active');
    if(jjActivePoints){
      const until=new Date(jjActivePoints.end_exclusive+'T00:00:00Z');
      until.setUTCDate(until.getUTCDate()-1);
      $('#pointDate').min=jjActivePoints.start_date+'T00:00';
      $('#pointDate').max=until.toISOString().slice(0,10)+'T23:59';
    }"""


def transform_app_js(js: str) -> str:
    for old, new in (
        (OLD_RANKING, NEW_RANKING),
        (OLD_MONTHS, NEW_MONTHS),
        (OLD_LABEL, NEW_LABEL),
        (OLD_DATES, NEW_DATES),
    ):
        if js.count(old) != 1:
            raise RuntimeError("season browser contract drift: " + old[:75])
        js = js.replace(old, new, 1)
    return js + "\n/* " + MARKER + " */\n"
