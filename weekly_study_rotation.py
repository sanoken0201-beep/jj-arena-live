"""Deterministic JST weekly GTO Wizard Japan card rotation for the compiled client.

Keep the immutable materialized v1.24.4 runtime untouched. The weekly cards
use the same validated Japanese article candidates as the learning API and
rotate in non-overlapping pairs when at least four articles are available.
"""
from __future__ import annotations

WEEKLY_MARKER = "JJ_WEEKLY_GTO_ROTATION_V1"


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise RuntimeError(f"weekly GTO card source drift: {label}")
    return source.replace(old, new, 1)


def transform_app_js(source: str) -> str:
    """Compile the weekly cards without adding requests or timers per hand."""
    if WEEKLY_MARKER in source:
        return source

    helper_start = "  function studyWeekSeed(){"
    helper_end = "  function studyCard("
    if source.count(helper_start) != 1 or source.count(helper_end) != 1:
        raise RuntimeError("weekly GTO helper anchors missing")
    start = source.index(helper_start)
    end = source.index(helper_end, start)
    source = source[:start] + """  // JJ_WEEKLY_GTO_ROTATION_V1: JST Monday midnight, stable across client timezones.
  function studyWeekSeed(nowMs=Date.now()){
    const jstDay=Math.floor((nowMs+32400000)/86400000);
    return Math.floor((jstDay+3)/7);
  }
  function studyIndex(length,nowMs=Date.now()){
    if(!length)return 0;
    const perWeek=length>=4?2:1;
    return ((studyWeekSeed(nowMs)*perWeek)%length+length)%length;
  }
""" + source[end:]

    source = _replace_once(
        source,
        """  function renderWeeklyStudy(){
    const articles=jjJapaneseStudyArticles(jjJapaneseArticleFallback);
    const offset=articles.length?studyIndex(articles.length):0;
    const selected=articles.slice(offset).concat(articles.slice(0,offset)).slice(0,2);
""",
        """  let jjWeeklyStudyItems=jjJapaneseArticleFallback;
  function renderWeeklyStudy(items){
    if(Array.isArray(items))jjWeeklyStudyItems=items;
    const articles=jjJapaneseStudyArticles(jjWeeklyStudyItems.concat(jjJapaneseArticleFallback));
    const offset=articles.length?studyIndex(articles.length):0;
    const count=articles.length>=4?2:Math.min(1,articles.length);
    const selected=articles.slice(offset).concat(articles.slice(0,offset)).slice(0,count);
""",
        "weekly source and selection",
    )

    boot = (
        "  if(document.readyState==='loading')"
        "document.addEventListener('DOMContentLoaded',renderWeeklyStudy,{once:true});"
        "else renderWeeklyStudy();"
    )
    source = _replace_once(
        source,
        "  }\n" + boot,
        """    // Refresh the cards even when these sections already exist in the SPA.
    const homeGrid=$('#weeklyStudyHome')?.querySelector('.study-grid');
    if(homeGrid)homeGrid.innerHTML=cards(true);
    const labGrid=$('#weeklyStudyLab')?.querySelector('.study-grid');
    if(labGrid)labGrid.innerHTML=cards(false);
  }
""" + boot,
        "weekly section rerender",
    )
    source = _replace_once(
        source,
        boot,
        boot + """
  document.addEventListener('visibilitychange',()=>{
    if(document.visibilityState==='visible')renderWeeklyStudy();
  });
  if(typeof window!=='undefined'&&typeof window.setTimeout==='function'){
    function scheduleWeeklyRotation(){
      const now=Date.now(),jstDay=Math.floor((now+32400000)/86400000);
      const weekday=(jstDay+3)%7;
      const nextMondayUtc=(jstDay+7-weekday)*86400000-32400000;
      const delay=Math.min(2147483647,Math.max(1000,nextMondayUtc-now+1500));
      window.setTimeout(()=>{renderWeeklyStudy();scheduleWeeklyRotation();},delay);
    }
    scheduleWeeklyRotation();
  }
""",
        "weekly rollover/visibility refresh",
    )
    source = _replace_once(
        source,
        "      const data=await api('/learning-content');\n"
        "      jjV192RenderArticles(data.articles||[]);",
        "      const data=await api('/learning-content');\n"
        "      renderWeeklyStudy(data.articles||[]);\n"
        "      jjV192RenderArticles(data.articles||[]);",
        "live article feed integration",
    )
    source = _replace_once(
        source,
        "    const result=await jjV192BaseRenderHome();\n"
        "    jjV192LearningShell();\n"
        "    jjV192RenderLearning();",
        "    const result=await jjV192BaseRenderHome();\n"
        "    renderWeeklyStudy();\n"
        "    jjV192LearningShell();\n"
        "    jjV192RenderLearning();",
        "home revisit update",
    )
    return source
