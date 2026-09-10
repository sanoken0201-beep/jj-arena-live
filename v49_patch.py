from __future__ import annotations

import re
from pathlib import Path


def apply(root: Path) -> None:
    _server(root / "server.py")
    _engine(root / "poker_engine.py")
    _app(root / "static" / "app.js")
    _styles(root / "static" / "styles.css")
    _index(root / "static" / "index.html")
    _sw(root / "static" / "sw.js")


def _server(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace('version="1.20.3"', 'version="1.21.0"')
    text = text.replace('"version":"1.20.3"', '"version":"1.21.0"')
    text = text.replace('request.url.query == "v=48"', 'request.url.query == "v=49"')

    model_old = "class ActionIn(BaseModel):\n    action: str\n    amount: int | None = None"
    model_new = "class ActionIn(BaseModel):\n    action: str\n    amount: int | None = None\n    action_id: str | None = Field(default=None, min_length=8, max_length=80)"
    if model_old in text:
        text = text.replace(model_old, model_new, 1)
    elif "action_id: str | None" not in text:
        raise RuntimeError("v1.21.0 ActionIn target missing")

    pattern = re.compile(
        r'@app\.post\("/api/tables/\{table_id\}/action"\)\n'
        r'async def action\(table_id: str, payload: ActionIn, user=Depends\(current_user\)\):\n'
        r'.*?\n    return public_state\(state,user\["id"\]\)', re.DOTALL)
    replacement = '''@app.post("/api/tables/{table_id}/action")
async def action(table_id: str, payload: ActionIn, user=Depends(current_user)):
    async with get_table_lock(table_id):
        state = load_table(table_id)
        receipt = str(payload.action_id or "").strip()
        processed = list(state.get("_processed_action_ids") or [])
        if receipt and receipt in processed:
            return public_state(state, user["id"])
        try:
            apply_action(state, user["id"], payload.action, payload.amount)
        except ValueError as e:
            raise HTTPException(400, str(e))
        if receipt:
            state["_processed_action_ids"] = (processed + [receipt])[-120:]
        arm_action_deadline(state)
        save_table(state)
    await hub.broadcast(table_id)
    return public_state(state, user["id"])'''
    text, n = pattern.subn(replacement, text, count=1)
    if n != 1 and "_processed_action_ids" not in text:
        raise RuntimeError(f"v1.21.0 action endpoint target mismatch: {n}")

    # Persist errors already caught by the long-lived loops instead of only printing.
    text = text.replace(
        'print(f"JJ_TIMEOUT_LOOP_ERROR {type(exc).__name__}")',
        'import resilience as _jj_resilience; _jj_resilience.record_error(db, "timeout_loop", f"{type(exc).__name__}: {exc}")'
    )
    text = text.replace(
        'print(f"JJ_WS_CONNECTION_ERROR {type(exc).__name__}")',
        'import resilience as _jj_resilience; _jj_resilience.record_error(db, "websocket", f"{type(exc).__name__}: {exc}", path=table_id)'
    )
    path.write_text(text, encoding="utf-8")


def _engine(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old = 'out = {k: v for k, v in state.items() if k not in ("seats", "hand")};'
    new = 'out = {k: v for k, v in state.items() if k not in ("seats", "hand", "_processed_action_ids")};'
    if old in text:
        text = text.replace(old, new, 1)
    elif '"_processed_action_ids"' not in text:
        raise RuntimeError("v1.21.0 public_state target missing")
    path.write_text(text, encoding="utf-8")


def _app(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "v1.21.0 learning and home hub"
    if marker in text:
        return
    pos = text.rfind("})();")
    if pos < 0:
        raise RuntimeError("v1.21.0 app closing marker missing")
    addon = r'''

  // v1.21.0 learning and home hub.
  let jjV121ActionPending=false;
  const jjV121ActionId=()=>globalThis.crypto?.randomUUID?.()||`jj-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  doAction=async function(action){
    if(!currentTableId||jjV121ActionPending)return;
    jjV121ActionPending=true;
    const body={action,action_id:jjV121ActionId()};
    if(action==='raise')body.amount=Math.round(Number($('#raiseTo')?.value||0)*Number(tableState.big_blind||100));
    try{
      try{await post(`/tables/${currentTableId}/action`,body)}
      catch(err){if(!(err instanceof TypeError))throw err;await new Promise(r=>setTimeout(r,450));await post(`/tables/${currentTableId}/action`,body)}
    }catch(err){toast(err.message)}finally{jjV121ActionPending=false}
  };

  const jjV121Confidence=v=>({high:'信頼度 高',medium:'信頼度 中',low:'参考値'})[v]||'参考値';
  function jjV121EnsureLearning(){
    const view=$('#analysisView');if(!view||$('#jjLearningCoach'))return;
    const box=document.createElement('section');box.id='jjLearningCoach';box.className='card jj-learning-coach';
    box.innerHTML=`<div class="section-head"><div><div class="eyebrow">RECENT TENDENCIES</div><h3>最近の傾向から学ぶ</h3><p>Solverの正解判定ではなく、JJ Arenaで実際に観測された頻度から復習候補を出します。</p></div><span id="jjLearningPolicy" class="hint">OBSERVED DATA</span></div><div id="jjLearningSignals" class="jj-learning-signals"><div class="empty">集計中…</div></div>`;
    const hero=view.querySelector('.jj-analysis-hero');if(hero)hero.insertAdjacentElement('afterend',box);else view.prepend(box);
  }
  async function jjV121LoadLearning(){
    jjV121EnsureLearning();if(!$('#jjLearningSignals'))return;
    try{
      const data=await api(`/analysis/learning?range=${encodeURIComponent(jjAnalysisState?.range||'30d')}`),items=data.signals?.length?data.signals:[data.recommended];
      $('#jjLearningSignals').innerHTML=items.map(x=>`<article class="jj-learning-signal ${safe(x.severity||'info')}"><div class="jj-learning-meta"><span>${safe(x.metric||'DATA')}</span><b>${safe(jjV121Confidence(x.confidence))} · n=${fmt(x.sample_size||0)}</b></div><h4>${safe(x.title||'')}</h4><p class="jj-learning-fact">${safe(x.fact||'')}</p><p>${safe(x.candidate||'')}</p><div class="jj-learning-target">今日の復習：<b>${safe(x.study_target||'ハンドレビュー')}</b></div></article>`).join('');
      if($('#jjLearningPolicy'))$('#jjLearningPolicy').textContent=data.policy?.solver_used===false?'SOLVER判定なし':'OBSERVED DATA';
    }catch(err){$('#jjLearningSignals').innerHTML=`<div class="empty">${safe(err.message)}</div>`}
  }
  if(typeof jjAnalysisLoad==='function'){
    const jjV121AnalysisLoad=jjAnalysisLoad;
    jjAnalysisLoad=async function(resetHands=false){const v=await jjV121AnalysisLoad(resetHands);await jjV121LoadLearning();return v};
  }

  function jjV121EnsureHomeHub(){
    const home=$('#homeView');if(!home||$('#jjHomeHub'))return;
    const hub=document.createElement('section');hub.id='jjHomeHub';hub.className='jj-home-hub';
    hub.innerHTML=`<div class="section-head"><div><div class="eyebrow">YOUR JJ ARENA</div><h3>プレイ・学習・ポイントをここから。</h3></div><button class="soft" id="jjHomeHubRefresh">更新</button></div><div id="jjHomeHubGrid" class="jj-home-hub-grid"><div class="card empty">読み込み中…</div></div><div id="jjHomeArticles" class="card jj-home-articles"></div>`;
    const hero=home.querySelector('.hero-grid');if(hero)hero.insertAdjacentElement('afterend',hub);else home.prepend(hub);
    $('#jjHomeHubRefresh')?.addEventListener('click',jjV121LoadHomeHub);
  }
  const jjV121Signed=v=>{const n=Number(v||0);return `${n>0?'+':''}${Number.isInteger(n)?n:n.toFixed(1)}bb`};
  async function jjV121LoadHomeHub(){
    if(!me)return;jjV121EnsureHomeHub();
    try{
      const d=await api('/home/overview'),q=d.quiz||{},p=d.points||{},perf=d.performance||{},learn=d.learning||{},hands=d.recent_hands||[];
      $('#jjHomeHubGrid').innerHTML=`
        <article class="card jj-hub-card"><span>現在の後期ポイント</span><strong>${fmt(p.season_total||0)} pt</strong><small>${p.rank?`#${p.rank} in ranking`:'ランキング集計中'}</small><button class="soft" data-jj-go="ranking">ランキング</button></article>
        <article class="card jj-hub-card"><span>今日のクイズ</span><strong>${fmt(q.answered||0)} / ${fmt(q.total||10)}</strong><small>${fmt(q.correct||0)}正解 · +${fmt(q.earned||0)}pt</small><button class="primary" data-jj-go="lab">続きを解く</button></article>
        <article class="card jj-hub-card"><span>直近30日</span><strong class="${Number(perf.net_bb_30d||0)>=0?'positive':'negative'}">${safe(jjV121Signed(perf.net_bb_30d||0))}</strong><small>${fmt(perf.hands_30d||0)} hands · ${perf.bb_per_100==null?'—':safe(jjV121Signed(perf.bb_per_100))}/100</small><button class="soft" data-jj-go="analysis">ハンド分析</button></article>
        <article class="card jj-hub-card jj-hub-learning"><span>今日のおすすめ学習</span><strong>${safe(learn.title||'ハンドレビュー')}</strong><small>${safe(learn.fact||'プレイデータが増えると傾向を表示します。')}</small><button class="soft" data-jj-go="analysis">傾向を見る</button></article>
        <article class="card jj-hub-card jj-hub-hands"><span>最近のハンド</span><div>${hands.length?hands.map(h=>`<button data-jj-hand="${safe(h.hand_id)}"><b>${safe(h.position||'—')}</b><em class="${Number(h.net_bb||0)>=0?'positive':'negative'}">${safe(jjV121Signed(h.net_bb||0))}</em><small>${safe(jjAnalysisDate?.(h.completed_at)||'')}</small></button>`).join(''):'<small>オンラインハンドが記録されると表示します。</small>'}</div><button class="soft" data-jj-go="analysis">履歴を開く</button></article>`;
      const articles=d.articles||[];
      $('#jjHomeArticles').innerHTML=`<div class="section-head"><div><div class="eyebrow">LEARN</div><h3>記事・学習コンテンツ</h3></div><button class="text-btn" data-jj-go="lab">学習を開く →</button></div>${articles.length?`<div class="jj-home-article-grid">${articles.map(a=>`<a href="${safe(a.url)}" target="_blank" rel="noopener"><span>${safe(a.source||'')}</span><strong>${safe(a.title||'')}</strong><small>${safe(a.topic||'')}</small></a>`).join('')}</div>`:'<div class="empty">学習コンテンツを読み込み中です。</div>'}`;
    }catch(err){if($('#jjHomeHubGrid'))$('#jjHomeHubGrid').innerHTML=`<div class="card empty">${safe(err.message)}</div>`}
  }
  document.addEventListener('click',e=>{
    const go=e.target.closest('[data-jj-go]');if(go)switchView(go.dataset.jjGo);
    const hand=e.target.closest('[data-jj-hand]');if(hand){switchView('analysis');setTimeout(()=>jjOpenHand?.(hand.dataset.jjHand).catch(err=>toast(err.message)),100)}
  });
  const jjV121OldRenderHome=renderHome;
  renderHome=async function(){const r=await jjV121OldRenderHome();await jjV121LoadHomeHub();return r};
  jjV121EnsureHomeHub();
'''
    path.write_text(text[:pos] + addon + "\n" + text[pos:], encoding="utf-8")


def _styles(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "/* v1.21.0 learning and home hub */"
    if marker in text:
        return
    addon = r'''

/* v1.21.0 learning and home hub */
.jj-learning-coach{margin:18px 0;padding:20px}.jj-learning-signals{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.jj-learning-signal{border:1px solid var(--line);border-radius:16px;padding:15px;background:var(--panel)}.jj-learning-signal h4{margin:7px 0;font-size:17px}.jj-learning-signal p{margin:6px 0;line-height:1.55}.jj-learning-fact{font-weight:700}.jj-learning-meta{display:flex;justify-content:space-between;gap:10px;font-size:11px;letter-spacing:.04em}.jj-learning-meta b{font-weight:600;opacity:.72}.jj-learning-target{margin-top:10px;padding-top:10px;border-top:1px solid var(--line);font-size:12px}
.jj-home-hub{margin:18px 0 24px}.jj-home-hub-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.jj-hub-card{display:flex;flex-direction:column;gap:8px;padding:17px}.jj-hub-card>span{font-size:12px;opacity:.72}.jj-hub-card>strong{font-size:24px;line-height:1.15}.jj-hub-card>small{line-height:1.45;min-height:34px}.jj-hub-card>button{margin-top:auto}.jj-hub-learning{grid-column:span 2}.jj-hub-learning>strong{font-size:18px}.jj-hub-hands{grid-column:span 2}.jj-hub-hands>div{display:grid;gap:6px}.jj-hub-hands>div>button{display:grid;grid-template-columns:52px 64px 1fr;gap:8px;align-items:center;text-align:left;border:0;border-bottom:1px solid var(--line);background:transparent;padding:7px 0}.jj-hub-hands em{font-style:normal;font-weight:800}.jj-home-articles{margin-top:12px;padding:18px}.jj-home-article-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.jj-home-article-grid a{display:flex;flex-direction:column;gap:6px;border:1px solid var(--line);border-radius:14px;padding:13px;color:inherit;text-decoration:none}.jj-home-article-grid span,.jj-home-article-grid small{font-size:11px;opacity:.7}
@media(max-width:900px){.jj-home-hub-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.jj-home-article-grid{grid-template-columns:1fr}.jj-learning-signals{grid-template-columns:1fr}}
@media(max-width:560px){.jj-home-hub-grid{grid-template-columns:1fr}.jj-hub-learning,.jj-hub-hands{grid-column:auto}.jj-learning-coach{padding:14px}.jj-learning-meta{align-items:flex-start;flex-direction:column}}
'''
    path.write_text(text.rstrip() + addon + "\n", encoding="utf-8")


def _index(path: Path) -> None:
    path.write_text(path.read_text(encoding="utf-8").replace("?v=48", "?v=49"), encoding="utf-8")


def _sw(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"jj-arena-live-v48", "jj-arena-live-v49", text)
    path.write_text(text, encoding="utf-8")
