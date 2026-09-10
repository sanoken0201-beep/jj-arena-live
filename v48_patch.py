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
    text = text.replace('version="1.20.2"', 'version="1.20.3"')
    text = text.replace('"version":"1.20.2"', '"version":"1.20.3"')
    text = text.replace('request.url.query == "v=47-ja1"', 'request.url.query == "v=48"')
    path.write_text(text, encoding="utf-8")


def _app(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "v1.20.3 daily poker quiz v2"
    if marker in text:
        return
    pos = text.rfind("})();")
    if pos < 0:
        raise RuntimeError("v1.20.3 app closing marker missing")
    addon = r'''

  // v1.20.3 daily poker quiz v2.
  // The server owns the JST day, question set, answer key and reward ledger.
  // Client counters are display-only and cannot create extra rewards.
  quiz={count:0,score:0,q:null,earned:0,lastResult:null};

  function jjV203Progress(p){
    p=p||{};
    return {answered:Number(p.answered||0),correct:Number(p.correct||0),earned:Number(p.earned||0),total:Number(p.total||10),remaining:Number(p.remaining||0),max_daily_reward:Number(p.max_daily_reward||100)};
  }

  jjV186LoadQuiz=async function(){
    if(jjV186QuizBusy)return;
    jjV186QuizBusy=true;
    try{
      quiz.q=await api('/quiz/question');
      quiz.lastResult=null;
      renderQuiz();
    }catch(err){
      $('#quizStage').innerHTML='<div class="empty">問題を読み込めませんでした</div>';
      $('#quizChoices').innerHTML='';
      toast(err.message);
    }finally{jjV186QuizBusy=false}
  };

  renderQuiz=function(){
    const q=quiz.q||{};
    const p=jjV203Progress(q.progress);
    if(q.done){
      $('#quizStage').innerHTML=`<div class="jj-quiz-category">DAILY COMPLETE</div><div class="pot-num">${p.correct}/${p.total}</div><p>今日の10問は完了です。次の問題セットは日本時間0:00に更新されます。</p><div class="jj-quiz-reward">本日の獲得 <b>+${p.earned}pt</b> / 最大 ${p.max_daily_reward}pt</div>`;
      $('#quizChoices').innerHTML='';
      $('#quizScore').textContent=`今日 ${p.correct}正解 / ${p.answered}回答 · +${p.earned}pt`;
      return;
    }
    if(!q.id){
      $('#quizStage').innerHTML='<div class="hint">今日の問題を読み込み中…</div>';
      $('#quizChoices').innerHTML='';
      jjV186LoadQuiz();
      return;
    }
    if(quiz.lastResult){
      const r=quiz.lastResult,rp=jjV203Progress(r.progress),tone=r.correct?'jj-quiz-correct':'jj-quiz-wrong';
      $('#quizStage').innerHTML=`<div class="jj-quiz-category">${safe(q.category_label||'POKER')}</div><div class="${tone}"><b>${r.correct?'正解':'不正解'}</b> · 正解 ${safe(r.correct_label||r.correct_answer||'')}</div><p class="jj-quiz-explanation">${safe(r.explanation||'')}</p><div class="jj-quiz-reward">この問題の報酬 <b>+${Number(r.awarded||0)}pt</b></div>`;
      $('#quizChoices').innerHTML='<button class="primary" data-quiz-next>次の問題へ</button>';
      $('#quizScore').textContent=`今日 ${rp.correct}正解 / ${rp.answered}回答 · +${rp.earned}pt`;
      return;
    }
    $('#quizStage').innerHTML=`<div class="jj-quiz-category">${safe(q.category_label||'POKER')}</div><div class="hint">今日の問題 ${Number(q.slot||p.answered+1)} / ${p.total}</div><p class="jj-quiz-prompt">${safe(q.prompt||'')}</p><div class="jj-quiz-reward">回答報酬 <b>+${Number(q.reward||10)}pt</b> · 同じ問題は1回だけ</div>`;
    $('#quizChoices').innerHTML=(q.choices||[]).map(c=>`<button data-daily-answer="${safe(String(c.value))}">${safe(c.label)}</button>`).join('');
    $('#quizScore').textContent=`今日 ${p.correct}正解 / ${p.answered}回答 · +${p.earned}pt`;
  };

  answerQuiz=async function(v){
    if(jjV186QuizBusy||quiz.lastResult||!quiz.q?.id||quiz.q?.done)return;
    jjV186QuizBusy=true;
    document.querySelectorAll('#quizChoices button').forEach(b=>b.disabled=true);
    try{
      const result=await post('/quiz/answer',{question_id:quiz.q.id,answer:String(v)});
      quiz.lastResult=result;
      renderQuiz();
    }catch(err){
      toast(err.message);
      if(/日付が変わり|上限に達し/.test(err.message)){
        try{quiz.q=await api('/quiz/question');quiz.lastResult=null;renderQuiz()}catch(retry){toast(retry.message)}
      }
      document.querySelectorAll('#quizChoices button').forEach(b=>b.disabled=false);
    }finally{jjV186QuizBusy=false}
  };

  async function jjV203NextQuiz(){
    if(jjV186QuizBusy)return;
    jjV186QuizBusy=true;
    try{
      quiz.q=await api('/quiz/question');
      quiz.lastResult=null;
      renderQuiz();
    }catch(err){toast(err.message)}finally{jjV186QuizBusy=false}
  }

  document.addEventListener('click',e=>{
    const choice=e.target.closest('[data-daily-answer]');
    if(choice)answerQuiz(choice.dataset.dailyAnswer);
    const next=e.target.closest('[data-quiz-next]');
    if(next)jjV203NextQuiz();
  });
  function jjV203DayCheck(){
    const day=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
    if(quiz.q?.date && quiz.q.date!==day && !jjV186QuizBusy)jjV186LoadQuiz();
  }
  window.addEventListener('focus',jjV203DayCheck);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)jjV203DayCheck()});
  setInterval(jjV203DayCheck,15000);
'''
    path.write_text(text[:pos] + addon + "\n" + text[pos:], encoding="utf-8")


def _styles(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "/* v1.20.3 daily poker quiz v2 */"
    if marker in text:
        return
    addon = r'''

/* v1.20.3 daily poker quiz v2 */
.jj-quiz-category{display:inline-flex;align-items:center;min-height:28px;padding:4px 9px;border:1px solid var(--line);border-radius:999px;font-size:11px;font-weight:800;letter-spacing:.08em;margin-bottom:10px}
.jj-quiz-prompt{font-size:clamp(16px,2.3vw,20px);line-height:1.65;font-weight:700;margin:8px 0 14px}
.jj-quiz-explanation{line-height:1.7;margin:12px 0}
.jj-quiz-correct,.jj-quiz-wrong{font-size:18px;margin:8px 0 4px}
#quizChoices{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
#quizChoices button{min-height:52px;white-space:normal;line-height:1.35}
#quizChoices button.primary{grid-column:1/-1}
@media(max-width:640px){#quizChoices{grid-template-columns:1fr}.jj-quiz-prompt{font-size:16px}#quizChoices button.primary{grid-column:auto}}
'''
    path.write_text(text.rstrip() + addon + "\n", encoding="utf-8")


def _index(path: Path) -> None:
    text = path.read_text(encoding="utf-8").replace("?v=47-ja1", "?v=48")
    path.write_text(text, encoding="utf-8")


def _sw(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"jj-arena-live-v\d+(?:-ja1)?", "jj-arena-live-v48", text)
    path.write_text(text, encoding="utf-8")
