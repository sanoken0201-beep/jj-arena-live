from __future__ import annotations

import re
from pathlib import Path


def apply(root: Path) -> None:
    _engine(root / "poker_engine.py")
    _server(root / "server.py")
    _app(root / "static" / "app.js")
    _styles(root / "static" / "styles.css")
    _index(root / "static" / "index.html")
    _sw(root / "static" / "sw.js")


def _engine(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "v1.23.0 mobile poker second-pass engine UX"
    if marker in text:
        return

    addon = r'''

# v1.23.0 mobile poker second-pass engine UX.
# Keep the established poker rules and card-privacy layer, but fix three pieces
# of table pacing that are directly visible to players: no-flop-no-drop,
# staged forced all-in runouts, and a longer synchronized showdown hold.
JJ_V123_RUNOUT_STREET_DELAY = 1.15
JJ_V123_SHOWDOWN_REVEAL_DELAY = 1.35
JJ_V123_SHOWDOWN_HOLD_SECONDS = 7.5


def _jj_v123_no_decision(state: dict) -> bool:
    """True only when nobody has a meaningful betting decision left."""
    if state.get("status") != "playing" or len(_in_hand_players(state)) <= 1:
        return False
    actors = list(_can_act(state))
    if not actors:
        return True
    if len(actors) > 1:
        return False
    actor = actors[0]
    hand = state.get("hand") or {}
    current = int(hand.get("current_bet", 0) or 0)
    paid = int(actor.get("round_bet", 0) or 0)
    return paid >= current


def _jj_v123_queue_runout(state: dict, delay: float = JJ_V123_RUNOUT_STREET_DELAY) -> None:
    hand = state.get("hand") or {}
    if not hand:
        return
    hand["forced_runout"] = True
    hand["runout_due_at_epoch"] = time.time() + max(0.15, float(delay))
    hand["action_seat"] = None
    hand.pop("action_deadline", None)


def _jj_v123_prepare_runout(state: dict) -> None:
    hand = state.get("hand") or {}
    if not hand:
        return
    _consume_bets_into_pot(state)
    hand["current_bet"] = 0
    hand["min_raise"] = int(state.get("big_blind", 100) or 100)
    hand["raises_in_round"] = 0
    hand["acted"] = []
    for player in _occupied(state):
        player["round_bet"] = 0
    _jj_v123_queue_runout(state)


_jj_v123_base_award_uncontested = _award_uncontested


def _award_uncontested(state: dict) -> None:
    """Use No Flop, No Drop for pots that end before any community card."""
    hand = state.get("hand")
    alive = _in_hand_players(state)
    if not hand or len(alive) != 1:
        return _jj_v123_base_award_uncontested(state)
    if len(hand.get("board") or []) != 0:
        return _jj_v123_base_award_uncontested(state)

    winner = alive[0]
    pot = sum(int(player.get("contributed", 0) or 0) for player in _occupied(state))
    hand["rake"] = 0
    winner["stack"] = int(winner.get("stack", 0) or 0) + max(0, int(pot))
    for player in _occupied(state):
        player["contributed"] = 0
        player["round_bet"] = 0
    _finish_hand(state, winner.get("name") or "")


_jj_v123_base_advance_round = _advance_round


def _advance_round(state: dict) -> None:
    hand = state.get("hand") or {}
    if (
        state.get("status") == "playing"
        and len(hand.get("board") or []) < 5
        and _jj_v123_no_decision(state)
    ):
        _jj_v123_prepare_runout(state)
        return
    _jj_v123_base_advance_round(state)


_jj_v123_base_auto_progress = _auto_progress_if_needed


def _auto_progress_if_needed(state: dict) -> None:
    if state.get("status") != "playing":
        return
    alive = _in_hand_players(state)
    if len(alive) == 1:
        _award_uncontested(state)
        return
    actors = list(_can_act(state))
    if len(actors) <= 1:
        if _jj_v123_no_decision(state):
            hand = state.get("hand") or {}
            if not hand.get("forced_runout"):
                if len(hand.get("board") or []) < 5:
                    _jj_v123_prepare_runout(state)
                else:
                    _jj_v123_queue_runout(state, JJ_V123_SHOWDOWN_REVEAL_DELAY)
        # Never delegate the <=1-player branch to the legacy while-loop: that
        # loop is exactly what used to expose flop/turn/river in one frame.
        return
    _jj_v123_base_auto_progress(state)


def advance_forced_runout(state: dict) -> bool:
    """Advance exactly one visual runout stage when its server timer expires."""
    if state.get("status") != "playing":
        return False
    hand = state.get("hand") or {}
    if not hand.get("forced_runout"):
        return False
    due = float(hand.get("runout_due_at_epoch") or 0)
    if due > time.time():
        return False
    if len(_in_hand_players(state)) <= 1:
        hand.pop("forced_runout", None)
        hand.pop("runout_due_at_epoch", None)
        _award_uncontested(state)
        return True

    hand.pop("runout_due_at_epoch", None)
    if len(hand.get("board") or []) < 5:
        _deal_next_street(state)
        hand = state.get("hand") or hand
        hand["action_seat"] = None
        hand.pop("action_deadline", None)
        if len(hand.get("board") or []) < 5:
            _jj_v123_queue_runout(state, JJ_V123_RUNOUT_STREET_DELAY)
        else:
            _jj_v123_queue_runout(state, JJ_V123_SHOWDOWN_REVEAL_DELAY)
        return True

    hand.pop("forced_runout", None)
    hand.pop("runout_due_at_epoch", None)
    _showdown(state)
    return True


_jj_v123_base_finish_hand = _finish_hand


def _finish_hand(state: dict, winner_name: str) -> None:
    hand_before = state.get("hand") or {}
    had_showdown = bool(hand_before.get("showdown"))
    _jj_v123_base_finish_hand(state, winner_name)
    result = state.get("last_result") or {}
    is_showdown = had_showdown or result.get("type") == "showdown" or bool(result.get("showdown"))
    if is_showdown:
        hold_until = time.time() + JJ_V123_SHOWDOWN_HOLD_SECONDS
        state["showdown_hold_until_epoch"] = hold_until
        state["next_hand_at_epoch"] = max(float(state.get("next_hand_at_epoch") or 0), hold_until)


_jj_v123_base_start_hand = start_hand


def start_hand(state: dict, *args, **kwargs):
    hold = float(state.get("showdown_hold_until_epoch") or 0)
    if hold > time.time():
        return None
    state.pop("showdown_hold_until_epoch", None)
    return _jj_v123_base_start_hand(state, *args, **kwargs)


_jj_v123_base_legal_actions = legal_actions


def legal_actions(state: dict, user_id: int) -> dict:
    legal = dict(_jj_v123_base_legal_actions(state, user_id) or {})
    hand = state.get("hand") or {}
    reasons: dict[str, str] = {}
    status_reason = ""

    hero = next((p for p in _occupied(state) if int(p.get("user_id") or -1) == int(user_id)), None)
    actor = next((p for p in _occupied(state) if p.get("seat") == hand.get("action_seat")), None)
    if hand.get("forced_runout"):
        status_reason = "オールイン後のボードを順番に公開しています"
    elif float(state.get("showdown_hold_until_epoch") or 0) > time.time():
        status_reason = "ショーダウンのカードを確認する時間です"
    elif not hero:
        status_reason = "着席するとアクションできます"
    elif state.get("status") != "playing":
        status_reason = "次のハンドを待っています"
    elif hero.get("folded"):
        status_reason = "このハンドではフォールド済みです"
    elif hero.get("all_in"):
        status_reason = "オールイン済みです"
    elif not legal.get("can_act"):
        status_reason = f"{actor.get('name')}さんの番です" if actor else "他のプレイヤーのアクション待ちです"
    else:
        status_reason = "あなたの番です"

    if not legal.get("can_check"):
        reasons["check"] = "相手のベットに対応する必要があります"
    if not legal.get("can_call"):
        reasons["call"] = "コールする額はありません"
    if not legal.get("can_raise"):
        if legal.get("raise_locked_allin"):
            reasons["raise"] = "ショートオールインでは再レイズ権が開いていません"
        else:
            reasons["raise"] = "現在はベット／レイズできません"
    if not legal.get("can_all_in"):
        reasons["allin"] = "現在はオールインできません"
    if legal.get("can_check"):
        reasons["fold"] = "チェックで無料に続行できるため、誤操作防止で非表示にしています"

    legal["status_reason"] = status_reason
    legal["disabled_reasons"] = reasons
    legal["runout_active"] = bool(hand.get("forced_runout"))
    return legal
'''
    path.write_text(text + addon, encoding="utf-8")


def _server(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace('version="1.22.0"', 'version="1.23.0"')
    text = text.replace('"version":"1.22.0"', '"version":"1.23.0"')
    marker = "v1.23.0 staged forced-runout scheduler"
    if marker in text:
        path.write_text(text, encoding="utf-8")
        return

    addon = r'''

# v1.23.0 staged forced-runout scheduler.
# Reuse the existing lifecycle task instead of creating another lifespan hook.
# The legacy auto-deal loop continues untouched as a child task; this wrapper
# only advances due all-in runouts one street at a time and broadcasts each frame.
from poker_engine import advance_forced_runout

_jj_v123_base_auto_deal_loop = auto_deal_loop


async def auto_deal_loop():
    base_task = asyncio.create_task(_jj_v123_base_auto_deal_loop())
    try:
        while True:
            await asyncio.sleep(0.18)
            now = time.time()
            for table_id in FIXED_TABLE_IDS:
                try:
                    async with table_locks[table_id]:
                        state = load_table(table_id)
                        hand = state.get("hand") or {}
                        due = float(hand.get("runout_due_at_epoch") or 0)
                        if (
                            state.get("status") == "playing"
                            and hand.get("forced_runout")
                            and due
                            and due <= now
                            and advance_forced_runout(state)
                        ):
                            arm_action_deadline(state)
                            save_table(state)
                            await broadcast_table(table_id)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    # A transient table read/broadcast problem must not stop the
                    # normal auto-deal lifecycle for every other table.
                    continue
    finally:
        base_task.cancel()
        await asyncio.gather(base_task, return_exceptions=True)
'''

    # Module definitions are fully evaluated before FastAPI lifespan starts, so
    # the lifespan's global lookup resolves this final wrapper.
    pos = text.rfind("\nif __name__")
    if pos < 0:
        text += addon
    else:
        text = text[:pos] + addon + text[pos:]
    path.write_text(text, encoding="utf-8")


def _app(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "v1.23.0 mobile poker second-pass interaction UX"
    if marker in text:
        return
    pos = text.rfind("})();")
    if pos < 0:
        raise RuntimeError("v1.23 app closing marker missing")

    addon = r'''

  // v1.23.0 mobile poker second-pass interaction UX.
  // Mobile-first: four-colour suits, integer stack display, explicit action
  // state, sound/haptics, safer all-ins, and latency acknowledgement.
  const JJ_V123_SOUND_KEY='jj_poker_sound_v123';
  let jjV123SoundEnabled=localStorage.getItem(JJ_V123_SOUND_KEY)!=='0';
  let jjV123Audio=null;
  let jjV123WasHeroTurn=false;
  let jjV123LastRunoutStage='';
  let jjV123ClockWarnedFor='';
  let jjV123AllinConfirmUntil=0;

  function jjV123SuitName(s){return({s:'spade',h:'heart',d:'diamond',c:'club'})[s]||'unknown'}
  cardHTML=function(c){
    if(!c||c==='??')return '<span class="card-face back" aria-label="伏せ札">JJ</span>';
    const rank=c[0]==='T'?'10':c[0],suit=c[1],glyph=suitChar(suit),name=jjV123SuitName(suit);
    return `<span class="card-face jj-four-suit suit-${name}" aria-label="${safe(rank)} ${safe(name)}"><b class="jj-card-rank">${safe(rank)}</b><span class="jj-card-suit">${glyph}</span></span>`;
  };

  function jjV123StackBb(chips){
    const big=Math.max(1,Number(tableState?.big_blind||100));
    return `${Math.max(0,Math.ceil(Number(chips||0)/big))}bb`;
  }

  const jjV123BaseRenderSeat=renderSeat;
  renderSeat=function(seat){
    let html=jjV123BaseRenderSeat(seat);
    const player=(tableState?.seats||[]).find(p=>Number(p.seat)===Number(seat));
    if(!player)return html;
    const stack=jjV123StackBb(player.stack);
    html=html.replace(/(<div class="stack"[^>]*>)[\s\S]*?(<\/div>)/,`$1${stack}$2`);
    html=html.replace(/(<div class="jj-seat-stack"[^>]*>)[\s\S]*?(<\/div>)/,`$1${stack}$2`);
    return html;
  };

  function jjV123Pending(){
    return (typeof jjV121ActionPending!=='undefined'&&!!jjV121ActionPending)||(typeof jjV186ActionPending!=='undefined'&&!!jjV186ActionPending);
  }

  function jjV123AudioContext(){
    if(!jjV123SoundEnabled)return null;
    try{
      if(!jjV123Audio)jjV123Audio=new (window.AudioContext||window.webkitAudioContext)();
      if(jjV123Audio.state==='suspended')jjV123Audio.resume().catch(()=>{});
      return jjV123Audio;
    }catch{return null}
  }

  function jjV123Tone(kind){
    if(!jjV123SoundEnabled)return;
    const ctx=jjV123AudioContext();if(!ctx)return;
    const cfg={turn:[660,0.08,0.00],urgent:[430,0.055,0.00],allin:[520,0.09,0.00],street:[760,0.045,0.00]}[kind]||[600,0.05,0];
    try{
      const osc=ctx.createOscillator(),gain=ctx.createGain();
      osc.type='sine';osc.frequency.value=cfg[0];gain.gain.setValueAtTime(0.0001,ctx.currentTime);gain.gain.exponentialRampToValueAtTime(0.055,ctx.currentTime+0.012);gain.gain.exponentialRampToValueAtTime(0.0001,ctx.currentTime+cfg[1]);osc.connect(gain);gain.connect(ctx.destination);osc.start();osc.stop(ctx.currentTime+cfg[1]+0.015);
      if(kind==='turn')setTimeout(()=>jjV123Tone('street'),105);
    }catch{}
  }

  function jjV123Haptic(pattern){
    try{if(navigator.vibrate)navigator.vibrate(pattern)}catch{}
  }

  function jjV123SoundButton(){
    const controls=$('#tableControls');if(!controls||$('#jjSoundToggle'))return;
    controls.insertAdjacentHTML('beforeend',`<button class="ghost jj-sound-toggle" id="jjSoundToggle" type="button" aria-pressed="${jjV123SoundEnabled?'true':'false'}">${jjV123SoundEnabled?'🔊 音':'🔇 音'}</button>`);
  }

  function jjV123StatusText(){
    const l=tableState?.legal||{};
    if(jjV123Pending())return '送信中… サーバーの確認を待っています';
    return l.status_reason||(!l.can_act?(tableState?.status==='playing'?'他のプレイヤーのアクション待ちです':'次のハンドを待っています'):'あなたの番です');
  }

  function jjV123ActionState(){
    const bar=$('#actionBar');if(!bar)return;
    const l=tableState?.legal||{};
    let status=$('#jjV123ActionStatus',bar);
    if(!status){
      bar.insertAdjacentHTML('afterbegin','<div id="jjV123ActionStatus" class="jj-v123-action-status" aria-live="polite"></div>');
      status=$('#jjV123ActionStatus',bar);
    }
    if(status){
      status.textContent=jjV123StatusText();
      status.classList.toggle('is-turn',!!l.can_act&&!jjV123Pending());
      status.classList.toggle('is-pending',jjV123Pending());
    }
    bar.classList.toggle('jj-v123-pending',jjV123Pending());
    if(jjV123Pending())bar.querySelectorAll('button,input').forEach(el=>el.disabled=true);

    const reasons=l.disabled_reasons||{};
    bar.querySelectorAll('[data-action]').forEach(btn=>{
      const action=btn.dataset.action;
      if(reasons[action])btn.title=reasons[action];
    });
    bar.querySelectorAll('button:disabled').forEach(btn=>{
      if(!btn.title)btn.title='現在この操作はできません';
    });
  }

  function jjV123TurnFeedback(){
    const l=tableState?.legal||{},isTurn=!!l.can_act&&!jjV123Pending();
    if(isTurn&&!jjV123WasHeroTurn){jjV123Tone('turn');jjV123Haptic([28,35,28])}
    jjV123WasHeroTurn=isTurn;

    const hand=tableState?.hand||{};
    const stage=hand.forced_runout?`${hand.id||''}:${(hand.board||[]).length}`:'';
    if(stage&&stage!==jjV123LastRunoutStage){
      if(jjV123LastRunoutStage)jjV123Tone('street');
      jjV123LastRunoutStage=stage;
    }else if(!stage){jjV123LastRunoutStage=''}
  }

  function jjV123ClockFeedback(){
    const deadline=tableState?.hand?.action_deadline,l=tableState?.legal||{};
    if(!deadline||!l.can_act){jjV123ClockWarnedFor='';return}
    const sec=Math.max(0,Math.ceil((new Date(deadline)-new Date())/1000));
    if(sec<=10&&sec>0&&jjV123ClockWarnedFor!==String(deadline)){
      jjV123ClockWarnedFor=String(deadline);jjV123Tone('urgent');jjV123Haptic(35);
    }
  }

  function jjV123DecorateCards(){
    document.querySelectorAll('#pokerRoom .card-face.jj-four-suit').forEach(card=>card.setAttribute('data-four-suit','1'));
  }

  const jjV123BaseRenderActionBar=renderActionBar;
  renderActionBar=function(){
    jjV123BaseRenderActionBar();
    jjV123ActionState();
  };

  const jjV123BaseRenderPokerRoom=renderPokerRoom;
  renderPokerRoom=function(){
    jjV123BaseRenderPokerRoom();
    jjV123DecorateCards();
    jjV123SoundButton();
    jjV123ActionState();
    jjV123TurnFeedback();
    jjV123ClockFeedback();
    document.body.classList.toggle('jj-v123-hero-turn',!!tableState?.legal?.can_act&&!jjV123Pending());
    document.body.classList.toggle('jj-v123-runout',!!tableState?.hand?.forced_runout);
  };

  // All-in is deliberately a two-tap action on touch devices. Choosing the
  // ALL-IN sizing preset is still only a sizing choice; committing the action
  // requires an explicit second confirmation on the action button.
  document.addEventListener('click',e=>{
    const sound=e.target.closest('#jjSoundToggle');
    if(sound){
      e.preventDefault();e.stopImmediatePropagation();
      jjV123SoundEnabled=!jjV123SoundEnabled;
      localStorage.setItem(JJ_V123_SOUND_KEY,jjV123SoundEnabled?'1':'0');
      sound.textContent=jjV123SoundEnabled?'🔊 音':'🔇 音';sound.setAttribute('aria-pressed',jjV123SoundEnabled?'true':'false');
      if(jjV123SoundEnabled)jjV123Tone('street');
      return;
    }

    const btn=e.target.closest('#actionBar [data-action]');
    if(!btn||jjV123Pending())return;
    const action=btn.dataset.action;
    const bounds=typeof jjRaiseBounds==='function'?jjRaiseBounds():{max:0};
    const selected=Number($('#raiseTo')?.value||0),atMax=Number(bounds.max||0)>0&&Math.abs(selected-Number(bounds.max||0))<0.011;
    const commitsAllin=action==='allin'||(action==='raise'&&atMax);
    if(!commitsAllin)return;

    const now=Date.now();
    if(jjV123AllinConfirmUntil<now){
      e.preventDefault();e.stopImmediatePropagation();
      jjV123AllinConfirmUntil=now+2600;
      btn.classList.add('jj-confirm-allin');
      btn.dataset.jjOldHtml=btn.innerHTML;
      btn.innerHTML='<small>CONFIRM</small><b>もう一度タップで確定</b>';
      jjV123Tone('allin');jjV123Haptic([35,35,35]);
      setTimeout(()=>{
        if(Date.now()>=jjV123AllinConfirmUntil&&btn.isConnected){
          if(btn.dataset.jjOldHtml)btn.innerHTML=btn.dataset.jjOldHtml;
          btn.classList.remove('jj-confirm-allin');delete btn.dataset.jjOldHtml;
        }
      },2700);
      return;
    }
    jjV123AllinConfirmUntil=0;
  },true);

  // Unlock WebAudio on the first intentional table interaction. Mobile Safari
  // and Chrome require a user gesture before sound can play.
  document.addEventListener('pointerdown',e=>{
    if(e.target.closest('#pokerRoom,#actionBar,#tableControls'))jjV123AudioContext();
  },{passive:true});

  window.setInterval(()=>{jjV123ClockFeedback();jjV123ActionState()},500);
'''
    path.write_text(text[:pos] + addon + text[pos:], encoding="utf-8")


def _styles(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "v1.23.0 mobile poker second-pass visual UX"
    if marker in text:
        return
    text += r'''

/* v1.23.0 mobile poker second-pass visual UX. */
.card-face.jj-four-suit{display:inline-flex!important;align-items:center!important;justify-content:center!important;gap:.06em!important;background:#fff!important;color:#111827!important;font-weight:950!important;text-shadow:none!important;overflow:hidden!important}
.card-face.jj-four-suit .jj-card-rank{font-size:1em!important;line-height:1!important;color:#111827!important}
.card-face.jj-four-suit .jj-card-suit{font-size:1.12em!important;line-height:1!important;font-family:Arial,"Noto Sans Symbols 2",sans-serif!important}
.card-face.jj-four-suit.suit-heart .jj-card-suit{color:#d52b35!important}
.card-face.jj-four-suit.suit-diamond .jj-card-suit{color:#1769d1!important}
.card-face.jj-four-suit.suit-club .jj-card-suit{color:#16834a!important}
.card-face.jj-four-suit.suit-spade .jj-card-suit{color:#111827!important}

#actionBar .jj-v123-action-status{display:flex;align-items:center;justify-content:center;min-height:30px;margin:0 0 7px;padding:5px 10px;border-radius:10px;background:rgba(255,255,255,.055);color:#cbd5d1;font-size:.72rem;font-weight:850;letter-spacing:.01em;text-align:center}
#actionBar .jj-v123-action-status.is-turn{background:rgba(241,196,82,.14);border:1px solid rgba(241,196,82,.38);color:#fff1bd}
#actionBar .jj-v123-action-status.is-pending{background:rgba(83,141,209,.14);border:1px solid rgba(104,168,238,.3);color:#d7ebff}
#actionBar.jj-v123-pending{cursor:progress}
#actionBar.jj-v123-pending .jj-action-btn,#actionBar.jj-v123-pending .jj-size-btn,#actionBar.jj-v123-pending input{opacity:.52!important;filter:saturate(.55)!important}
#actionBar .jj-confirm-allin{background:#6d244f!important;border-color:#ef90c8!important;box-shadow:0 0 0 2px rgba(239,144,200,.15)!important}
.jj-sound-toggle{white-space:nowrap!important}

@media(max-width:760px){
  /* Keep the decision dock inside the natural thumb zone and above iOS home indicator. */
  body.jj-mobile-table-open #actionBar{padding-bottom:max(10px,env(safe-area-inset-bottom))!important}
  body.jj-mobile-table-open #actionBar .jj-v123-action-status{min-height:34px!important;margin-bottom:6px!important;font-size:.68rem!important}
  body.jj-mobile-table-open #actionBar .jj-main-actions{position:relative!important;z-index:20!important}
  body.jj-mobile-table-open #actionBar .jj-action-btn{min-height:60px!important;height:60px!important}
  body.jj-mobile-table-open #actionBar .jj-action-btn b{font-size:.8rem!important}
  body.jj-mobile-table-open #actionBar .jj-size-btn{min-height:42px!important;height:42px!important}
  body.jj-mobile-table-open #actionBar .jj-raise-editor input[type=range],
  body.jj-mobile-table-open #actionBar .jj-raise-editor label,
  body.jj-mobile-table-open #actionBar .jj-raise-editor input[type=number]{min-height:44px!important;height:44px!important}

  /* Hole cards must always win the visual stacking contest against bet/blind chips. */
  body.jj-mobile-table-open #pokerRoom .hole,
  body.jj-mobile-table-open #pokerRoom .jj-hole,
  body.jj-mobile-table-open #pokerRoom .jj-hole-cards{position:relative!important;z-index:12!important}
  body.jj-mobile-table-open #pokerRoom .card-face{position:relative!important;z-index:13!important}
  body.jj-mobile-table-open #pokerRoom .jj-bet-marker{z-index:6!important;pointer-events:none!important;max-width:64px!important;white-space:nowrap!important}

  body.jj-mobile-table-open #pokerRoom .card-face.jj-four-suit{min-width:30px!important;min-height:42px!important;padding:2px 4px!important;border:1px solid rgba(17,24,39,.18)!important;box-shadow:0 2px 5px rgba(0,0,0,.28)!important}
  body.jj-mobile-table-open #pokerRoom .hole .card-face.jj-four-suit,
  body.jj-mobile-table-open #pokerRoom .jj-hole .card-face.jj-four-suit,
  body.jj-mobile-table-open #pokerRoom .jj-hole-cards .card-face.jj-four-suit{min-width:34px!important;min-height:48px!important;font-size:1.02rem!important}

  body.jj-v123-hero-turn.jj-mobile-table-open #pokerRoom .seat.active .seat-box,
  body.jj-v123-hero-turn.jj-mobile-table-open #pokerRoom .jj-seat.active .jj-seat-box{animation:jjV123TurnGlow 1.15s ease-in-out infinite alternate!important}
  body.jj-v123-runout.jj-mobile-table-open #boardCards{box-shadow:0 0 0 1px rgba(255,255,255,.08),0 0 22px rgba(93,179,230,.12)!important}
}

@media(max-width:430px) and (orientation:portrait){
  body.jj-mobile-table-open #actionBar .jj-main-actions{gap:6px!important}
  body.jj-mobile-table-open #actionBar .jj-action-btn{min-height:62px!important;height:62px!important;border-radius:13px!important}
  body.jj-mobile-table-open #actionBar .jj-size-row{grid-template-columns:repeat(4,minmax(0,1fr))!important}
  body.jj-mobile-table-open #actionBar .jj-allin-size{grid-column:auto!important}
  body.jj-mobile-table-open #tableControls .jj-sound-toggle{min-width:54px!important;padding-inline:7px!important}
}

@keyframes jjV123TurnGlow{from{box-shadow:0 0 0 2px rgba(255,216,102,.32),0 7px 18px rgba(0,0,0,.38)}to{box-shadow:0 0 0 3px rgba(255,216,102,.68),0 0 28px rgba(255,196,68,.23),0 7px 18px rgba(0,0,0,.38)}}
@media(prefers-reduced-motion:reduce){body.jj-v123-hero-turn #pokerRoom .seat.active .seat-box,body.jj-v123-hero-turn #pokerRoom .jj-seat.active .jj-seat-box{animation:none!important}}
'''
    path.write_text(text, encoding="utf-8")


def _index(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace("?v=50", "?v=51").replace("?v=48-hotfix1", "?v=51")
    path.write_text(text, encoding="utf-8")


def _sw(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"jj-arena-live-v(?:\d+)(?:-hotfix\d+)?", "jj-arena-live-v51", text)
    path.write_text(text, encoding="utf-8")
