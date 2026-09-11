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
    text = text.replace('version="1.24.3"', 'version="1.24.4"')
    text = text.replace('"version":"1.24.3"', '"version":"1.24.4"')
    text = text.replace('request.url.query == "v=55"', 'request.url.query == "v=56"')
    marker = "v1.24.4 analysis focus-hand endpoint"
    if marker not in text:
        addon = r'''

# v1.24.4 analysis focus-hand endpoint
# Read-only bridge from an observed aggregate tendency to the exact recent hands
# that formed that metric's denominator. It does not score decisions or alter
# poker state, ranking, points, or stored analytics.
from datetime import datetime as _jj_v1244_datetime, timedelta as _jj_v1244_timedelta, timezone as _jj_v1244_timezone

_JJ_V1244_FOCUS_SQL = {
    "vpip_pfr_gap": "p.vpip=1 AND p.pfr=0",
    "fold_to_3bet": "p.faced_three_bet=1",
    "three_bet": "p.three_bet_opp=1",
    "cbet": "p.cbet_opp=1",
    "position_vpip": "p.position IN ('UTG','UTG+1','MP','LJ','HJ','CO','BTN','BTN/SB')",
    "timeout": "p.timeout_count>0",
}


def _jj_v1244_focus_start(range_name: str):
    days = {"7d": 7, "30d": 30, "90d": 90}.get(str(range_name or "all"))
    if not days:
        return None
    return (_jj_v1244_datetime.now(_jj_v1244_timezone.utc) - _jj_v1244_timedelta(days=days)).isoformat()


@app.get("/api/analysis/focus-hands")
def jj_v1244_analysis_focus_hands(metric: str, range: str = "all", limit: int = 12, user=Depends(current_user)):
    condition = _JJ_V1244_FOCUS_SQL.get(str(metric or ""))
    if condition is None:
        raise HTTPException(status_code=400, detail="未対応の分析指標です")
    limit = max(1, min(24, int(limit or 12)))
    where = ["p.user_id=?", "h.completed_at IS NOT NULL", "COALESCE(h.partial_capture,0)=0", condition]
    params = [int(user["id"])]
    start = _jj_v1244_focus_start(range)
    if start:
        where.append("h.completed_at>=?")
        params.append(start)
    params.append(limit)
    sql = f"""
      SELECT h.hand_id,h.table_id,h.table_name,h.hand_no,h.completed_at,h.reached_street,h.showdown,
             p.position,p.net_bb,p.starting_stack_bb,p.effective_stack_bb,p.vpip,p.pfr,
             p.three_bet_opp,p.three_bet,p.faced_three_bet,p.folded_to_three_bet,
             p.cbet_opp,p.cbet,p.timeout_count
      FROM jj_hand_players p
      JOIN jj_hand_history h ON h.hand_id=p.hand_id
      WHERE {' AND '.join(where)}
      ORDER BY h.completed_at DESC
      LIMIT ?
    """
    with db.connect() as con:
        rows = con.execute(sql, tuple(params)).fetchall()
    out = []
    for row in rows:
        r = dict(row)
        out.append({
            "hand_id": str(r.get("hand_id") or ""),
            "table_id": str(r.get("table_id") or ""),
            "table_name": str(r.get("table_name") or ""),
            "hand_no": int(r.get("hand_no") or 0),
            "completed_at": r.get("completed_at"),
            "reached_street": str(r.get("reached_street") or "preflop"),
            "showdown": bool(r.get("showdown")),
            "position": str(r.get("position") or "—"),
            "net_bb": float(r.get("net_bb") or 0),
            "starting_stack_bb": float(r.get("starting_stack_bb") or 0),
            "effective_stack_bb": float(r.get("effective_stack_bb") or 0),
            "context": {
                "vpip": bool(r.get("vpip")), "pfr": bool(r.get("pfr")),
                "three_bet_opp": bool(r.get("three_bet_opp")), "three_bet": bool(r.get("three_bet")),
                "faced_three_bet": bool(r.get("faced_three_bet")), "folded_to_three_bet": bool(r.get("folded_to_three_bet")),
                "cbet_opp": bool(r.get("cbet_opp")), "cbet": bool(r.get("cbet")),
                "timeout_count": int(r.get("timeout_count") or 0),
            },
        })
    return {"metric": metric, "range": range, "hands": out, "count": len(out)}
'''
        text = text.rstrip() + addon + "\n"
    path.write_text(text, encoding="utf-8")


def _app(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "v1.24.4 analysis focus and decision-first review"
    if marker in text:
        return
    pos = text.rfind("})();")
    if pos < 0:
        raise RuntimeError("v1.24.4 app closing marker missing")
    addon = r'''

  // v1.24.4 analysis focus and decision-first review.
  // Observed frequencies remain descriptive; this layer never presents a solver
  // verdict or fabricated EV loss.
  const JJ_V1244_FOCUS_KEY={
    'VPIP-PFR gap':'vpip_pfr_gap',
    'Fold to 3bet':'fold_to_3bet',
    '3bet':'three_bet',
    'Cbet':'cbet',
    'Position VPIP':'position_vpip',
    'Timeout':'timeout',
  };
  const jjV1244FocusMeta=s=>({
    key:JJ_V1244_FOCUS_KEY[String(s?.metric||'')]||'',
    label:String(s?.metric||'Sample'),
    severity:String(s?.severity||'info'),
    title:String(s?.title||''),
    detail:String(s?.detail||''),
  });
  const jjV1244StreetLabel=s=>({preflop:'PREFLOP',flop:'FLOP',turn:'TURN',river:'RIVER'})[String(s||'').toLowerCase()]||String(s||'').toUpperCase();

  function jjV1244EnsureFocusUI(){
    const view=$('#analysisView');if(!view)return null;
    let section=$('#jjV1244AnalysisFocus');
    if(section)return section;
    section=document.createElement('section');
    section.id='jjV1244AnalysisFocus';
    section.className='jj-v1244-analysis-focus';
    const kpis=$('#jjAnalysisKpis');
    if(kpis)kpis.insertAdjacentElement('beforebegin',section);else view.prepend(section);
    return section;
  }

  function jjV1244RenderFocus(data){
    const box=jjV1244EnsureFocusUI();if(!box)return;
    const signals=(data?.signals||[]).filter(x=>String(x.severity||'')!=='ok').slice(0,3);
    if(!signals.length){
      box.innerHTML=`<div class="jj-v1244-focus-head"><div><span>START HERE</span><h3>今見るべきポイント</h3><p>十分なサンプルで強い偏りが見つかると、ここに最大3件だけ表示します。</p></div></div><div class="jj-v1244-focus-empty"><b>大きな頻度偏りはまだありません</b><span>下の統計は確認できますが、少ないサンプルから結論は出しません。</span></div>`;
      return;
    }
    box.innerHTML=`<div class="jj-v1244-focus-head"><div><span>START HERE</span><h3>今見るべきポイント</h3><p>検出された傾向を最大3件に絞っています。タップすると、その指標を構成した最近のハンドを確認できます。</p></div><small>solver判定ではありません</small></div><div class="jj-v1244-focus-grid">${signals.map((raw,i)=>{const s=jjV1244FocusMeta(raw);return `<article class="jj-v1244-focus-card is-${safe(s.severity)}"><div class="jj-v1244-focus-no">0${i+1}</div><div><span>${safe(s.label)}</span><h4>${safe(s.title)}</h4><p>${safe(s.detail)}</p></div>${s.key?`<button type="button" data-jj-v1244-focus="${safe(s.key)}" data-jj-v1244-label="${safe(s.title)}">関連ハンドを見る →</button>`:'<small>サンプルが増えると関連ハンドを表示します</small>'}</article>`}).join('')}</div><div id="jjV1244FocusHands" class="jj-v1244-focus-hands hidden"></div>`;
  }

  if(typeof jjRenderAnalysisSummary==='function'){
    const jjV1244BaseRenderAnalysisSummary=jjRenderAnalysisSummary;
    jjRenderAnalysisSummary=function(data){jjV1244BaseRenderAnalysisSummary(data);jjV1244RenderFocus(data)};
  }

  async function jjV1244LoadFocusHands(key,label){
    const box=$('#jjV1244FocusHands');if(!box)return;
    box.classList.remove('hidden');
    box.innerHTML=typeof jjV1243Skeleton==='function'?jjV1243Skeleton(3):'<div class="hint">読み込み中...</div>';
    try{
      const d=await api(`/analysis/focus-hands?metric=${encodeURIComponent(key)}&range=${encodeURIComponent(jjAnalysisState?.range||'all')}&limit=12`),hands=d.hands||[];
      box.innerHTML=`<div class="jj-v1244-focus-hands-head"><div><span>RELATED HANDS</span><h4>${safe(label||'関連ハンド')}</h4><p>この指標の母集団に含まれる最近のハンドです。結果の良し悪しではなく、意思決定を確認してください。</p></div><button type="button" class="text-btn" data-jj-v1244-close-focus>閉じる</button></div>${hands.length?`<div class="jj-v1244-focus-hand-grid">${hands.map(h=>`<button type="button" data-hand-open="${safe(h.hand_id)}"><div><b>${safe(h.position||'—')}</b><span>${safe(jjV1244StreetLabel(h.reached_street))}</span></div><strong class="${Number(h.net_bb)>=0?'positive':'negative'}">${safe(jjSigned(h.net_bb))}</strong><small>${safe(h.table_name||h.table_id||'')} · #${safe(String(h.hand_no||''))}</small><em>${safe(jjAnalysisDate(h.completed_at))}</em></button>`).join('')}</div>`:(typeof jjV1243State==='function'?jjV1243State('empty','該当ハンドがありません','現在の期間・サンプルでは関連ハンドを取得できませんでした。'):'<div class="empty">該当ハンドなし</div>')}`;
      box.scrollIntoView({behavior:'smooth',block:'nearest'});
    }catch(err){
      box.innerHTML=typeof jjV1243State==='function'?jjV1243State('error','関連ハンドを取得できませんでした',err?.message||'もう一度お試しください。'):`<div class="empty">${safe(err?.message||'取得失敗')}</div>`;
    }
  }

  document.addEventListener('click',e=>{
    const focus=e.target.closest('[data-jj-v1244-focus]');
    if(focus){e.preventDefault();jjV1244LoadFocusHands(focus.dataset.jjV1244Focus,focus.dataset.jjV1244Label);return}
    const close=e.target.closest('[data-jj-v1244-close-focus]');
    if(close){e.preventDefault();$('#jjV1244FocusHands')?.classList.add('hidden');return}
    const hand=e.target.closest('#jjV1244FocusHands [data-hand-open]');
    if(hand){e.preventDefault();jjOpenHand(hand.dataset.handOpen).catch(err=>toast(err.message))}
  });

  function jjV1244ActionLabel(a){return typeof jjV122ActionName!=='undefined'?(jjV122ActionName[String(a?.action||'')]||String(a?.action||'')):String(a?.action||'')}
  function jjV1244DecisionAmount(a){return typeof jjV122ActionAmount==='function'?jjV122ActionAmount(a):''}
  function jjV1244DecisionSummary(data){
    const players=data?.players||[],hero=players.find(p=>Number(p.user_id)===Number(me?.id))||players[0]||{},h=data?.hand||{},bb=Number(h.big_blind||0);
    const mine=(data?.actions||[]).filter(a=>Number(a.user_id)===Number(hero.user_id));
    if(!mine.length)return '<div class="jj-v1244-decision-empty">自分のアクション記録はありません。</div>';
    return `<div class="jj-v1244-decision-list">${mine.map((a,i)=>{const amount=jjV1244DecisionAmount(a),facing=Number(a.facing_chips||0)>0&&typeof jjV122Bb==='function'?jjV122Bb(a.facing_chips,bb):'',pot=typeof jjV122Bb==='function'?jjV122Bb(a.pot_before,bb):'';return `<article class="jj-v1244-decision ${a.timed_out?'is-timeout':''}"><div class="jj-v1244-decision-index">${String(i+1).padStart(2,'0')}</div><div class="jj-v1244-decision-street"><span>${safe(jjV1244StreetLabel(a.street))}</span><small>${pot?`Pot ${safe(pot)}`:''}</small></div><div class="jj-v1244-decision-action"><strong>${safe(jjV1244ActionLabel(a))}</strong>${amount?`<b>${safe(amount)}</b>`:''}</div><div class="jj-v1244-decision-context">${facing?`<span>Facing ${safe(facing)}</span>`:'<span>Facing —</span>'}${a.decision_seconds==null?'':`<small>${safe(String(Number(a.decision_seconds).toFixed(1).replace(/\.0$/,'')))}s</small>`}${a.timed_out?'<em>TIMEOUT</em>':''}</div></article>`}).join('')}</div>`;
  }

  async function jjV1244PolishReview(handId){
    const shell=$('.jj-v122-review');if(!shell)return;
    let data;
    try{data=await api(`/analysis/hands/${encodeURIComponent(handId)}`)}catch{return}
    if(!$('.jj-v1244-decision-panel')){
      const facts=$('.jj-v122-facts');
      const panel=document.createElement('section');panel.className='jj-v1244-decision-panel';
      panel.innerHTML=`<div class="jj-v1244-review-heading"><div><span>YOUR DECISIONS</span><h4>自分の意思決定</h4><p>最初に自分のアクションだけを確認します。Pot / Facing / サイズ / 時間を並べ、結果とは分けて振り返ります。</p></div><small>${(data.actions||[]).filter(a=>Number(a.user_id)===Number(me?.id)).length} decisions</small></div>${jjV1244DecisionSummary(data)}`;
      if(facts)facts.insertAdjacentElement('afterend',panel);else shell.prepend(panel);
    }
    const timeline=$('.jj-v122-timeline-panel');
    if(timeline&&!timeline.closest('.jj-v1244-full-flow')){
      const details=document.createElement('details');details.className='jj-v1244-full-flow';
      const summary=document.createElement('summary');summary.innerHTML='<span><b>全プレイヤーのアクションを見る</b><small>必要なときだけストリート全体を展開</small></span><em>詳細</em>';
      timeline.replaceWith(details);details.append(summary,timeline);
    }
    const note=$('.jj-v122-note-card');
    if(note){note.classList.add('jj-v1244-note-priority');const textarea=note.querySelector('textarea');if(textarea&&!textarea.placeholder.includes('判断'))textarea.placeholder='この判断で何を考えたか、次回どう確認するかを残す'}
  }

  if(typeof jjOpenHand==='function'){
    const jjV1244BaseOpenHand=jjOpenHand;
    jjOpenHand=async function(handId){const result=await jjV1244BaseOpenHand(handId);await jjV1244PolishReview(handId);return result};
  }
'''
    path.write_text(text[:pos] + addon + "\n" + text[pos:], encoding="utf-8")


def _styles(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "v1.24.4 analysis focus and decision-first review"
    if marker in text:
        return
    addon = r'''

/* v1.24.4 analysis focus and decision-first review */
.jj-v1244-analysis-focus{margin:0 0 14px}.jj-v1244-focus-head{display:flex;justify-content:space-between;gap:18px;align-items:end;margin-bottom:10px}.jj-v1244-focus-head>div>span,.jj-v1244-review-heading>div>span,.jj-v1244-focus-hands-head>div>span{font-size:.6rem;font-weight:900;letter-spacing:.12em;color:#63b993}.jj-v1244-focus-head h3,.jj-v1244-review-heading h4,.jj-v1244-focus-hands-head h4{margin:4px 0}.jj-v1244-focus-head p,.jj-v1244-review-heading p,.jj-v1244-focus-hands-head p{margin:0;max-width:760px;color:var(--muted);font-size:.72rem;line-height:1.55}.jj-v1244-focus-head>small{padding:5px 8px;border-radius:999px;background:rgba(255,255,255,.045);color:var(--muted);font-size:.6rem;white-space:nowrap}
.jj-v1244-focus-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.jj-v1244-focus-card{position:relative;display:flex;flex-direction:column;min-height:190px;padding:16px;border:1px solid var(--line);border-radius:16px;background:var(--panel);overflow:hidden}.jj-v1244-focus-card.is-watch{border-color:rgba(224,185,77,.35);background:linear-gradient(145deg,rgba(224,185,77,.07),var(--panel) 45%)}.jj-v1244-focus-card.is-info{border-color:rgba(87,155,203,.28)}.jj-v1244-focus-no{position:absolute;right:12px;top:8px;font-size:2rem;font-weight:950;line-height:1;color:rgba(255,255,255,.045)}.jj-v1244-focus-card>div:nth-child(2)>span{display:block;font-size:.6rem;font-weight:900;letter-spacing:.08em;color:#82c9a9}.jj-v1244-focus-card h4{margin:6px 0 7px;font-size:.93rem;line-height:1.35}.jj-v1244-focus-card p{margin:0 0 14px;color:var(--muted);font-size:.7rem;line-height:1.55}.jj-v1244-focus-card>button{margin-top:auto;width:100%;min-height:38px;border:1px solid rgba(99,185,147,.28);border-radius:10px;background:rgba(99,185,147,.08);color:inherit;font-weight:850;font-size:.68rem}.jj-v1244-focus-card>small{margin-top:auto;color:var(--muted);font-size:.63rem;line-height:1.4}.jj-v1244-focus-empty{display:flex;justify-content:space-between;gap:16px;padding:14px 16px;border:1px solid var(--line);border-radius:14px;background:rgba(255,255,255,.02)}.jj-v1244-focus-empty b{font-size:.8rem}.jj-v1244-focus-empty span{color:var(--muted);font-size:.68rem;text-align:right}
.jj-v1244-focus-hands{margin-top:10px;padding:14px;border:1px solid var(--line);border-radius:16px;background:rgba(255,255,255,.018)}.jj-v1244-focus-hands-head{display:flex;justify-content:space-between;align-items:start;gap:14px;margin-bottom:10px}.jj-v1244-focus-hand-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}.jj-v1244-focus-hand-grid>button{display:grid;grid-template-columns:minmax(0,1fr) auto;grid-template-areas:'top net' 'meta net' 'date date';gap:3px 8px;align-items:center;padding:10px;border:1px solid var(--line);border-radius:11px;background:var(--panel);color:inherit;text-align:left}.jj-v1244-focus-hand-grid>button:hover{border-color:rgba(99,185,147,.5)}.jj-v1244-focus-hand-grid>button>div{grid-area:top;display:flex;gap:6px;align-items:center}.jj-v1244-focus-hand-grid>button>div b{font-size:.72rem}.jj-v1244-focus-hand-grid>button>div span{font-size:.55rem;color:var(--muted)}.jj-v1244-focus-hand-grid>button>strong{grid-area:net;font-size:.86rem}.jj-v1244-focus-hand-grid>button>small{grid-area:meta;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted);font-size:.6rem}.jj-v1244-focus-hand-grid>button>em{grid-area:date;font-style:normal;color:var(--muted);font-size:.58rem}
.jj-v1244-decision-panel{margin:0 0 15px;padding:15px;border:1px solid rgba(42,132,95,.22);border-radius:16px;background:linear-gradient(145deg,rgba(42,132,95,.055),#fff 44%)}.jj-v1244-review-heading{display:flex;justify-content:space-between;gap:14px;align-items:end;margin-bottom:10px}.jj-v1244-review-heading>small{font-size:.62rem;color:var(--muted)}.jj-v1244-decision-list{display:grid;gap:6px}.jj-v1244-decision{display:grid;grid-template-columns:32px minmax(80px,.8fr) minmax(110px,1fr) minmax(120px,1fr);gap:8px;align-items:center;padding:9px 10px;border:1px solid #e7eeea;border-radius:11px;background:#fff}.jj-v1244-decision.is-timeout{border-color:#e3b7ad}.jj-v1244-decision-index{font-size:.58rem;font-weight:900;color:#a3b1aa}.jj-v1244-decision-street span{display:block;font-size:.6rem;font-weight:900;color:#257c58}.jj-v1244-decision-street small{font-size:.58rem;color:var(--muted)}.jj-v1244-decision-action{display:flex;gap:7px;align-items:baseline}.jj-v1244-decision-action strong{font-size:.78rem}.jj-v1244-decision-action b{font-size:.7rem;color:#8d6c17}.jj-v1244-decision-context{display:flex;justify-content:flex-end;gap:7px;align-items:center;font-size:.62rem;color:var(--muted)}.jj-v1244-decision-context em{padding:2px 5px;border-radius:5px;background:#f6ddd7;color:#a23e2f;font-style:normal;font-weight:900;font-size:.52rem}.jj-v1244-decision-empty{padding:12px;color:var(--muted);font-size:.72rem}
.jj-v1244-full-flow{margin:0;border:1px solid var(--line);border-radius:16px;background:#fff;overflow:hidden}.jj-v1244-full-flow>summary{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:13px 15px;cursor:pointer;list-style:none}.jj-v1244-full-flow>summary::-webkit-details-marker{display:none}.jj-v1244-full-flow>summary span b,.jj-v1244-full-flow>summary span small{display:block}.jj-v1244-full-flow>summary span b{font-size:.78rem}.jj-v1244-full-flow>summary span small{margin-top:2px;color:var(--muted);font-size:.62rem}.jj-v1244-full-flow>summary em{font-style:normal;color:#257c58;font-size:.65rem;font-weight:900}.jj-v1244-full-flow[open]>summary{border-bottom:1px solid var(--line)}.jj-v1244-full-flow .jj-v122-timeline-panel{border:0!important;border-radius:0!important;margin:0!important}.jj-v1244-note-priority{box-shadow:0 0 0 1px rgba(42,132,95,.08)}
@media(max-width:900px){.jj-v1244-focus-grid,.jj-v1244-focus-hand-grid{grid-template-columns:1fr}.jj-v1244-focus-card{min-height:0}.jj-v1244-decision{grid-template-columns:28px minmax(70px,.7fr) minmax(100px,1fr);grid-template-areas:'idx street action' 'idx context context'}.jj-v1244-decision-index{grid-area:idx}.jj-v1244-decision-street{grid-area:street}.jj-v1244-decision-action{grid-area:action;justify-self:end}.jj-v1244-decision-context{grid-area:context;justify-content:flex-end}}
@media(max-width:640px){.jj-v1244-focus-head,.jj-v1244-review-heading,.jj-v1244-focus-hands-head{align-items:flex-start}.jj-v1244-focus-head>small{display:none}.jj-v1244-focus-empty{flex-direction:column}.jj-v1244-focus-empty span{text-align:left}.jj-v1244-focus-card>button{min-height:44px}.jj-v1244-decision-panel{padding:12px}.jj-v1244-decision{grid-template-columns:26px 1fr;grid-template-areas:'idx street' 'idx action' 'idx context';gap:3px 7px}.jj-v1244-decision-action,.jj-v1244-decision-context{justify-self:start;justify-content:flex-start}.jj-v1244-full-flow>summary{min-height:54px}}
'''
    path.write_text(text.rstrip() + addon + "\n", encoding="utf-8")


def _index(path: Path) -> None:
    text = path.read_text(encoding="utf-8").replace("?v=55", "?v=56")
    path.write_text(text, encoding="utf-8")


def _sw(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"jj-arena-live-v55(?:-[A-Za-z0-9_-]+)?", "jj-arena-live-v56", text)
    path.write_text(text, encoding="utf-8")
