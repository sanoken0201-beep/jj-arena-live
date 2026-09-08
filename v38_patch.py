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
    text = text.replace('version="1.18.5"', 'version="1.18.6"')
    text = text.replace('"version":"1.18.5"', '"version":"1.18.6"')
    text = text.replace('request.url.query == "v=37"', 'request.url.query == "v=38"')
    if "v1.18.6 server-authoritative poker quiz rewards" in text:
        path.write_text(text, encoding="utf-8")
        return

    model_marker = "class ScheduleIn(BaseModel):"
    if model_marker not in text:
        raise RuntimeError("v1.18.6 ScheduleIn marker missing")
    model = r'''# v1.18.6 server-authoritative poker quiz rewards.
class QuizAnswerIn(BaseModel):
    question_id: str = Field(min_length=3, max_length=80)
    answer: int = Field(ge=0, le=100)


'''
    text = text.replace(model_marker, model + model_marker, 1)

    endpoint_marker = '@app.get("/api/schedules")'
    if endpoint_marker not in text:
        raise RuntimeError("v1.18.6 schedules endpoint marker missing")
    endpoints = r'''# v1.18.6 server-authoritative poker quiz rewards.
# Every completed question awards exactly 10 official points. The question,
# answer key, completion state, and ledger write all live on the server so a
# browser refresh, double tap, or edited JavaScript cannot award twice.
JJ_QUIZ_REWARD = 10
JJ_QUIZ_POTS = (40, 60, 80, 100, 120, 150, 200)
JJ_QUIZ_BETS = (10, 20, 25, 30, 40, 50, 75)
JJ_QUIZ_OFFSETS = (-10, -7, -5, 5, 7, 10)


def _jj_quiz_schema() -> None:
    uid_type = "BIGINT" if getattr(db, "IS_POSTGRES", False) else "INTEGER"
    ddl = (
        "CREATE TABLE IF NOT EXISTS quiz_attempts("
        "id TEXT PRIMARY KEY,"
        f"user_id {uid_type} NOT NULL REFERENCES users(id),"
        "pot INTEGER NOT NULL,"
        "bet INTEGER NOT NULL,"
        "correct_answer INTEGER NOT NULL,"
        "choices_json TEXT NOT NULL,"
        "answer INTEGER,"
        "created_at TEXT NOT NULL,"
        "answered_at TEXT)"
    )
    with db.connect() as con:
        con.execute(ddl)
        con.execute("CREATE INDEX IF NOT EXISTS idx_quiz_attempts_user_created ON quiz_attempts(user_id,created_at)")


def _jj_quiz_choices(correct: int, seed: int) -> list[int]:
    choices = {int(correct)}
    offsets = list(JJ_QUIZ_OFFSETS)
    start = abs(int(seed)) % len(offsets)
    for i in range(len(offsets)):
        d = offsets[(start + i) % len(offsets)]
        choices.add(max(3, min(60, int(correct) + int(d))))
        if len(choices) >= 4:
            break
    fallback = 3
    while len(choices) < 4:
        if fallback != correct:
            choices.add(fallback)
        fallback += 1
    return sorted(choices)[:4]


def _jj_quiz_payload(row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "pot": int(row["pot"]),
        "bet": int(row["bet"]),
        "choices": [int(v) for v in json.loads(row["choices_json"])],
        "reward": JJ_QUIZ_REWARD,
    }


_jj_quiz_schema()


@app.get("/api/quiz/question")
def quiz_question(user=Depends(current_user)):
    with db.connect() as con:
        existing = con.execute(
            "SELECT id,pot,bet,choices_json FROM quiz_attempts "
            "WHERE user_id=? AND answer IS NULL ORDER BY created_at DESC LIMIT 1",
            (user["id"],),
        ).fetchone()
        if existing:
            return _jj_quiz_payload(existing)

        nonce = uuid.uuid4()
        selector = nonce.int
        pot = JJ_QUIZ_POTS[selector % len(JJ_QUIZ_POTS)]
        bet = JJ_QUIZ_BETS[(selector // len(JJ_QUIZ_POTS)) % len(JJ_QUIZ_BETS)]
        correct = round(bet / (pot + bet + bet) * 100)
        choices = _jj_quiz_choices(correct, selector)
        qid = "q-" + nonce.hex
        created = db.utcnow()
        con.execute(
            "INSERT INTO quiz_attempts(id,user_id,pot,bet,correct_answer,choices_json,answer,created_at,answered_at) "
            "VALUES (?,?,?,?,?,?,NULL,?,NULL)",
            (qid, user["id"], pot, bet, correct, json.dumps(choices, separators=(",", ":")), created),
        )
        row = con.execute(
            "SELECT id,pot,bet,choices_json FROM quiz_attempts WHERE id=? AND user_id=?",
            (qid, user["id"]),
        ).fetchone()
    return _jj_quiz_payload(row)


@app.post("/api/quiz/answer")
def quiz_answer(payload: QuizAnswerIn, user=Depends(current_user)):
    now = db.utcnow()
    with db.connect() as con:
        row = con.execute(
            "SELECT id,user_id,correct_answer,choices_json,answer FROM quiz_attempts "
            "WHERE id=? AND user_id=?",
            (payload.question_id, user["id"]),
        ).fetchone()
        if not row:
            raise HTTPException(404, "quiz question not found")

        choices = [int(v) for v in json.loads(row["choices_json"])]
        if int(payload.answer) not in choices:
            raise HTTPException(400, "answer is not one of the choices")

        if row["answer"] is not None:
            return {
                "ok": True,
                "already_answered": True,
                "correct": int(row["answer"]) == int(row["correct_answer"]),
                "correct_answer": int(row["correct_answer"]),
                "awarded": 0,
            }

        cur = con.execute(
            "UPDATE quiz_attempts SET answer=?,answered_at=? "
            "WHERE id=? AND user_id=? AND answer IS NULL",
            (int(payload.answer), now, payload.question_id, user["id"]),
        )
        if int(getattr(cur, "rowcount", 0) or 0) != 1:
            return {
                "ok": True,
                "already_answered": True,
                "correct": False,
                "correct_answer": int(row["correct_answer"]),
                "awarded": 0,
            }

        correct = int(payload.answer) == int(row["correct_answer"])
        txid = "quiz-" + str(payload.question_id)
        reason = "ポーカークイズ回答"
        con.execute(
            "INSERT INTO point_ledger(id,user_id,amount,kind,reason,effective_at,created_by,created_at,reversal_of) "
            "VALUES (?,?,?,?,?,?,?,?,NULL)",
            (txid, user["id"], JJ_QUIZ_REWARD, "quiz_reward", reason, now, user["id"], now),
        )

    return {
        "ok": True,
        "already_answered": False,
        "correct": correct,
        "correct_answer": int(row["correct_answer"]),
        "awarded": JJ_QUIZ_REWARD,
    }


'''
    text = text.replace(endpoint_marker, endpoints + endpoint_marker, 1)
    path.write_text(text, encoding="utf-8")


def _app(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "v1.18.6 poker quiz rewards and action reliability" in text:
        return
    marker = "})();"
    pos = text.rfind(marker)
    if pos < 0:
        raise RuntimeError("v1.18.6 app closing marker missing")
    addon = r'''

  // v1.18.6 poker quiz rewards and action reliability.
  // Quiz questions and award decisions now come from the server. Each completed
  // question earns 10 official points exactly once, even across reloads or taps.
  let jjV186QuizBusy=false;
  makeQuiz=function(){return null};

  async function jjV186LoadQuiz(){
    if(jjV186QuizBusy)return;
    jjV186QuizBusy=true;
    try{
      quiz.q=await api('/quiz/question');
      renderQuiz();
    }catch(err){
      $('#quizStage').innerHTML='<div class="empty">問題を読み込めませんでした</div>';
      $('#quizChoices').innerHTML='';
      toast(err.message);
    }finally{jjV186QuizBusy=false}
  }

  renderQuiz=function(){
    if(!quiz.q||!quiz.q.id){
      $('#quizStage').innerHTML='<div class="hint">問題を読み込み中…</div>';
      $('#quizChoices').innerHTML='';
      jjV186LoadQuiz();
      return;
    }
    const earned=Number(quiz.earned||0);
    $('#quizStage').innerHTML=`<div class="jj-quiz-reward">回答報酬 <b>+${Number(quiz.q.reward||10)}pt</b></div><div class="hint">Pot ${quiz.q.pot} に相手が ${quiz.q.bet} bet</div><div class="pot-num">Call <b>${quiz.q.bet}</b></div><p>コールに必要な最低勝率は？</p>`;
    $('#quizChoices').innerHTML=(quiz.q.choices||[]).map(x=>`<button data-quiz="${Number(x)}">${Number(x)}%</button>`).join('');
    $('#quizScore').textContent=`正解 ${quiz.score} / ${quiz.count} · 獲得 +${earned}pt`;
  };

  answerQuiz=async function(v){
    if(jjV186QuizBusy||!quiz.q?.id)return;
    jjV186QuizBusy=true;
    document.querySelectorAll('#quizChoices button').forEach(b=>b.disabled=true);
    const qid=quiz.q.id;
    try{
      const result=await post('/quiz/answer',{question_id:qid,answer:Number(v)});
      if(result.already_answered){
        toast('この問題のポイントはすでに反映済みです');
      }else{
        quiz.count++;
        if(result.correct)quiz.score++;
        quiz.earned=Number(quiz.earned||0)+Number(result.awarded||0);
        toast(result.correct?`正解 · +${Number(result.awarded||0)}pt`:`正解 ${Number(result.correct_answer)}% · +${Number(result.awarded||0)}pt`);
      }
      if(quiz.count>=10){
        $('#quizStage').innerHTML=`<div class="pot-num">${quiz.score}/10</div><p>${quiz.score>=8?'Good pace.':'もう一周すると速くなります。'}</p><div class="jj-quiz-reward">今回の獲得 <b>+${Number(quiz.earned||0)}pt</b></div>`;
        $('#quizChoices').innerHTML='';
        $('#quizScore').textContent=`正解 ${quiz.score} / 10 · 獲得 +${Number(quiz.earned||0)}pt`;
        quiz.q=null;
        return;
      }
      quiz.q=await api('/quiz/question');
      renderQuiz();
    }catch(err){
      toast(err.message);
      document.querySelectorAll('#quizChoices button').forEach(b=>b.disabled=false);
    }finally{jjV186QuizBusy=false}
  };

  // Preflop sizing labels are multipliers of the current price, not absolute BB.
  // Example: facing 3bb, "3x" now means 9bb rather than clamping an absolute 3bb.
  function jjV186PreflopBaseBb(){
    const hero=jjHero(),l=tableState?.legal||{},big=Number(tableState?.big_blind||100);
    return Math.max(1,(Number(hero?.round_bet||0)+Number(l.call_amount||0))/big);
  }
  function jjV186SizeText(v){return jjV185FmtBb(Number(v||0))}
  function jjV186EnhanceSizing(){
    if(!tableState?.legal?.can_act)return;
    const isPre=tableState.hand?.phase==='preflop';
    if(isPre){
      const base=jjV186PreflopBaseBb();
      document.querySelectorAll('#actionBar [data-raise-bb]').forEach(btn=>{
        const multiplier=Number(btn.dataset.multiplier||btn.dataset.raiseBb||0);
        if(!multiplier)return;
        const target=jjClampRaiseBb(base*multiplier);
        btn.dataset.multiplier=String(multiplier);
        btn.dataset.raiseBb=String(target);
        btn.innerHTML=`<span>${multiplier}x</span><small>${jjV186SizeText(target)}</small>`;
      });
    }else{
      document.querySelectorAll('#actionBar [data-pot-pct]').forEach(btn=>{
        const pct=Number(btn.dataset.potPct||0),target=jjPotPctBb(pct);
        const label=pct===100?'POT':`${pct}%`;
        btn.innerHTML=`<span>${label}</span><small>${jjV186SizeText(target)}</small>`;
      });
    }
    const allin=document.querySelector('#actionBar [data-allin-size]');
    if(allin){
      const target=jjRaiseBounds().max;
      allin.innerHTML=`<span>ALL-IN</span><small>${jjV186SizeText(target)}</small>`;
    }
    jjV185SyncRaiseUi();
  }

  function jjV186TickActionClock(){
    const el=$('#jjActionClock');if(!el)return;
    const deadline=tableState?.hand?.action_deadline;
    if(!deadline){el.textContent='';el.classList.remove('is-urgent');return}
    const sec=Math.max(0,Math.ceil((new Date(deadline)-new Date())/1000));
    el.textContent=`残り ${sec}秒`;
    el.classList.toggle('is-urgent',sec<=10);
  }

  let jjV186ActionPending=false;
  function jjV186ApplyPending(){
    const bar=$('#actionBar');if(!bar)return;
    bar.classList.toggle('jj-action-pending',jjV186ActionPending);
    bar.querySelectorAll('button,input').forEach(el=>{el.disabled=jjV186ActionPending});
  }

  const jjV186RenderActionBar=renderActionBar;
  renderActionBar=function(){
    jjV186RenderActionBar();
    if(tableState?.legal?.can_act){
      jjV186EnhanceSizing();
      const context=$('#actionBar .jj-action-context');
      if(context&&!$('#jjActionClock',context)){
        context.insertAdjacentHTML('beforeend','<div id="jjActionClock" class="jj-action-clock" aria-live="polite"></div>');
      }
      jjV186TickActionClock();
      $('#actionBar')?.setAttribute('aria-busy',jjV186ActionPending?'true':'false');
    }
    jjV186ApplyPending();
  };

  const jjV186DoAction=doAction;
  doAction=async function(action){
    if(jjV186ActionPending)return;
    jjV186ActionPending=true;
    jjV186ApplyPending();
    try{
      await jjV186DoAction(action);
    }finally{
      jjV186ActionPending=false;
      jjV186ApplyPending();
    }
  };

  window.setInterval(jjV186TickActionClock,500);
'''
    text = text[:pos] + addon + text[pos:]
    path.write_text(text, encoding="utf-8")


def _styles(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "v1.18.6 poker interaction reliability" in text:
        return
    text += r'''

/* v1.18.6 poker interaction reliability. */
.jj-quiz-reward{display:flex;align-items:center;justify-content:center;gap:7px;width:max-content;max-width:100%;margin:0 auto 12px;padding:6px 11px;border-radius:999px;background:rgba(39,118,84,.14);border:1px solid rgba(75,171,130,.32);font-size:.76rem;font-weight:800}
.jj-quiz-reward b{font-size:.86rem;color:var(--accent2)}
#quizChoices button:disabled{opacity:.58;cursor:wait}

#actionBar .jj-size-btn{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px}
#actionBar .jj-size-btn span{font-weight:900;line-height:1}
#actionBar .jj-size-btn small{font-size:.54rem;line-height:1;color:inherit;opacity:.72;font-variant-numeric:tabular-nums}
#actionBar .jj-action-clock{margin-left:auto;min-width:62px;padding:4px 7px;border-radius:999px;background:rgba(255,255,255,.06);color:#cbd7d2;font-size:.65rem;font-weight:900;text-align:center;font-variant-numeric:tabular-nums;white-space:nowrap}
#actionBar .jj-action-clock.is-urgent{background:rgba(181,66,66,.2);color:#ffd3d3;border:1px solid rgba(255,116,116,.34)}
#actionBar.jj-action-pending{pointer-events:none}
#actionBar.jj-action-pending .jj-action-btn,#actionBar.jj-action-pending .jj-size-btn,#actionBar.jj-action-pending input{opacity:.62}

@media(max-width:760px){
  body.jj-mobile-table-open #actionBar .jj-size-btn small{font-size:.5rem}
  body.jj-mobile-table-open #actionBar .jj-action-clock{font-size:.62rem;min-width:58px;padding:4px 6px}
}
'''
    path.write_text(text, encoding="utf-8")


def _index(path: Path) -> None:
    text = path.read_text(encoding="utf-8").replace("?v=37", "?v=38")
    path.write_text(text, encoding="utf-8")


def _sw(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"jj-arena-live-v\d+", "jj-arena-live-v38", text)
    path.write_text(text, encoding="utf-8")
