from __future__ import annotations

import re
from pathlib import Path


def apply(root: Path) -> None:
    _server(root / "server.py")
    _app(root / "static" / "app.js")
    _index(root / "static" / "index.html")
    _sw(root / "static" / "sw.js")


def _server(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace('version="1.20.0"', 'version="1.20.1"')
    text = text.replace('"version":"1.20.0"', '"version":"1.20.1"')
    text = text.replace('request.url.query == "v=44"', 'request.url.query == "v=46"')
    path.write_text(text, encoding="utf-8")


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"v1.20.1 {label} target mismatch: {text.count(old)}")
    return text.replace(old, new, 1)


def _app(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "v1.20.1 analysis request/replay stabilization" in text:
        return

    old_load = """  async function jjAnalysisLoad(resetHands=false){if(jjAnalysisState.loading)return;jjAnalysisState.loading=true;$('#analysisView')?.classList.add('jj-loading');try{const summary=await api(`/analysis/summary?range=${encodeURIComponent(jjAnalysisState.range)}`);jjAnalysisState.summary=summary;jjRenderAnalysisSummary(summary);if(resetHands){jjAnalysisState.offset=0;await jjLoadHands(true)}}finally{jjAnalysisState.loading=false;$('#analysisView')?.classList.remove('jj-loading')}}"""
    new_load = """  // v1.20.1 analysis request/replay stabilization\n  async function jjAnalysisLoad(resetHands=false){const seq=Number(jjAnalysisState.analysisRequestSeq||0)+1,requestedRange=jjAnalysisState.range;jjAnalysisState.analysisRequestSeq=seq;jjAnalysisState.loading=true;$('#analysisView')?.classList.add('jj-loading');try{const summary=await api(`/analysis/summary?range=${encodeURIComponent(requestedRange)}`);if(seq!==jjAnalysisState.analysisRequestSeq||requestedRange!==jjAnalysisState.range)return;jjAnalysisState.summary=summary;jjRenderAnalysisSummary(summary);if(resetHands){jjAnalysisState.offset=0;await jjLoadHands(true)}}finally{if(seq===jjAnalysisState.analysisRequestSeq){jjAnalysisState.loading=false;$('#analysisView')?.classList.remove('jj-loading')}}}"""
    text = _replace_once(text, old_load, new_load, "summary request")

    old_hands = """  async function jjLoadHands(reset){const box=$('#jjHandList');if(!box)return;if(reset){jjAnalysisState.offset=0;box.innerHTML='<div class=\"empty\">読み込み中…</div>'}const data=await api('/analysis/hands?'+jjHandQuery().toString());jjAnalysisState.total=Number(data.total||0);jjAnalysisState.hands=reset?(data.items||[]):[...jjAnalysisState.hands,...(data.items||[])];jjRenderHands()}"""
    new_hands = """  async function jjLoadHands(reset){const box=$('#jjHandList');if(!box)return;if(!reset&&jjAnalysisState.handLoading)return;const seq=Number(jjAnalysisState.handRequestSeq||0)+1,query=jjHandQuery().toString();jjAnalysisState.handRequestSeq=seq;jjAnalysisState.handLoading=true;if(reset){jjAnalysisState.offset=0;box.innerHTML='<div class=\"empty\">読み込み中…</div>'}try{const data=await api('/analysis/hands?'+query);if(seq!==jjAnalysisState.handRequestSeq)return;jjAnalysisState.total=Number(data.total||0);jjAnalysisState.hands=reset?(data.items||[]):[...jjAnalysisState.hands,...(data.items||[])];jjRenderHands()}finally{if(seq===jjAnalysisState.handRequestSeq)jjAnalysisState.handLoading=false}}"""
    text = _replace_once(text, old_hands, new_hands, "hand list request")

    old_replay = """  function jjRenderReplayStage(state,players,heroId){const box=$('#jjReplayStage');if(!box)return;if(!state?.hand){box.innerHTML='<div class=\"empty\">リプレイ用スナップショットがありません</div>';return}const cardsById=new Map(players.map(p=>[Number(p.user_id),p.cards||[]])),seats=state.seats||[],max=6;box.innerHTML=`<div class=\"jj-replay-table\"><div class=\"jj-replay-center\"><div class=\"cards\">${jjCardSet(state.hand.board||[])}</div><b>${safe(String(state.hand.phase||'').toUpperCase())}</b></div>${seats.map(p=>{const angle=(-90+Number(p.seat||0)*(360/max))*Math.PI/180,left=50+Math.cos(angle)*41,top=49+Math.sin(angle)*37,cards=cardsById.get(Number(p.user_id))||[];return `<div class=\"jj-replay-seat ${Number(p.user_id)===Number(heroId)?'hero':''} ${p.folded?'folded':''}\" style=\"left:${left}%;top:${top}%\"><strong>${safe(p.name)}</strong><span>${(Number(p.stack||0)/Math.max(1,Number(state.big_blind||100))).toFixed(1)}bb</span>${Number(p.user_id)===Number(heroId)||cards.some(c=>c!=='??')?`<div class=\"cards jj-tiny-cards\">${jjCardSet(cards)}</div>`:''}</div>`}).join('')}</div>`}"""
    new_replay = """  function jjRenderReplayStage(state,players,heroId){const box=$('#jjReplayStage');if(!box)return;if(!state?.hand){box.innerHTML='<div class=\"empty\">リプレイ用スナップショットがありません</div>';return}const cardsById=new Map(players.map(p=>[Number(p.user_id),p.cards||[]])),seats=state.seats||[],max=6,phase=String(state.hand.phase||'').toLowerCase(),showdownVisible=phase==='complete';box.innerHTML=`<div class=\"jj-replay-table\"><div class=\"jj-replay-center\"><div class=\"cards\">${jjCardSet(state.hand.board||[])}</div><b>${safe(String(state.hand.phase||'').toUpperCase())}</b></div>${seats.map(p=>{const angle=(-90+Number(p.seat||0)*(360/max))*Math.PI/180,left=50+Math.cos(angle)*41,top=49+Math.sin(angle)*37,cards=cardsById.get(Number(p.user_id))||[],hero=Number(p.user_id)===Number(heroId),revealed=showdownVisible&&cards.some(c=>c!=='??'),shown=hero?cards:revealed?cards:(p.in_hand?['??','??']:[]);return `<div class=\"jj-replay-seat ${hero?'hero':''} ${p.folded?'folded':''}\" style=\"left:${left}%;top:${top}%\"><strong>${safe(p.name)}</strong><span>${(Number(p.stack||0)/Math.max(1,Number(state.big_blind||100))).toFixed(1)}bb</span>${shown.length?`<div class=\"cards jj-tiny-cards\">${jjCardSet(shown)}</div>`:''}</div>`}).join('')}</div>`}"""
    text = _replace_once(text, old_replay, new_replay, "replay card timing")
    path.write_text(text, encoding="utf-8")


def _index(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace("?v=44", "?v=46")
    path.write_text(text, encoding="utf-8")


def _sw(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"jj-arena-live-v\d+", "jj-arena-live-v46", text)
    path.write_text(text, encoding="utf-8")
