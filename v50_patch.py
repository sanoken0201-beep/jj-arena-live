from __future__ import annotations

import re
from pathlib import Path


def apply(root: Path) -> None:
    _server(root / "server.py")
    _app(root / "static" / "app.js")
    _styles(root / "static" / "styles.css")
    _index(root / "static" / "index.html")
    _sw(root / "static" / "sw.js")


def _server(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace('version="1.21.0"', 'version="1.22.0"')
    text = text.replace('"version":"1.21.0"', '"version":"1.22.0"')
    text = text.replace('request.url.query == "v=49"', 'request.url.query == "v=50"')
    path.write_text(text, encoding="utf-8")


def _app(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "v1.22.0 readable quiz and visual hand review"
    if marker in text:
        return
    pos = text.rfind("})();")
    if pos < 0:
        raise RuntimeError("v1.22.0 app closing marker missing")
    addon = r'''

  // v1.22.0 readable quiz and visual hand review.
  // Quiz difficulty belongs in the decision, not in decoding unexplained jargon.
  const jjV122RenderQuizBase=renderQuiz;
  function jjV122QuizTerms(q){
    const terms=q?.glossary||[];
    if(!terms.length)return '';
    return `<div class="jj-quiz-terms" aria-label="問題に出てくる言葉">${terms.map(x=>`<div><b>${safe(x.term)}</b><span>${safe(x.meaning)}</span></div>`).join('')}</div>`;
  }
  renderQuiz=function(){
    jjV122RenderQuizBase();
    if(quiz?.lastResult||quiz?.q?.done||!quiz?.q?.id)return;
    const prompt=$('#quizStage .jj-quiz-prompt');
    if(prompt&&!$('#quizStage .jj-quiz-terms'))prompt.insertAdjacentHTML('afterend',jjV122QuizTerms(quiz.q));
  };

  const jjV122StreetOrder=['preflop','flop','turn','river'];
  const jjV122StreetName={preflop:'PREFLOP',flop:'FLOP',turn:'TURN',river:'RIVER'};
  const jjV122ActionName={fold:'フォールド',check:'チェック',call:'コール',bet:'ベット',raise:'レイズ',allin_call:'オールインをコール',allin_raise:'オールイン',allin:'オールイン'};
  const jjV122Num=v=>Number(v||0).toFixed(1).replace(/\.0$/,'');
  const jjV122Bb=(chips,bb)=>bb>0?`${jjV122Num(Number(chips||0)/bb)}bb`:`${fmt(Number(chips||0))}`;
  function jjV122StreetBoard(board,street){const n={preflop:0,flop:3,turn:4,river:5}[street]||0;return (board||[]).slice(0,n)}
  function jjV122ActionAmount(a){
    const act=String(a.action||'');
    if(act==='raise'||act==='allin_raise')return a.to_bb==null?'':`to ${jjV122Num(a.to_bb)}bb`;
    if(act==='bet'||act==='call'||act==='allin_call'||act==='allin')return Number(a.amount_bb||0)>0?`${jjV122Num(a.amount_bb)}bb`:'';
    return '';
  }
  function jjV122ActionTimeline(actions,hero,h){
    const groups=new Map(jjV122StreetOrder.map(s=>[s,[]]));
    (actions||[]).forEach(a=>{const s=String(a.street||'preflop').toLowerCase();if(!groups.has(s))groups.set(s,[]);groups.get(s).push(a)});
    const bb=Number(h.big_blind||0),board=h.board||[];
    return [...groups.entries()].filter(([,rows])=>rows.length).map(([street,rows])=>{
      const streetBoard=jjV122StreetBoard(board,street);
      return `<section class="jj-v122-street"><header><div><span>${safe(jjV122StreetName[street]||street.toUpperCase())}</span>${streetBoard.length?`<div class="cards jj-v122-street-board">${jjCardSet(streetBoard)}</div>`:'<small>HOLE CARDS</small>'}</div><b>${rows.length} actions</b></header><div class="jj-v122-actions">${rows.map(a=>{
        const mine=Number(a.user_id)===Number(hero?.user_id),amount=jjV122ActionAmount(a),pot=jjV122Bb(a.pot_before,bb),facing=Number(a.facing_chips||0)>0?jjV122Bb(a.facing_chips,bb):'';
        return `<article class="jj-v122-action ${mine?'hero':''} ${a.timed_out?'timeout':''}"><div class="jj-v122-action-player"><span>${mine?'YOU':safe(a.player_name)}</span>${mine?`<small>${safe(a.player_name)}</small>`:''}</div><div class="jj-v122-action-main"><strong>${safe(jjV122ActionName[String(a.action||'')]||String(a.action||''))}</strong>${amount?`<b>${safe(amount)}</b>`:''}</div><div class="jj-v122-action-context"><span>Pot ${safe(pot)}</span>${facing?`<span>Facing ${safe(facing)}</span>`:''}${a.decision_seconds==null?'':`<span>${jjV122Num(a.decision_seconds)}s</span>`}${a.timed_out?'<em>TIMEOUT</em>':''}</div></article>`;
      }).join('')}</div></section>`;
    }).join('')||'<div class="empty">アクション記録なし</div>';
  }

  jjOpenHand=async function(handId){
    const data=await api(`/analysis/hands/${encodeURIComponent(handId)}`),h=data.hand||{},players=data.players||[],actions=data.actions||[],hero=players.find(p=>Number(p.user_id)===Number(me.id))||players[0]||{};
    const net=Number(hero.net_bb||0),start=Number(hero.starting_stack_bb||0),effective=Number(hero.effective_stack_bb||0),bb=Number(h.big_blind||0),result=(h.summary||{}).message||h.result_type||'—';
    const timeline=jjV122ActionTimeline(actions,hero,h);
    openModal(`<div class="jj-review-shell jj-v122-review">
      <header class="jj-v122-review-head">
        <div class="jj-v122-title"><div class="eyebrow">HAND REVIEW</div><h3>${safe(h.table_name||h.table_id)} · #${safe(String(h.hand_no||h.hand_id))}</h3><p>${safe(jjAnalysisDate(h.completed_at))}</p></div>
        <div class="jj-v122-result"><span>RESULT</span><strong class="${net>=0?'positive':'negative'}">${safe(jjSigned(net))}</strong><small>${safe(result)}</small></div>
      </header>
      <section class="jj-v122-cards-zone">
        <div class="jj-v122-hero-hand"><span>YOUR HAND</span><div class="cards">${jjCardSet(hero.cards)}</div></div>
        <div class="jj-v122-board"><span>BOARD</span><div class="cards">${jjCardSet(h.board)}</div></div>
      </section>
      <div class="jj-v122-facts">
        <div><span>POSITION</span><strong>${safe(hero.position||'—')}</strong></div>
        <div><span>START</span><strong>${start?`${jjV122Num(start)}bb`:'—'}</strong></div>
        <div><span>EFFECTIVE</span><strong>${effective?`${jjV122Num(effective)}bb`:'—'}</strong></div>
        <div><span>BLINDS</span><strong>${bb?`${fmt(h.small_blind||0)} / ${fmt(bb)}`:'—'}</strong></div>
        <div><span>REACHED</span><strong>${safe(String(h.reached_street||'preflop').toUpperCase())}</strong></div>
        <div><span>SHOWDOWN</span><strong>${h.showdown?'YES':'NO'}</strong></div>
      </div>
      ${h.partial_capture?'<div class="notice">このハンドは記録開始・再起動の途中から取得されたため、集計統計からは除外しています。</div>':''}
      <div class="jj-v122-review-grid">
        <main class="jj-v122-review-main">
          <section class="jj-v122-timeline-panel"><div class="section-head"><div><div class="eyebrow">ACTION FLOW</div><h4>アクションの流れ</h4><p>ストリートごとに、ポットとベット額を確認できます。自分の判断は強調表示しています。</p></div></div>${timeline}</section>
          <details class="jj-v122-replay-details"><summary><span><b>テーブルリプレイ</b><small>必要なときだけ盤面全体を確認</small></span><span id="jjReplayCounter"></span></summary><div class="jj-replayer"><div id="jjReplayStage"></div><div class="jj-replay-controls"><button class="soft" id="jjReplayPrev">← 前へ</button><button class="primary" id="jjReplayNext">次へ →</button></div></div></details>
        </main>
        <aside class="jj-v122-review-side">
          <form id="jjHandReviewForm" class="jj-review-form stack jj-v122-note-card">
            <div><div class="eyebrow">YOUR REVIEW</div><h4>このハンドから残すこと</h4><p>判断理由や、次に同じ状況が来たとき確認したいことを記録します。</p></div>
            <label class="jj-review-bookmark"><input name="bookmarked" type="checkbox" ${data.review?.bookmarked?'checked':''}> ★ ブックマーク</label>
            <label>タグ<input name="tags" value="${safe((data.review?.tags||[]).join(', '))}" placeholder="例: 3bet pot, bluff catch"></label>
            <label>メモ<textarea name="note" rows="8" maxlength="4000" placeholder="例：ターンで相手の続行レンジを狭く見積もりすぎた">${safe(data.review?.note||'')}</textarea></label>
            <div class="jj-review-actions"><button class="primary" type="submit">保存</button><button class="soft" type="button" id="jjExportHand">HHテキスト</button></div>
          </form>
          <p class="jj-v122-privacy">相手のホールカードは、ショーダウンで実際に公開された場合だけ表示します。</p>
        </aside>
      </div>
    </div>`);
    let replayIndex=0;
    const renderReplay=()=>{const snaps=data.snapshots||[],snap=snaps[Math.min(replayIndex,Math.max(0,snaps.length-1))];jjRenderReplayStage(snap?.state||{},players,hero?.user_id);if($('#jjReplayCounter'))$('#jjReplayCounter').textContent=snaps.length?`${replayIndex+1} / ${snaps.length}`:'—';if($('#jjReplayPrev'))$('#jjReplayPrev').disabled=replayIndex<=0;if($('#jjReplayNext'))$('#jjReplayNext').disabled=!snaps.length||replayIndex>=snaps.length-1};
    if($('#jjReplayPrev'))$('#jjReplayPrev').onclick=()=>{replayIndex=Math.max(0,replayIndex-1);renderReplay()};
    if($('#jjReplayNext'))$('#jjReplayNext').onclick=()=>{replayIndex=Math.min((data.snapshots||[]).length-1,replayIndex+1);renderReplay()};
    renderReplay();
    $('#jjExportHand').onclick=()=>jjDownload(`/analysis/hands/${encodeURIComponent(handId)}/export.txt`,`jj-${handId}.txt`);
    $('#jjHandReviewForm').onsubmit=async e=>{e.preventDefault();const fd=new FormData(e.target),tags=String(fd.get('tags')||'').split(',').map(x=>x.trim()).filter(Boolean);try{await api(`/analysis/hands/${encodeURIComponent(handId)}/review`,{method:'PUT',body:JSON.stringify({bookmarked:fd.get('bookmarked')==='on',note:String(fd.get('note')||''),tags})});toast('ハンドレビューを保存しました');await jjLoadHands(true)}catch(err){toast(err.message)}};
  };
'''
    path.write_text(text[:pos] + addon + "\n" + text[pos:], encoding="utf-8")


def _styles(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "/* v1.22.0 readable quiz and visual hand review */"
    if marker in text:
        return
    addon = r'''

/* v1.22.0 readable quiz and visual hand review */
.jj-quiz-terms{display:grid;gap:6px;margin:-2px 0 16px;padding:10px 12px;border:1px solid var(--line);border-radius:12px;background:#f8faf9}.jj-quiz-terms>div{display:grid;grid-template-columns:minmax(80px,.34fr) 1fr;gap:10px;align-items:start;font-size:12px;line-height:1.5}.jj-quiz-terms b{color:var(--ink);font-size:12px}.jj-quiz-terms span{color:var(--muted)}
.jj-v122-review{width:min(1120px,calc(100vw - 56px));max-width:none}.jj-v122-review-head{display:flex;justify-content:space-between;gap:24px;align-items:flex-start;padding-bottom:14px;border-bottom:1px solid var(--line)}.jj-v122-title h3{margin:4px 0;font-size:22px}.jj-v122-title p{margin:0;color:var(--muted);font-size:12px}.jj-v122-result{min-width:150px;text-align:right}.jj-v122-result>span,.jj-v122-cards-zone span,.jj-v122-facts span{display:block;font-size:10px;font-weight:850;letter-spacing:.09em;color:var(--muted)}.jj-v122-result strong{display:block;font-size:30px;line-height:1.1;margin:3px 0}.jj-v122-result small{display:block;max-width:260px;margin-left:auto;line-height:1.35;color:var(--muted)}
.jj-v122-cards-zone{display:grid;grid-template-columns:minmax(180px,.7fr) minmax(360px,1.3fr);gap:12px;margin:14px 0}.jj-v122-cards-zone>div{padding:14px 16px;border:1px solid var(--line);border-radius:15px;background:#f8faf9}.jj-v122-cards-zone .cards{margin-top:8px;display:flex;gap:6px;flex-wrap:wrap}.jj-v122-cards-zone .card-face{width:48px;height:64px;font-size:1.05rem}.jj-v122-hero-hand{box-shadow:inset 3px 0 0 var(--accent,#18825c)}
.jj-v122-facts{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:7px;margin-bottom:16px}.jj-v122-facts>div{padding:9px 10px;border-radius:11px;background:#f5f8f6;border:1px solid #edf2ef}.jj-v122-facts strong{display:block;margin-top:3px;font-size:13px;font-variant-numeric:tabular-nums}
.jj-v122-review-grid{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(280px,.7fr);gap:16px;align-items:start}.jj-v122-timeline-panel{border:1px solid var(--line);border-radius:16px;padding:15px;background:#fff}.jj-v122-timeline-panel h4,.jj-v122-note-card h4{margin:3px 0}.jj-v122-timeline-panel .section-head p,.jj-v122-note-card>div p{margin:3px 0 0;color:var(--muted);font-size:12px;line-height:1.45}.jj-v122-street{margin-top:14px;border:1px solid var(--line);border-radius:14px;overflow:hidden;background:#fff}.jj-v122-street>header{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:9px 11px;background:#f5f8f6;border-bottom:1px solid var(--line)}.jj-v122-street>header>div{display:flex;align-items:center;gap:10px;min-width:0}.jj-v122-street>header>div>span{font-size:11px;font-weight:950;letter-spacing:.09em}.jj-v122-street>header small,.jj-v122-street>header>b{font-size:10px;color:var(--muted);font-weight:700}.jj-v122-street-board{display:flex;gap:3px}.jj-v122-street-board .card-face{width:24px;height:32px;font-size:.55rem}
.jj-v122-actions{display:grid}.jj-v122-action{display:grid;grid-template-columns:minmax(92px,.7fr) minmax(150px,1fr) minmax(165px,1.1fr);gap:10px;align-items:center;padding:9px 11px;border-bottom:1px solid #eef2f0}.jj-v122-action:last-child{border-bottom:0}.jj-v122-action.hero{background:#eef8f3;box-shadow:inset 4px 0 0 var(--accent,#18825c)}.jj-v122-action.timeout{background:#fff8ef}.jj-v122-action-player>span{display:block;font-size:12px;font-weight:850;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.jj-v122-action-player>small{display:block;font-size:9px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.jj-v122-action.hero .jj-v122-action-player>span{color:var(--accent,#18825c);font-weight:950}.jj-v122-action-main{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}.jj-v122-action-main strong{font-size:14px}.jj-v122-action-main b{font-size:13px;font-variant-numeric:tabular-nums}.jj-v122-action-context{display:flex;justify-content:flex-end;gap:8px;flex-wrap:wrap}.jj-v122-action-context span{padding:3px 6px;border-radius:7px;background:#f4f6f5;color:#5d6b63;font-size:10px;font-variant-numeric:tabular-nums}.jj-v122-action-context em{font-size:9px;font-style:normal;font-weight:900;color:#a35e17}
.jj-v122-review-side{position:sticky;top:10px}.jj-v122-note-card{padding:15px;background:#f8faf9}.jj-v122-note-card textarea{resize:vertical;min-height:150px}.jj-v122-privacy{margin:9px 3px 0;color:var(--muted);font-size:10px;line-height:1.5}.jj-v122-replay-details{margin-top:12px;border:1px solid var(--line);border-radius:14px;background:#fff;overflow:hidden}.jj-v122-replay-details>summary{display:flex;justify-content:space-between;gap:10px;align-items:center;cursor:pointer;padding:12px 14px;list-style:none}.jj-v122-replay-details>summary::-webkit-details-marker{display:none}.jj-v122-replay-details>summary span:first-child{display:flex;flex-direction:column;gap:2px}.jj-v122-replay-details>summary b{font-size:13px}.jj-v122-replay-details>summary small{font-size:10px;color:var(--muted)}.jj-v122-replay-details .jj-replayer{border:0;border-top:1px solid var(--line);border-radius:0;margin:0;padding:14px}
@media(max-width:900px){.jj-v122-review{width:min(760px,calc(100vw - 32px))}.jj-v122-review-grid{grid-template-columns:1fr}.jj-v122-review-side{position:static}.jj-v122-facts{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:640px){.jj-quiz-terms>div{grid-template-columns:1fr;gap:2px}.jj-v122-review{width:calc(100vw - 22px)}.jj-v122-review-head{gap:10px}.jj-v122-title h3{font-size:17px}.jj-v122-result{min-width:92px}.jj-v122-result strong{font-size:24px}.jj-v122-result small{font-size:9px}.jj-v122-cards-zone{grid-template-columns:1fr}.jj-v122-cards-zone>div{padding:11px}.jj-v122-cards-zone .card-face{width:42px;height:57px}.jj-v122-facts{grid-template-columns:repeat(2,minmax(0,1fr))}.jj-v122-timeline-panel{padding:10px}.jj-v122-street>header{align-items:flex-start}.jj-v122-street>header>div{align-items:flex-start;flex-direction:column;gap:5px}.jj-v122-action{grid-template-columns:78px 1fr;gap:5px 8px;padding:9px}.jj-v122-action-context{grid-column:2;justify-content:flex-start}.jj-v122-action-main strong{font-size:13px}.jj-v122-action-main b{font-size:12px}.jj-v122-review .jj-replay-table{min-height:245px}.jj-v122-note-card textarea{min-height:120px}}
'''
    path.write_text(text.rstrip() + addon + "\n", encoding="utf-8")


def _index(path: Path) -> None:
    text = path.read_text(encoding="utf-8").replace("?v=49", "?v=50")
    path.write_text(text, encoding="utf-8")


def _sw(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"jj-arena-live-v49(?:-[A-Za-z0-9_-]+)?", "jj-arena-live-v50", text)
    path.write_text(text, encoding="utf-8")
