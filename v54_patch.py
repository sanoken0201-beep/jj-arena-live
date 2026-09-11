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
    text = text.replace('version="1.24.2"', 'version="1.24.3"')
    text = text.replace('"version":"1.24.2"', '"version":"1.24.3"')
    text = text.replace('request.url.query == "v=54"', 'request.url.query == "v=55"')
    path.write_text(text, encoding="utf-8")


def _app(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "v1.24.3 focused non-poker product UX"
    if marker in text:
        return
    pos = text.rfind("})();")
    if pos < 0:
        raise RuntimeError("v1.24.3 app closing marker missing")

    addon = r'''

  // v1.24.3 focused non-poker product UX.
  // Scope is intentionally limited to Home / Daily Quiz / Ranking / shared UI
  // states so concurrent online-poker work can evolve independently.
  const jjV1243Num=v=>Number(v||0);
  const jjV1243Signed=(v,suffix='')=>{const n=jjV1243Num(v);return `${n>0?'+':''}${Number.isInteger(n)?n:n.toFixed(1)}${suffix}`};
  const jjV1243Pct=(n,d)=>Math.max(0,Math.min(100,d?Math.round(jjV1243Num(n)*100/jjV1243Num(d)):0));
  const jjV1243State=(kind,title,detail='',action='')=>`<div class="jj-v1243-state is-${safe(kind)}"><div class="jj-v1243-state-icon" aria-hidden="true">${kind==='error'?'!':kind==='empty'?'○':'···'}</div><div><strong>${safe(title)}</strong>${detail?`<p>${safe(detail)}</p>`:''}${action||''}</div></div>`;
  const jjV1243Skeleton=(count=4)=>`<div class="jj-v1243-skeleton-grid" aria-label="読み込み中">${Array.from({length:count},()=>'<div class="jj-v1243-skeleton"><i></i><b></b><span></span></div>').join('')}</div>`;

  function jjV1243MonthKey(){
    try{
      const parts=new Intl.DateTimeFormat('ja-JP-u-ca-gregory',{timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit'}).formatToParts(new Date());
      const year=parts.find(x=>x.type==='year')?.value,month=parts.find(x=>x.type==='month')?.value;
      return year&&month?`${year}-${month}`:'';
    }catch{return ''}
  }

  // Priority 1: Home is a daily decision surface, not a catalogue of features.
  if(typeof jjV121LoadHomeHub==='function'){
    jjV121LoadHomeHub=async function(){
      if(!me)return;
      jjV121EnsureHomeHub();
      const grid=$('#jjHomeHubGrid'),articleBox=$('#jjHomeArticles');
      if(!grid)return;
      grid.innerHTML=jjV1243Skeleton(5);
      try{
        const d=await api('/home/overview'),q=d.quiz||{},p=d.points||{},perf=d.performance||{},learn=d.learning||{},hands=d.recent_hands||[],articles=d.articles||[];
        const total=Math.max(1,jjV1243Num(q.total||10)),answered=Math.min(total,jjV1243Num(q.answered||0));
        const remaining=Math.max(0,q.remaining==null?total-answered:jjV1243Num(q.remaining));
        const earned=jjV1243Num(q.earned||0),maxReward=Math.max(1,jjV1243Num(q.max_daily_reward||100));
        let focus={eyebrow:'TODAY',title:'今日の学習を1つ確認',detail:'短い学習を1つ終えるところから始めましょう。',action:'lab',cta:'学習を開く'};
        if(remaining>0){
          focus={eyebrow:'TODAY · PRIORITY',title:`今日のクイズをあと${remaining}問`,detail:`${answered}/${total}問完了 · 本日 +${earned}pt。残り最大 +${Math.max(0,maxReward-earned)}pt。`,action:'lab',cta:'続きを解く'};
        }else if(learn?.title){
          focus={eyebrow:'TODAY · REVIEW',title:String(learn.title),detail:String(learn.fact||'最近のプレイ傾向から復習候補を確認できます。'),action:'analysis',cta:'傾向を見る'};
        }else if(hands.length){
          focus={eyebrow:'TODAY · REVIEW',title:'最近のハンドを1件振り返る',detail:'直近の意思決定を短時間で確認して、次のプレイに繋げましょう。',action:'analysis',cta:'ハンドを見る'};
        }
        const quizPct=jjV1243Pct(answered,total),rewardPct=jjV1243Pct(earned,maxReward);
        const net=jjV1243Num(perf.net_bb_30d||0),bb100=perf.bb_per_100==null?null:jjV1243Num(perf.bb_per_100);
        grid.innerHTML=`
          <article class="card jj-v1243-focus">
            <div class="jj-v1243-focus-copy"><span>${safe(focus.eyebrow)}</span><h3>${safe(focus.title)}</h3><p>${safe(focus.detail)}</p></div>
            <div class="jj-v1243-focus-side"><button class="primary" data-jj-go="${safe(focus.action)}">${safe(focus.cta)} →</button><small>最初にやることを1つだけ表示しています</small></div>
          </article>
          <article class="card jj-v1243-metric"><span>今日のクイズ</span><div><strong>${answered}<small>/${total}</small></strong><em>+${earned}pt</em></div><div class="jj-v1243-meter"><i style="width:${quizPct}%"></i></div><small>${remaining?`残り${remaining}問`:'本日完了'} · 報酬 ${rewardPct}%</small><button class="soft" data-jj-go="lab">${remaining?'クイズへ':'結果を見る'}</button></article>
          <article class="card jj-v1243-metric"><span>後期ポイント</span><div><strong>${fmt(p.season_total||0)}<small>pt</small></strong><em>${p.rank?`#${fmt(p.rank)}`:'—'}</em></div><small>${p.rank?'現在のシーズン順位':'ランキング名の集計待ち'}</small><button class="soft" data-jj-go="ranking">ランキングを見る</button></article>
          <article class="card jj-v1243-metric"><span>直近30日</span><div><strong class="${net>=0?'positive':'negative'}">${safe(jjV1243Signed(net,'bb'))}</strong><em>${fmt(perf.hands_30d||0)} hands</em></div><small>${bb100==null?'bb/100はサンプル待ち':`${safe(jjV1243Signed(bb100,'bb'))}/100`}</small><button class="soft" data-jj-go="analysis">分析を見る</button></article>
          <article class="card jj-v1243-learning"><div><span>RECOMMENDED REVIEW</span><h4>${safe(learn.title||'ハンドレビューを継続')}</h4><p>${safe(learn.fact||'プレイデータが増えると、観測された傾向を表示します。')}</p></div><button class="soft" data-jj-go="analysis">根拠を見る →</button></article>
          <article class="card jj-v1243-hands"><div class="jj-v1243-card-head"><div><span>RECENT HANDS</span><h4>最近のハンド</h4></div><button class="text-btn" data-jj-go="analysis">すべて見る →</button></div>${hands.length?`<div class="jj-v1243-hand-list">${hands.map(h=>`<button data-jj-hand="${safe(h.hand_id)}"><b>${safe(h.position||'—')}</b><em class="${jjV1243Num(h.net_bb)>=0?'positive':'negative'}">${safe(jjV1243Signed(h.net_bb,'bb'))}</em><small>${safe(typeof jjAnalysisDate==='function'?jjAnalysisDate(h.completed_at):'')}</small></button>`).join('')}</div>`:jjV1243State('empty','まだハンド履歴がありません','オンラインハンドが記録されると、ここからすぐ振り返れます。') }</article>`;
        if(articleBox){
          articleBox.innerHTML=`<div class="section-head"><div><div class="eyebrow">LEARN</div><h3>今日のJJ</h3><p class="hint">日本語で読める学習コンテンツを厳選しています。</p></div><button class="text-btn" data-jj-go="lab">学習を開く →</button></div>${articles.length?`<div class="jj-home-article-grid">${articles.map(a=>`<a href="${safe(a.url)}" target="_blank" rel="noopener"><span>${safe(a.source||'')}</span><strong>${safe(a.title||'')}</strong><small>${safe(a.topic||'')}</small></a>`).join('')}</div>`:jjV1243State('empty','記事を準備しています','取得できる日本語コンテンツがない場合は、学習画面の保存済み教材を利用できます。', '<button class="soft" data-jj-go="lab">学習を開く</button>')}`;
        }
      }catch(err){
        grid.innerHTML=jjV1243State('error','ホームを更新できませんでした',err?.message||'通信状態を確認して、もう一度お試しください。','<button class="soft" data-jj-v1243-retry="home">再試行</button>');
      }
    };
  }

  // Priority 2: Daily Quiz always exposes progress, reward progress and a clear
  // result/next step. The server remains authoritative for answers and points.
  let jjV1243QuizAnswerValue=null;
  function jjV1243QuizHeader(p){
    p=jjV203Progress(p||{});
    const pct=jjV1243Pct(p.answered,p.total),rewardPct=jjV1243Pct(p.earned,p.max_daily_reward);
    return `<div class="jj-v1243-quiz-head"><div><span>DAILY QUIZ</span><strong>${p.answered}<small> / ${p.total}</small></strong></div><div class="jj-v1243-quiz-progress"><div><b>進捗</b><span>${pct}%</span></div><div class="jj-v1243-meter"><i style="width:${pct}%"></i></div><div class="jj-v1243-quiz-reward-row"><span>今日 +${fmt(p.earned)}pt</span><small>最大 ${fmt(p.max_daily_reward)}pt · ${rewardPct}%</small></div></div></div>`;
  }
  renderQuiz=function(){
    const q=quiz.q||{},p=jjV203Progress(q.progress||quiz.lastResult?.progress);
    const head=jjV1243QuizHeader(p);
    if(q.done){
      $('#quizStage').innerHTML=`${head}<div class="jj-v1243-quiz-complete"><span>DAILY COMPLETE</span><h3>今日の10問を完了しました</h3><strong>${fmt(p.correct)} / ${fmt(p.total)} 正解</strong><p>本日の獲得は <b>+${fmt(p.earned)}pt</b> です。次の問題セットは日本時間0:00に更新されます。</p></div>`;
      $('#quizChoices').innerHTML='';
      $('#quizScore').textContent=`${p.answered}/${p.total} · +${p.earned}pt`;
      return;
    }
    if(!q.id){
      $('#quizStage').innerHTML=`${head}${jjV1243State('loading','今日の問題を読み込んでいます','数秒経っても進まない場合は再試行してください。','<button class="soft" data-jj-v1243-retry="quiz">再試行</button>')}`;
      $('#quizChoices').innerHTML='';
      if(!jjV186QuizBusy)jjV186LoadQuiz();
      return;
    }
    if(quiz.lastResult){
      const r=quiz.lastResult,rp=jjV203Progress(r.progress),selected=(q.choices||[]).find(c=>String(c.value)===String(jjV1243QuizAnswerValue));
      const nextText=rp.remaining>0?'次の問題へ':'今日の結果を見る';
      $('#quizStage').innerHTML=`${jjV1243QuizHeader(rp)}<div class="jj-v1243-quiz-result ${r.correct?'is-correct':'is-wrong'}"><span>${r.correct?'CORRECT':'REVIEW'}</span><h3>${r.correct?'正解です':'ここを復習しましょう'}</h3><div class="jj-v1243-answer-compare">${selected?`<div><span>あなたの回答</span><b>${safe(selected.label)}</b></div>`:''}<div><span>正解</span><b>${safe(r.correct_label||r.correct_answer||'')}</b></div></div><p class="jj-quiz-explanation">${safe(r.explanation||'')}</p><div class="jj-v1243-quiz-earned">この問題 <b>+${fmt(r.awarded||0)}pt</b> · 今日合計 <b>+${fmt(rp.earned)}pt</b></div></div>`;
      $('#quizChoices').innerHTML=`<button class="primary" data-quiz-next>${safe(nextText)} →</button>`;
      $('#quizScore').textContent=`${rp.answered}/${rp.total} · ${rp.correct}正解 · +${rp.earned}pt`;
      return;
    }
    $('#quizStage').innerHTML=`${head}<div class="jj-v1243-question-meta"><span>${safe(q.category_label||'POKER')}</span><b>問題 ${Number(q.slot||p.answered+1)} / ${p.total}</b></div><p class="jj-quiz-prompt">${safe(q.prompt||'')}</p>${Array.isArray(q.glossary)&&q.glossary.length?`<div class="jj-v1243-glossary">${q.glossary.map(x=>`<span>${safe(typeof x==='string'?x:(x.term||''))}${typeof x==='object'&&x?.meaning?`：${safe(x.meaning)}`:''}</span>`).join('')}</div>`:''}<div class="jj-v1243-quiz-footnote">回答すると <b>+${Number(q.reward||10)}pt</b> · 同じ問題への加点は1回だけ</div>`;
    $('#quizChoices').innerHTML=(q.choices||[]).map((c,i)=>`<button data-daily-answer="${safe(String(c.value))}"><span>${String.fromCharCode(65+i)}</span><b>${safe(c.label)}</b></button>`).join('');
    $('#quizScore').textContent=`${p.answered}/${p.total} · +${p.earned}pt`;
  };
  answerQuiz=async function(v){
    if(jjV186QuizBusy||quiz.lastResult||!quiz.q?.id||quiz.q?.done)return;
    jjV186QuizBusy=true;jjV1243QuizAnswerValue=String(v);
    document.querySelectorAll('#quizChoices button').forEach(b=>{b.disabled=true;b.classList.toggle('is-selected',String(b.dataset.dailyAnswer)===String(v))});
    try{
      const result=await post('/quiz/answer',{question_id:quiz.q.id,answer:String(v)});
      quiz.lastResult=result;renderQuiz();
    }catch(err){
      if(typeof toast==='function')toast(err.message);
      if(/日付が変わり|上限に達し/.test(err.message)){
        try{quiz.q=await api('/quiz/question');quiz.lastResult=null;jjV1243QuizAnswerValue=null;renderQuiz()}catch(retry){if(typeof toast==='function')toast(retry.message)}
      }else document.querySelectorAll('#quizChoices button').forEach(b=>b.disabled=false);
    }finally{jjV186QuizBusy=false}
  };
  if(typeof jjV203NextQuiz==='function'){
    const jjV1243BaseNextQuiz=jjV203NextQuiz;
    jjV203NextQuiz=async function(){jjV1243QuizAnswerValue=null;return jjV1243BaseNextQuiz()};
  }

  // Priority 3: Ranking summary adds context without replacing the existing
  // detailed ranking table. It uses the existing public season/month API.
  function jjV1243EnsureRanking(){
    const view=$('#rankingView');if(!view)return null;
    let box=$('#jjV1243RankingSummary');
    if(!box){box=document.createElement('section');box.id='jjV1243RankingSummary';box.className='jj-v1243-ranking-summary';view.prepend(box)}
    return box;
  }
  async function jjV1243LoadRanking(){
    const box=jjV1243EnsureRanking();if(!box||!me)return;
    box.innerHTML=jjV1243Skeleton(3);
    try{
      const month=jjV1243MonthKey();
      const [seasonRows,monthRows]=await Promise.all([api('/rankings?season=fall'),month?api(`/rankings?season=fall&month=${encodeURIComponent(month)}`):Promise.resolve([])]);
      const rows=Array.isArray(seasonRows)?seasonRows:[],monthly=Array.isArray(monthRows)?monthRows:[],name=String(me.ranking_name||me.name||'');
      const mine=rows.find(r=>String(r.name)===name),monthMine=monthly.find(r=>String(r.name)===name),leader=rows[0]||null;
      if(!mine){box.innerHTML=jjV1243State('empty','ランキングへの紐付けを確認中です','あなたの表示名に一致する後期ランキングがまだありません。ポイントが反映されるとここに表示されます。');return}
      const higher=mine.rank>1?rows.find(r=>Number(r.rank)===Number(mine.rank)-1):null;
      const gap=higher?Math.max(0,jjV1243Num(higher.points)-jjV1243Num(mine.points)):0;
      const components=[['サークル',mine.club_points],['オンライン',mine.online_points],['台帳・クイズ等',mine.admin_points]];
      const positiveTotal=Math.max(1,components.reduce((s,x)=>s+Math.max(0,jjV1243Num(x[1])),0));
      const top=rows.slice(0,5),maxTop=Math.max(1,...top.map(r=>Math.max(0,jjV1243Num(r.points))));
      box.innerHTML=`<div class="jj-v1243-ranking-head"><div><span>YOUR SEASON</span><h3>ランキングの現在地</h3><p>合計だけでなく、順位差とポイントの内訳を確認できます。</p></div><button class="soft" data-jj-v1243-retry="ranking">更新</button></div>
        <div class="jj-v1243-ranking-grid">
          <article class="card jj-v1243-rank-me"><span>後期シーズン</span><div><strong>#${fmt(mine.rank)}</strong><b>${fmt(mine.points)} pt</b></div><p>${mine.rank===1?'現在1位です':higher?`#${fmt(higher.rank)} ${safe(higher.name)} まであと ${fmt(gap)}pt`:'次の順位との差を集計中'}</p><div class="jj-v1243-rank-sub"><span>今月 <b>${monthMine?`#${fmt(monthMine.rank)} · ${fmt(monthMine.points)}pt`:'まだ記録なし'}</b></span><span>記録 <b>${fmt(mine.games||0)}</b></span></div></article>
          <article class="card jj-v1243-rank-breakdown"><span>ポイント内訳</span><div>${components.map(([label,value])=>{const n=jjV1243Num(value),w=Math.max(0,Math.min(100,Math.round(Math.max(0,n)*100/positiveTotal)));return `<div class="jj-v1243-break-row"><p><span>${safe(label)}</span><b class="${n<0?'negative':''}">${safe(jjV1243Signed(n,'pt'))}</b></p><div class="jj-v1243-meter"><i style="width:${w}%"></i></div></div>`}).join('')}</div></article>
          <article class="card jj-v1243-rank-top"><div class="jj-v1243-card-head"><div><span>TOP 5</span><h4>上位の現在地</h4></div>${leader?`<small>1位 ${safe(leader.name)}</small>`:''}</div><div>${top.map(r=>`<div class="jj-v1243-rank-row ${String(r.name)===name?'is-me':''}"><b>#${fmt(r.rank)}</b><span>${safe(r.name)}</span><div><i style="width:${Math.max(3,Math.round(Math.max(0,jjV1243Num(r.points))*100/maxTop))}%"></i></div><strong>${fmt(r.points)}pt</strong></div>`).join('')}</div></article>
        </div>`;
    }catch(err){box.innerHTML=jjV1243State('error','ランキングを更新できませんでした',err?.message||'通信状態を確認してください。','<button class="soft" data-jj-v1243-retry="ranking">再試行</button>')}
  }
  if(typeof refreshView==='function'){
    const jjV1243BaseRefreshView=refreshView;
    refreshView=async function(v){const result=await jjV1243BaseRefreshView(v);if(v==='ranking')await jjV1243LoadRanking();return result};
  }

  // Priority 4: common loading/empty/error states share one visual language.
  document.addEventListener('click',e=>{
    const retry=e.target.closest('[data-jj-v1243-retry]');
    if(!retry)return;
    const target=retry.dataset.jjV1243Retry;
    if(target==='home')jjV121LoadHomeHub?.();
    else if(target==='quiz')jjV186LoadQuiz?.();
    else if(target==='ranking')jjV1243LoadRanking();
  });
'''
    path.write_text(text[:pos] + addon + "\n" + text[pos:], encoding="utf-8")


def _styles(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "v1.24.3 focused non-poker product UX"
    if marker in text:
        return
    addon = r'''

/* v1.24.3 focused non-poker product UX */
.jj-v1243-state{display:flex;gap:12px;align-items:flex-start;padding:16px;border:1px solid var(--line);border-radius:14px;background:rgba(255,255,255,.025);color:inherit}
.jj-v1243-state-icon{display:grid;place-items:center;flex:0 0 30px;width:30px;height:30px;border-radius:50%;background:rgba(255,255,255,.08);font-weight:900}
.jj-v1243-state strong{display:block;font-size:.9rem}.jj-v1243-state p{margin:4px 0 10px;opacity:.72;line-height:1.5;font-size:.76rem}.jj-v1243-state.is-error{border-color:rgba(220,98,88,.38)}.jj-v1243-state.is-error .jj-v1243-state-icon{background:rgba(220,98,88,.15);color:#ffb9b2}
.jj-v1243-skeleton-grid{grid-column:1/-1;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.jj-v1243-skeleton{min-height:132px;padding:16px;border:1px solid var(--line);border-radius:16px;background:var(--panel);overflow:hidden}.jj-v1243-skeleton>*{display:block;border-radius:999px;background:linear-gradient(90deg,rgba(255,255,255,.04),rgba(255,255,255,.11),rgba(255,255,255,.04));background-size:220% 100%;animation:jjV1243Shimmer 1.2s linear infinite}.jj-v1243-skeleton i{width:34%;height:10px}.jj-v1243-skeleton b{width:62%;height:26px;margin-top:22px}.jj-v1243-skeleton span{width:82%;height:10px;margin-top:18px}@keyframes jjV1243Shimmer{to{background-position:-220% 0}}@media(prefers-reduced-motion:reduce){.jj-v1243-skeleton>*{animation:none}}
.jj-v1243-meter{height:6px;border-radius:999px;overflow:hidden;background:rgba(255,255,255,.08)}.jj-v1243-meter>i{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,#5fc69a,#e3c96f);transition:width .28s ease}

#jjHomeHubGrid .jj-v1243-focus{grid-column:1/-1;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:24px;align-items:center;padding:22px;border-color:rgba(224,193,96,.3);background:linear-gradient(120deg,rgba(224,193,96,.09),rgba(68,160,121,.08))}
.jj-v1243-focus-copy>span,.jj-v1243-learning span,.jj-v1243-card-head span,.jj-v1243-ranking-head span,.jj-v1243-rank-me>span,.jj-v1243-rank-breakdown>span{font-size:.62rem;letter-spacing:.11em;font-weight:900;color:#8fd8b6}.jj-v1243-focus h3{margin:6px 0 6px;font-size:clamp(1.15rem,2vw,1.55rem);line-height:1.25}.jj-v1243-focus p{margin:0;max-width:720px;opacity:.76;line-height:1.55}.jj-v1243-focus-side{display:flex;min-width:170px;flex-direction:column;gap:7px;align-items:stretch}.jj-v1243-focus-side small{text-align:center;font-size:.62rem;opacity:.55}
#jjHomeHubGrid .jj-v1243-metric{display:flex;flex-direction:column;gap:10px;padding:16px}.jj-v1243-metric>span{font-size:.68rem;opacity:.68}.jj-v1243-metric>div:first-of-type{display:flex;justify-content:space-between;align-items:end;gap:8px}.jj-v1243-metric strong{font-size:1.45rem;line-height:1}.jj-v1243-metric strong small{font-size:.62rem;opacity:.6}.jj-v1243-metric em{font-style:normal;font-size:.72rem;font-weight:800;color:#f0d982}.jj-v1243-metric>small{font-size:.68rem;line-height:1.35;opacity:.67;min-height:18px}.jj-v1243-metric>button{margin-top:auto}
#jjHomeHubGrid .jj-v1243-learning{grid-column:span 2;display:flex;justify-content:space-between;align-items:end;gap:20px;padding:17px}.jj-v1243-learning h4{margin:6px 0;font-size:1rem}.jj-v1243-learning p{margin:0;line-height:1.5;font-size:.75rem;opacity:.7;max-width:680px}.jj-v1243-learning button{flex:0 0 auto}
#jjHomeHubGrid .jj-v1243-hands{grid-column:span 2;padding:17px}.jj-v1243-card-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:9px}.jj-v1243-card-head h4{margin:4px 0 0}.jj-v1243-hand-list{display:grid}.jj-v1243-hand-list>button{display:grid;grid-template-columns:52px 72px 1fr;gap:8px;align-items:center;width:100%;padding:9px 0;border:0;border-bottom:1px solid var(--line);background:transparent;color:inherit;text-align:left}.jj-v1243-hand-list>button:last-child{border-bottom:0}.jj-v1243-hand-list em{font-style:normal;font-weight:900}.jj-v1243-hand-list small{text-align:right;opacity:.6}

.jj-v1243-quiz-head{display:grid;grid-template-columns:auto minmax(180px,1fr);gap:20px;align-items:center;margin-bottom:20px;padding:13px 15px;border:1px solid var(--line);border-radius:14px;background:rgba(255,255,255,.025)}.jj-v1243-quiz-head>div:first-child>span{display:block;font-size:.58rem;font-weight:900;letter-spacing:.12em;color:#8fd8b6}.jj-v1243-quiz-head>div:first-child>strong{display:block;margin-top:3px;font-size:1.25rem}.jj-v1243-quiz-head>div:first-child small{font-size:.65rem;opacity:.55}.jj-v1243-quiz-progress>div:first-child,.jj-v1243-quiz-reward-row{display:flex;justify-content:space-between;gap:12px;align-items:center;font-size:.65rem}.jj-v1243-quiz-progress .jj-v1243-meter{margin:6px 0}.jj-v1243-quiz-reward-row span{font-weight:800;color:#f0d982}.jj-v1243-quiz-reward-row small{opacity:.6}.jj-v1243-question-meta{display:flex;justify-content:space-between;gap:10px;align-items:center}.jj-v1243-question-meta span{display:inline-flex;padding:5px 9px;border-radius:999px;background:rgba(77,183,137,.13);color:#9be0c0;font-size:.63rem;font-weight:800}.jj-v1243-question-meta b{font-size:.68rem;opacity:.62}.jj-v1243-glossary{display:flex;flex-wrap:wrap;gap:6px;margin:-3px 0 12px}.jj-v1243-glossary span{padding:5px 8px;border-radius:8px;background:rgba(255,255,255,.045);font-size:.67rem;line-height:1.35}.jj-v1243-quiz-footnote{font-size:.68rem;opacity:.65}.jj-v1243-quiz-footnote b{color:#f0d982}
#quizChoices button[data-daily-answer]{display:flex;align-items:center;gap:10px;text-align:left;padding:11px 13px}#quizChoices button[data-daily-answer]>span{display:grid;place-items:center;flex:0 0 26px;width:26px;height:26px;border-radius:8px;background:rgba(255,255,255,.07);font-size:.64rem;font-weight:900}#quizChoices button[data-daily-answer]>b{font-size:.78rem;line-height:1.45}#quizChoices button.is-selected{outline:2px solid rgba(229,198,103,.7)}
.jj-v1243-quiz-result>span,.jj-v1243-quiz-complete>span{font-size:.62rem;font-weight:900;letter-spacing:.12em;color:#8fd8b6}.jj-v1243-quiz-result h3,.jj-v1243-quiz-complete h3{margin:6px 0 12px}.jj-v1243-quiz-result.is-wrong>span{color:#f3c879}.jj-v1243-answer-compare{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.jj-v1243-answer-compare>div{padding:10px;border:1px solid var(--line);border-radius:10px;background:rgba(255,255,255,.025)}.jj-v1243-answer-compare span{display:block;font-size:.6rem;opacity:.58;margin-bottom:4px}.jj-v1243-answer-compare b{font-size:.78rem;line-height:1.4}.jj-v1243-quiz-earned{padding-top:10px;border-top:1px solid var(--line);font-size:.72rem}.jj-v1243-quiz-earned b{color:#f0d982}.jj-v1243-quiz-complete{text-align:center;padding:18px 8px}.jj-v1243-quiz-complete>strong{display:block;font-size:2rem;color:#f0d982}.jj-v1243-quiz-complete p{line-height:1.6;opacity:.75}

.jj-v1243-ranking-summary{margin:0 0 18px}.jj-v1243-ranking-head{display:flex;justify-content:space-between;gap:16px;align-items:end;margin-bottom:10px}.jj-v1243-ranking-head h3{margin:4px 0}.jj-v1243-ranking-head p{margin:0;font-size:.72rem;opacity:.65}.jj-v1243-ranking-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.jj-v1243-ranking-grid>article{padding:17px}.jj-v1243-rank-me>div:first-of-type{display:flex;align-items:end;justify-content:space-between;gap:12px;margin:8px 0}.jj-v1243-rank-me>div:first-of-type strong{font-size:2rem;line-height:1;color:#f0d982}.jj-v1243-rank-me>div:first-of-type b{font-size:1.25rem}.jj-v1243-rank-me>p{margin:0 0 12px;font-size:.72rem;opacity:.72}.jj-v1243-rank-sub{display:flex;gap:16px;padding-top:10px;border-top:1px solid var(--line);font-size:.68rem}.jj-v1243-rank-sub span{opacity:.65}.jj-v1243-rank-sub b{opacity:1;color:var(--text)}.jj-v1243-rank-breakdown>div{display:grid;gap:10px;margin-top:10px}.jj-v1243-break-row p{display:flex;justify-content:space-between;gap:10px;margin:0 0 4px;font-size:.68rem}.jj-v1243-rank-top{grid-column:1/-1}.jj-v1243-rank-row{display:grid;grid-template-columns:38px minmax(90px,160px) minmax(80px,1fr) 72px;gap:9px;align-items:center;min-height:34px;border-bottom:1px solid var(--line);font-size:.7rem}.jj-v1243-rank-row:last-child{border-bottom:0}.jj-v1243-rank-row>div{height:5px;border-radius:999px;background:rgba(255,255,255,.07);overflow:hidden}.jj-v1243-rank-row>div i{display:block;height:100%;background:#68c89e;border-radius:inherit}.jj-v1243-rank-row>strong{text-align:right}.jj-v1243-rank-row.is-me{background:rgba(229,198,103,.055)}.jj-v1243-rank-row.is-me>b,.jj-v1243-rank-row.is-me>span{color:#f0d982}

@media(max-width:900px){.jj-v1243-skeleton-grid{grid-template-columns:repeat(2,minmax(0,1fr))}#jjHomeHubGrid .jj-v1243-metric{grid-column:span 2}#jjHomeHubGrid .jj-v1243-learning,#jjHomeHubGrid .jj-v1243-hands{grid-column:1/-1}}
@media(max-width:640px){
  .jj-v1243-skeleton-grid{grid-template-columns:1fr}.jj-v1243-skeleton{min-height:98px}
  #jjHomeHubGrid .jj-v1243-focus{grid-template-columns:1fr;gap:14px;padding:17px}.jj-v1243-focus-side{min-width:0}.jj-v1243-focus-side small{text-align:left}
  #jjHomeHubGrid .jj-v1243-metric{grid-column:1/-1;padding:14px}#jjHomeHubGrid .jj-v1243-learning{align-items:stretch;flex-direction:column}#jjHomeHubGrid .jj-v1243-learning button{width:100%}
  .jj-v1243-quiz-head{grid-template-columns:1fr;gap:9px;margin-bottom:14px}.jj-v1243-answer-compare{grid-template-columns:1fr}#quizChoices button[data-daily-answer]{min-height:58px}.jj-v1243-quiz-result h3{font-size:1.05rem}
  .jj-v1243-ranking-head{align-items:flex-start}.jj-v1243-ranking-grid{grid-template-columns:1fr}.jj-v1243-rank-top{grid-column:auto}.jj-v1243-rank-row{grid-template-columns:32px minmax(70px,1fr) 54px}.jj-v1243-rank-row>div{display:none}.jj-v1243-rank-row>strong{font-size:.66rem}.jj-v1243-rank-sub{justify-content:space-between}
}
'''
    path.write_text(text.rstrip() + addon + "\n", encoding="utf-8")


def _index(path: Path) -> None:
    text = path.read_text(encoding="utf-8").replace("?v=54", "?v=55")
    path.write_text(text, encoding="utf-8")


def _sw(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"jj-arena-live-v54(?:-[A-Za-z0-9_-]+)?", "jj-arena-live-v55", text)
    path.write_text(text, encoding="utf-8")
