from __future__ import annotations

"""Deterministic v2 asset transform for the 2026-09-12 player UX audit.

The committed ``materialized_v1244`` tree stays byte-for-byte immutable for the
v2 parity contract. Production already serves post-cutover asset adjustments
from ``app.py``; this module changes the *served source* at the authoritative
implementation sites instead of adding another browser-side function override.

Every transform is guarded by an exact source assertion. A materialized-core
change therefore fails CI instead of silently shipping only part of the audit.
"""

PLAYER_UX_MARKER = "v2 player-ux audit hardening 2026-09-12"


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"player UX transform drift at {label}: expected 1 source block, found {count}")
    return source.replace(old, new, 1)


def transform_app_js(source: str) -> str:
    if PLAYER_UX_MARKER in source:
        return source

    source = _replace_once(
        source,
        """  function jjV123AllinKey(action,selected){
    const hand=tableState?.hand||{};
    return `${hand.id||''}:${hand.action_seat??''}:${action}:${Number(selected||0).toFixed(2)}`;
  }
""",
        """  function jjV123AllinKey(action,selected){
    const hand=tableState?.hand||{};
    return `${currentTableId||''}:${hand.id||''}:${hand.action_seat??''}:${hand.action_deadline||''}:${action}:${Number(selected||0).toFixed(2)}`;
  }
""",
        "all-in confirmation identity",
    )

    source = _replace_once(
        source,
        """  function jjV123StackBb(chips){
    const big=Math.max(1,Number(tableState?.big_blind||100));
    return `${Math.max(0,Math.ceil(Number(chips||0)/big))}bb`;
  }
""",
        """  function jjV123StackBb(chips){
    const big=Math.max(1,Number(tableState?.big_blind||100));
    const value=Math.max(0,Number(chips||0)/big),rounded=Math.round(value*10)/10;
    return `${Number.isInteger(rounded)?String(rounded):rounded.toFixed(1)}bb`;
  }
""",
        "stack precision",
    )

    source = _replace_once(
        source,
        """  doAction=async function(action){
    if(!currentTableId||jjV121ActionPending)return;
    jjV121ActionPending=true;
    const body={action,action_id:jjV121ActionId()};
    if(action==='raise')body.amount=Math.round(Number($('#raiseTo')?.value||0)*Number(tableState.big_blind||100));
    try{
      try{await post(`/tables/${currentTableId}/action`,body)}
      catch(err){if(!(err instanceof TypeError))throw err;await new Promise(r=>setTimeout(r,450));await post(`/tables/${currentTableId}/action`,body)}
    }catch(err){toast(err.message)}finally{jjV121ActionPending=false}
  };
""",
        """  doAction=async function(action){
    if(!currentTableId||jjV121ActionPending)return;
    const body={action,action_id:jjV121ActionId()};
    if(action==='raise'){
      const raw=String($('#raiseTo')?.value??'').trim().replace(',','.');
      const value=raw===''?NaN:Number(raw),bounds=jjRaiseBounds();
      if(!Number.isFinite(value))return toast('ベット／レイズ額を入力してください');
      if(value<Number(bounds.min)-0.001||value>Number(bounds.max)+0.001){
        return toast(`ベット／レイズ額は ${jjV185FmtBb(bounds.min)}〜${jjV185FmtBb(bounds.max)} の範囲で入力してください`);
      }
      body.amount=Math.round(value*Number(tableState.big_blind||100));
    }
    jjV121ActionPending=true;
    try{
      try{await post(`/tables/${currentTableId}/action`,body)}
      catch(err){if(!(err instanceof TypeError))throw err;await new Promise(r=>setTimeout(r,450));await post(`/tables/${currentTableId}/action`,body)}
    }catch(err){toast(err.message)}finally{jjV121ActionPending=false}
  };
""",
        "raise validation",
    )

    source = _replace_once(
        source,
        """  function jjV185SyncRaiseUi(){
    const input=$('#raiseTo');
    if(!input)return;
    const value=Number(input.value||0), l=tableState?.legal||{};
    const verb=l.can_check?'ベット':'レイズ';
    const btn=$('#jjRaiseAction');
    if(btn){
      const small=btn.querySelector('small'),big=btn.querySelector('b');
      if(small)small.textContent=l.can_check?'BET':'RAISE';
      if(big)big.textContent=`${verb} ${jjV185FmtBb(value)}`;
    }
    const amount=$('#jjRaiseAmount');
    if(amount)amount.textContent=jjV185FmtBb(value);
    document.querySelectorAll('#actionBar .jj-size-btn').forEach(b=>{
      let target=null;
      if(b.dataset.raiseBb!=null)target=jjClampRaiseBb(Number(b.dataset.raiseBb));
      else if(b.dataset.potPct!=null)target=jjPotPctBb(Number(b.dataset.potPct));
      else if(b.hasAttribute('data-allin-size'))target=jjRaiseBounds().max;
      b.classList.toggle('is-selected',target!=null&&Math.abs(Number(target)-value)<0.011);
    });
  }

  const jjV185SetRaiseBb=jjSetRaiseBb;
  jjSetRaiseBb=function(v){
    jjV185SetRaiseBb(v);
    jjV185SyncRaiseUi();
  };
""",
        """  function jjV185SyncRaiseUi(){
    const input=$('#raiseTo');
    if(!input)return;
    const l=tableState?.legal||{},parsed=typeof jjV124ParseRaiseText==='function'?jjV124ParseRaiseText(input.value):Number(input.value),value=parsed==null?null:Number(parsed);
    const meta=typeof jjV124RaiseVerb==='function'?jjV124RaiseVerb(l):{en:l.can_check?'BET':'RAISE',ja:l.can_check?'ベット':'レイズ'};
    const btn=$('#jjRaiseAction');
    if(btn){
      const small=btn.querySelector('small'),big=btn.querySelector('b');
      const added=value==null?null:(typeof jjV124RaiseAdditionalBb==='function'?jjV124RaiseAdditionalBb(value):value);
      if(small)small.textContent=value==null?meta.en:`${meta.en} · +${jjV185FmtBb(added)}`;
      if(big)big.textContent=value==null?'金額を入力':`${meta.ja} 合計 ${jjV185FmtBb(value)}`;
    }
    const amount=$('#jjRaiseAmount');
    if(amount)amount.textContent=value==null?'—':jjV185FmtBb(value);
    document.querySelectorAll('#actionBar .jj-size-btn').forEach(b=>{
      let target=null;
      if(b.dataset.raiseBb!=null)target=jjClampRaiseBb(Number(b.dataset.raiseBb));
      else if(b.dataset.potPct!=null)target=jjPotPctBb(Number(b.dataset.potPct));
      else if(b.hasAttribute('data-allin-size'))target=jjRaiseBounds().max;
      b.classList.toggle('is-selected',value!=null&&target!=null&&Math.abs(Number(target)-value)<0.011);
    });
  }

  const jjV185SetRaiseBb=jjSetRaiseBb;
  jjSetRaiseBb=function(v){
    const value=jjClampRaiseBb(v);
    jjV185SetRaiseBb(value);
    if(typeof jjV124RememberRaise==='function')jjV124RememberRaise(value);
    jjV185SyncRaiseUi();
  };
""",
        "raise UI sync",
    )

    source = _replace_once(
        source,
        """  function jjV124Hero(){return tableState?.seats?.find(p=>Number(p.user_id)===Number(me?.id))||null}
  function jjV124PotChips(){return Number(typeof jjTotalPot==='function'?jjTotalPot():0)||0}
  function jjV124EffectiveChips(hero){
    if(!hero)return 0;
    const opponents=(tableState?.seats||[]).filter(p=>Number(p.user_id)!==Number(hero.user_id)&&p.in_hand&&!p.folded&&Number(p.stack||0)>=0);
    const oppMax=opponents.length?Math.max(...opponents.map(p=>Number(p.stack||0))):Number(hero.stack||0);
    return Math.min(Number(hero.stack||0),oppMax);
  }
""",
        """  function jjV124Hero(){return tableState?.seats?.find(p=>Number(p.user_id)===Number(me?.id))||null}
  function jjV124PotChips(){return Number(typeof jjTotalPot==='function'?jjTotalPot():0)||0}
  let jjV124RaiseDraft={key:'',text:'',value:null,notice:''};
  function jjV124DecisionKey(){
    const hand=tableState?.hand||{};
    return `${currentTableId||''}:${hand.id||''}:${hand.action_seat??''}:${hand.action_deadline||''}`;
  }
  function jjV124ParseRaiseText(text){
    const raw=String(text??'').trim().replace(',','.');
    if(raw==='')return null;
    const value=Number(raw);
    return Number.isFinite(value)?value:null;
  }
  function jjV124EnsureRaiseDraft(bounds=jjRaiseBounds()){
    const key=jjV124DecisionKey(),min=Number(bounds.min||0),max=Number(bounds.max||0);
    if(jjV124RaiseDraft.key!==key){
      jjV124RaiseDraft={key,text:jjV124FmtNumber(min,2),value:min,notice:''};
    }else if(jjV124RaiseDraft.value!=null){
      const clamped=Math.max(min,Math.min(max,Number(jjV124RaiseDraft.value)));
      if(Math.abs(clamped-Number(jjV124RaiseDraft.value))>0.001){
        jjV124RaiseDraft.value=clamped;jjV124RaiseDraft.text=jjV124FmtNumber(clamped,2);
        jjV124RaiseDraft.notice='利用可能額が変わったため、現在の上限／下限に合わせました';
      }
    }
    return jjV124RaiseDraft;
  }
  function jjV124RememberRaise(value){
    const bounds=jjRaiseBounds(),draft=jjV124EnsureRaiseDraft(bounds),clamped=Math.max(Number(bounds.min||0),Math.min(Number(bounds.max||0),Number(value)));
    draft.value=clamped;draft.text=jjV124FmtNumber(clamped,2);draft.notice='';
    return draft;
  }
  function jjV124RaiseAdditionalBb(totalBb,hero=jjV124Hero()){
    const big=Math.max(1,Number(tableState?.big_blind||100));
    return Math.max(0,Number(totalBb||0)-Number(hero?.round_bet||0)/big);
  }
  function jjV124RaiseVerb(l){
    const phase=String(tableState?.hand?.phase||''),currentBet=Number(tableState?.hand?.current_bet||0);
    const isBet=phase!=='preflop'&&currentBet<=0;
    return isBet?{en:'BET',ja:'ベット'}:{en:'RAISE',ja:'レイズ'};
  }
  function jjV124EffectiveChips(hero){
    if(!hero)return 0;
    const opponents=(tableState?.seats||[]).filter(p=>Number(p.user_id)!==Number(hero.user_id)&&p.in_hand&&!p.folded&&Number(p.stack||0)>=0);
    if(opponents.length!==1)return null;
    const call=Math.max(0,Number(tableState?.legal?.call_amount||0));
    return Math.min(Number(hero.stack||0),call+Number(opponents[0].stack||0));
  }
""",
        "decision draft and effective stack",
    )

    source = _replace_once(
        source,
        """  function jjV124SizingMarkup(hero,l){
    const bounds=jjRaiseBounds(),min=Number(bounds.min||0),max=Number(bounds.max||0);
    if(!l.can_raise||max<=0)return '';
    const pre=tableState?.hand?.phase==='preflop';
    const defs=pre?[['2.5x',2.5],['3x',3],['4x',4]]:[['33%',33],['50%',50],['75%',75],['POT',100]];
    const quick=defs.map(([label,value])=>{
      const target=jjV124PresetTarget(pre?'pre':'post',value,hero,l);
      return `<button type="button" class="jj-size-btn" ${pre?`data-raise-bb="${target}" data-multiplier="${value}"`:`data-pot-pct="${value}"`} aria-label="${safe(label)} サイズ">${safe(label)}</button>`;
    }).join('');
    const allin=l.can_all_in?'<button type="button" class="jj-size-btn jj-allin-size" data-allin-size aria-label="オールイン額を選択">ALL-IN</button>':'';
    return `<div class="jj-sizing jj-v124-sizing">
      <div class="jj-size-row" aria-label="ベットサイズ候補">${quick}${allin}</div>
      <div class="jj-raise-editor jj-v124-raise-editor">
        <input id="raiseSlider" aria-label="ベット・レイズ額スライダー" type="range" min="${min}" max="${max}" step="0.5" value="${min}">
        <div class="jj-v124-stepper" role="group" aria-label="ベット・レイズ額">
          <button type="button" data-jj-raise-step="-0.5" aria-label="0.5BB減らす">−</button>
          <label><input id="raiseTo" aria-label="ベット・レイズ額 BB" type="number" inputmode="decimal" min="${min}" max="${max}" step="0.5" value="${min}"><span>BB</span></label>
          <button type="button" data-jj-raise-step="0.5" aria-label="0.5BB増やす">＋</button>
        </div>
      </div>
    </div>`;
  }
""",
        """  function jjV124SizingMarkup(hero,l){
    const bounds=jjRaiseBounds(),min=Number(bounds.min||0),max=Number(bounds.max||0);
    if(!l.can_raise||max<=0)return '';
    const draft=jjV124EnsureRaiseDraft({min,max}),sliderValue=draft.value==null?min:Math.max(min,Math.min(max,Number(draft.value)));
    const pre=tableState?.hand?.phase==='preflop';
    const defs=pre?[['2.5x',2.5],['3x',3],['4x',4]]:[['33%',33],['50%',50],['75%',75],['POT',100]];
    const quick=defs.map(([label,value])=>{
      const target=jjV124PresetTarget(pre?'pre':'post',value,hero,l);
      return `<button type="button" class="jj-size-btn" ${pre?`data-raise-bb="${target}" data-multiplier="${value}"`:`data-pot-pct="${value}"`} aria-label="${safe(label)} サイズ">${safe(label)}</button>`;
    }).join('');
    const allin=l.can_all_in?'<button type="button" class="jj-size-btn jj-allin-size" data-allin-size aria-label="オールイン額を選択">ALL-IN</button>':'';
    return `<div class="jj-sizing jj-v124-sizing">
      <div class="jj-size-row" aria-label="ベットサイズ候補">${quick}${allin}</div>
      <div class="jj-raise-editor jj-v124-raise-editor">
        <input id="raiseSlider" aria-label="ベット・レイズ額スライダー" type="range" min="${min}" max="${max}" step="0.5" value="${sliderValue}">
        <div class="jj-v124-stepper" role="group" aria-label="ベット・レイズ額">
          <button type="button" data-jj-raise-step="-0.5" aria-label="0.5BB減らす">−</button>
          <label><input id="raiseTo" aria-label="ベット・レイズ額 BB" type="text" inputmode="decimal" autocomplete="off" value="${safe(draft.text)}" data-min="${min}" data-max="${max}"><span>BB</span></label>
          <button type="button" data-jj-raise-step="0.5" aria-label="0.5BB増やす">＋</button>
        </div>
      </div>
      <div id="jjV124SizingError" class="jj-v124-sizing-error" aria-live="polite">${safe(draft.notice||'')}</div>
    </div>`;
  }
""",
        "sizing draft markup",
    )

    source = _replace_once(
        source,
        """  function jjV124ActionButtons(l){
    const hero=jjV124Hero(),callChips=Number(l.call_amount||0),callText=jjV124RawBb(callChips,{maxDecimals:1}),callIsAllin=callChips>0&&callChips>=Number(hero?.stack||Infinity);
    const bounds=jjRaiseBounds(),raiseAmount=Number($('#raiseTo')?.value||bounds.min||0);
    const actions=[];
    if(!l.can_check)actions.push('<button class="jj-action-btn jj-fold" data-action="fold"><small>FOLD</small><b>フォールド</b></button>');
    if(l.can_check){
      actions.push('<button class="jj-action-btn jj-check" data-action="check"><small>CHECK</small><b>チェック</b></button>');
    }else if(l.can_call){
      actions.push(`<button class="jj-action-btn jj-call" data-action="call"><small>${callIsAllin?'ALL-IN CALL':'CALL'}</small><b>${callIsAllin?'オールインコール':'コール'} <span id="jjV124CallButtonAmount">${safe(callText)}</span></b></button>`);
    }
    if(l.can_raise){
      actions.push(`<button class="jj-action-btn jj-raise" id="jjRaiseAction" data-action="raise"><small>${l.can_check?'BET':'RAISE'}</small><b>${l.can_check?'ベット':'レイズ'} ${safe(jjV185FmtBb(raiseAmount))}</b></button>`);
    }else if(l.can_all_in&&!callIsAllin){
      actions.push('<button class="jj-action-btn jj-allin" data-action="allin"><small>ALL-IN</small><b>オールイン</b></button>');
    }
    return `<div class="jj-main-actions jj-actions-${actions.length}">${actions.join('')}</div>`;
  }
""",
        """  function jjV124ActionButtons(l){
    const hero=jjV124Hero(),callChips=Number(l.call_amount||0),callText=jjV124RawBb(callChips,{maxDecimals:1}),callIsAllin=callChips>0&&callChips>=Number(hero?.stack||Infinity);
    const bounds=jjRaiseBounds(),draft=jjV124EnsureRaiseDraft(bounds),raiseAmount=jjV124ParseRaiseText(draft.text),meta=jjV124RaiseVerb(l);
    const actions=[];
    if(!l.can_check)actions.push('<button class="jj-action-btn jj-fold" data-action="fold"><small>FOLD</small><b>フォールド</b></button>');
    if(l.can_check){
      actions.push('<button class="jj-action-btn jj-check" data-action="check"><small>CHECK</small><b>チェック</b></button>');
    }else if(l.can_call){
      actions.push(`<button class="jj-action-btn jj-call" data-action="call"><small>${callIsAllin?'ALL-IN CALL':'CALL'}</small><b>${callIsAllin?'オールインコール':'コール'} <span id="jjV124CallButtonAmount">${safe(callText)}</span></b></button>`);
    }
    if(l.can_raise){
      const added=raiseAmount==null?null:jjV124RaiseAdditionalBb(raiseAmount,hero);
      actions.push(`<button class="jj-action-btn jj-raise" id="jjRaiseAction" data-action="raise"><small>${safe(raiseAmount==null?meta.en:`${meta.en} · +${jjV185FmtBb(added)}`)}</small><b>${safe(raiseAmount==null?'金額を入力':`${meta.ja} 合計 ${jjV185FmtBb(raiseAmount)}`)}</b></button>`);
    }else if(l.can_all_in&&!callIsAllin){
      actions.push('<button class="jj-action-btn jj-allin" data-action="allin"><small>ALL-IN</small><b>オールイン</b></button>');
    }
    return `<div class="jj-main-actions jj-actions-${actions.length}">${actions.join('')}</div>`;
  }
""",
        "bet raise semantics",
    )

    source = _replace_once(
        source,
        """  function jjV124DecisionMeta(hero,l){
    const street=JJ_V124_STREET[tableState?.hand?.phase]||String(tableState?.hand?.phase||'').toUpperCase();
    const pot=jjV124RawBb(jjV124PotChips(),{maxDecimals:1});
    const call=Number(l.call_amount||0)>0?jjV124RawBb(l.call_amount,{maxDecimals:1}):'—';
    const stack=jjV124RawBb(hero?.stack||0,{ceil:true});
    const effective=jjV124RawBb(jjV124EffectiveChips(hero),{ceil:true});
    return `<div class="jj-v124-decision-meta" aria-label="アクション情報">
      <div><span>STREET</span><strong>${safe(street)}</strong></div>
      <div><span>POT</span><strong>${safe(pot)}</strong></div>
      <div><span>TO CALL</span><strong id="jjV124CallAmount">${safe(call)}</strong></div>
      <div><span>STACK</span><strong>${safe(stack)}</strong></div>
      <div><span>EFFECTIVE</span><strong>${safe(effective)}</strong></div>
      <div class="jj-v124-time"><span>TIME</span><strong id="jjActionClock" class="jj-action-clock" aria-live="polite"></strong></div>
    </div>`;
  }

  renderActionBar=function(){
    const bar=$('#actionBar');if(!bar)return;
    const l=tableState?.legal||{can_act:false},hero=jjV124Hero();
    if(!hero){bar.innerHTML='<span class="hint">着席するとアクションパネルが表示されます</span>';return}
    if(!l.can_act){
      const stateText=hero.sitting_out?'一時離席中':tableState?.status==='playing'?'他のプレイヤーのアクション待ち':'次のハンドを待機';
      bar.innerHTML=`<div class="jj-v124-waiting"><span>${safe(stateText)}</span><strong>${safe(jjV124RawBb(hero.stack,{ceil:true}))}</strong></div>`;
      return;
    }
    bar.innerHTML=`${jjV124DecisionMeta(hero,l)}${jjV124SizingMarkup(hero,l)}${jjV124ActionButtons(l)}`;
    if(typeof jjV185SyncRaiseUi==='function')jjV185SyncRaiseUi();
    if(typeof jjV123ActionState==='function')jjV123ActionState();
    if(typeof jjV123ClockFeedback==='function')jjV123ClockFeedback();
  };

  function jjV124SyncRaiseFrom(el){
    if(!el)return;
    const value=Number(el.value||0);
    if(typeof jjSetRaiseBb==='function')jjSetRaiseBb(value);
    if(typeof jjV185SyncRaiseUi==='function')jjV185SyncRaiseUi();
  }

  document.addEventListener('input',e=>{
    if(e.target?.id==='raiseSlider'||e.target?.id==='raiseTo')jjV124SyncRaiseFrom(e.target);
  });
""",
        """  function jjV124DecisionMeta(hero,l){
    const street=JJ_V124_STREET[tableState?.hand?.phase]||String(tableState?.hand?.phase||'').toUpperCase();
    const pot=jjV124RawBb(jjV124PotChips(),{maxDecimals:1});
    const call=Number(l.call_amount||0)>0?jjV124RawBb(l.call_amount,{maxDecimals:1}):'—';
    const stack=jjV124RawBb(hero?.stack||0,{maxDecimals:1});
    const effectiveChips=jjV124EffectiveChips(hero),effective=effectiveChips==null?'相手別':jjV124RawBb(effectiveChips,{maxDecimals:1});
    return `<div class="jj-v124-decision-meta" aria-label="アクション情報">
      <div><span>STREET</span><strong>${safe(street)}</strong></div>
      <div><span>POT</span><strong>${safe(pot)}</strong></div>
      <div><span>TO CALL</span><strong id="jjV124CallAmount">${safe(call)}</strong></div>
      <div><span>STACK</span><strong>${safe(stack)}</strong></div>
      <div title="ヘッズアップでは、現在のコール額を含めて今後追加で争える最大額。マルチウェイでは単一値にしません"><span>EFFECTIVE</span><strong>${safe(effective)}</strong></div>
      <div class="jj-v124-time"><span>TIME</span><strong id="jjActionClock" class="jj-action-clock" aria-live="polite"></strong></div>
    </div>`;
  }

  renderActionBar=function(){
    const bar=$('#actionBar');if(!bar)return;
    const l=tableState?.legal||{can_act:false},hero=jjV124Hero();
    const active=document.activeElement,focusDraft=active?.id==='raiseTo'?{key:jjV124DecisionKey(),start:active.selectionStart,end:active.selectionEnd}:null;
    if(!hero){bar.innerHTML='<span class="hint">着席するとアクションパネルが表示されます</span>';return}
    if(!l.can_act){
      const stateText=hero.sitting_out?'一時離席中':tableState?.status==='playing'?'他のプレイヤーのアクション待ち':'次のハンドを待機';
      bar.innerHTML=`<div class="jj-v124-waiting"><span>${safe(stateText)}</span><strong>${safe(jjV124RawBb(hero.stack,{maxDecimals:1}))}</strong></div>`;
      return;
    }
    bar.innerHTML=`${jjV124DecisionMeta(hero,l)}${jjV124SizingMarkup(hero,l)}${jjV124ActionButtons(l)}`;
    if(typeof jjV185SyncRaiseUi==='function')jjV185SyncRaiseUi();
    if(typeof jjV123ActionState==='function')jjV123ActionState();
    if(typeof jjV123ClockFeedback==='function')jjV123ClockFeedback();
    if(focusDraft&&focusDraft.key===jjV124DecisionKey())requestAnimationFrame(()=>{
      const next=$('#raiseTo');if(!next||jjV124DecisionKey()!==focusDraft.key)return;
      next.focus({preventScroll:true});
      try{next.setSelectionRange(focusDraft.start,focusDraft.end)}catch{}
    });
  };

  function jjV124SyncRaiseFrom(el){
    if(!el)return;
    const bounds=jjRaiseBounds(),draft=jjV124EnsureRaiseDraft(bounds),error=$('#jjV124SizingError');
    if(el.id==='raiseSlider'){
      const value=jjClampRaiseBb(Number(el.value));
      jjV124RememberRaise(value);
      const input=$('#raiseTo');if(input)input.value=jjV124RaiseDraft.text;
      if(error)error.textContent='';
      if(typeof jjV185SyncRaiseUi==='function')jjV185SyncRaiseUi();
      return;
    }
    draft.text=String(el.value??'');draft.notice='';
    const value=jjV124ParseRaiseText(draft.text),min=Number(bounds.min||0),max=Number(bounds.max||0);
    if(value==null){if(error)error.textContent=draft.text.trim()===''?'金額を入力してください':'数値を確認してください';if(typeof jjV185SyncRaiseUi==='function')jjV185SyncRaiseUi();return}
    if(value<min-0.001||value>max+0.001){if(error)error.textContent=`${jjV185FmtBb(min)}〜${jjV185FmtBb(max)} の範囲で入力してください`;if(typeof jjV185SyncRaiseUi==='function')jjV185SyncRaiseUi();return}
    draft.value=value;
    const slider=$('#raiseSlider');if(slider)slider.value=value;
    if(error)error.textContent='';
    if(typeof jjV185SyncRaiseUi==='function')jjV185SyncRaiseUi();
  }

  document.addEventListener('input',e=>{
    if(e.target?.id==='raiseSlider'||e.target?.id==='raiseTo')jjV124SyncRaiseFrom(e.target);
  });
""",
        "decision metadata and draft input",
    )

    source = _replace_once(
        source,
        """    const btn=e.target.closest('#actionBar [data-action]');
    if(!btn||jjV123Pending())return;
    const action=btn.dataset.action;
    const bounds=typeof jjRaiseBounds==='function'?jjRaiseBounds():{max:0};
    const selected=Number($('#raiseTo')?.value||0),atMax=Number(bounds.max||0)>0&&Math.abs(selected-Number(bounds.max||0))<0.011;
    const commitsAllin=action==='allin'||(action==='raise'&&atMax);
    if(!commitsAllin)return;

    const now=Date.now(),confirmKey=jjV123AllinKey(action,selected);
    if(jjV123AllinConfirmUntil<now||jjV123AllinConfirmKey!==confirmKey){
      e.preventDefault();e.stopImmediatePropagation();
      jjV123AllinConfirmUntil=now+2600;
      jjV123AllinConfirmKey=confirmKey;
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
    jjV123AllinConfirmUntil=0;jjV123AllinConfirmKey='';
""",
        """    const btn=e.target.closest('#actionBar [data-action]');
    if(!btn||jjV123Pending())return;
    const action=btn.dataset.action,hero=typeof jjV124Hero==='function'?jjV124Hero():null;
    const heroStack=Math.max(0,Number(hero?.stack||0)),big=Math.max(1,Number(tableState?.big_blind||100));
    const selected=typeof jjV124ParseRaiseText==='function'?jjV124ParseRaiseText($('#raiseTo')?.value):Number($('#raiseTo')?.value||0);
    const callChips=Math.max(0,Number(tableState?.legal?.call_amount||0));
    const raiseDelta=selected==null?0:Math.max(0,Number(selected)*big-Number(hero?.round_bet||0));
    const commitChips=action==='call'?Math.min(callChips,heroStack):action==='raise'?Math.min(raiseDelta,heroStack):action==='allin'?heroStack:0;
    const commitsAllin=heroStack>0&&commitChips>=heroStack-0.01;
    if(!commitsAllin)return;

    const commitBb=commitChips/big,now=Date.now(),confirmKey=jjV123AllinKey(action,commitBb);
    if(jjV123AllinConfirmUntil<now||jjV123AllinConfirmKey!==confirmKey){
      e.preventDefault();e.stopImmediatePropagation();
      jjV123AllinConfirmUntil=now+2600;
      jjV123AllinConfirmKey=confirmKey;
      btn.classList.add('jj-confirm-allin');
      btn.dataset.jjOldHtml=btn.innerHTML;
      btn.innerHTML=`<small>CONFIRM</small><b>追加 ${safe(jjV124FmtNumber(commitBb,1))}bb ／ 残り0bb</b>`;
      jjV123Tone('allin');jjV123Haptic([35,35,35]);
      setTimeout(()=>{
        if(Date.now()>=jjV123AllinConfirmUntil&&btn.isConnected){
          if(btn.dataset.jjOldHtml)btn.innerHTML=btn.dataset.jjOldHtml;
          btn.classList.remove('jj-confirm-allin');delete btn.dataset.jjOldHtml;
        }
      },2700);
      return;
    }
    jjV123AllinConfirmUntil=0;jjV123AllinConfirmKey='';
""",
        "all-in confirmation commitment",
    )

    source = _replace_once(
        source,
        """    if(!seated){
      const full=(tableState?.seats||[]).length>=Number(tableState?.max_seats||6);
      $('#tableControls').innerHTML=`<div class="jj-table-control-left"><b class="jj-control-title">観戦中</b><span class="hint">${full?'現在は満席です':'150bbで参加できます'}</span></div><div class="jj-table-control-right"><button class="primary jj-join-control" data-jj-join="${safe(currentTableId||'')}" ${full?'disabled':''}>${full?'満席':'着席する · 150bb'}</button></div>`;
      return;
    }
""",
        """    if(!seated){
      const full=(tableState?.seats||[]).length>=Number(tableState?.max_seats||6);
      $('#tableControls').innerHTML=`<div class="jj-table-control-left"><b class="jj-control-title">観戦中</b><span class="hint">${full?'現在は満席です':'卓中央の「150bbで着席」から参加できます。空席の＋を押すと座席も選べます。'}</span></div>`;
      return;
    }
""",
        "observer seating CTA",
    )

    source = _replace_once(
        source,
        """      : '<div><b>JOIN TABLE</b><span>150bb · プレイマネー</span></div><button class="primary" id="jjJoinTableBtn">着席してプレイ</button>';
""",
        """      : '<div><b>JOIN TABLE</b><span>150bb · プレイマネー</span></div><button class="primary" id="jjJoinTableBtn">150bbで着席</button>';
""",
        "primary seating label",
    )

    source = _replace_once(
        source,
        """  renderLobby=async function(){
    if(currentTableId)return;
    $('#lobbyPanel').classList.remove('hidden');$('#pokerRoom').classList.add('hidden');
    const tables=await api('/tables');
    $('#tableCards').innerHTML=tables.map(t=>{
      const seated=Number(t.seated||0),active=Number(t.players||0),full=seated>=Number(t.max_seats||6),extra=[];
      if(seated!==active)extra.push(`着席中 ${seated}/6`);
      if(Number(t.sitouts||0)>0)extra.push(`一時離席 ${Number(t.sitouts||0)}`);
      return `<article class="lobby-card"><div class="eyebrow ${t.status==='playing'?'status-live':''}">${t.status==='playing'?'● HAND IN PROGRESS':'OPEN TABLE'}</div><h4>${safe(t.name)}</h4><div class="lobby-stats"><span>参加者 ${active}/6</span>${extra.map(x=>`<span>${x}</span>`).join('')}<span>0.5 / 1 bb</span><span>150bb start</span></div><p class="hint">観戦だけでも入れます。プレイする場合は「着席する」を押してください。</p><div class="jj-lobby-actions"><button class="soft" data-open-table="${safe(t.id)}">観戦する</button><button class="primary" data-jj-join="${safe(t.id)}" ${full?'disabled':''}>${full?'満席':'着席する · 150bb'}</button></div></article>`;
    }).join('')||'<div class="card empty">テーブルがありません</div>';
  };
""",
        """  renderLobby=async function(){
    if(currentTableId)return;
    $('#lobbyPanel').classList.remove('hidden');$('#pokerRoom').classList.add('hidden');
    const resultsBox=$('#onlineResults'),summaryBox=$('#onlineSummary');
    if(resultsBox)resultsBox.innerHTML='<div class="empty">結果を読み込み中…</div>';
    if(summaryBox)summaryBox.innerHTML='<div class="empty">統計を読み込み中…</div>';
    const [tables,resultsState,summaryState]=await Promise.all([
      api('/tables'),
      api('/online/results?limit=72').then(data=>({ok:true,data})).catch(error=>({ok:false,error})),
      api('/online/summary').then(data=>({ok:true,data})).catch(error=>({ok:false,error})),
    ]);
    $('#tableCards').innerHTML=tables.map(t=>{
      const seated=Number(t.seated||0),active=Number(t.players||0),full=seated>=Number(t.max_seats||6),extra=[];
      if(seated!==active)extra.push(`着席中 ${seated}/6`);
      if(Number(t.sitouts||0)>0)extra.push(`一時離席 ${Number(t.sitouts||0)}`);
      return `<article class="lobby-card"><div class="eyebrow ${t.status==='playing'?'status-live':''}">${t.status==='playing'?'● 対戦中':'参加受付中'}</div><h4>${safe(t.name)}</h4><div class="lobby-stats"><span>参加者 ${active}/6</span>${extra.map(x=>`<span>${x}</span>`).join('')}<span>0.5 / 1 bb</span><span>150bb固定</span></div><p class="hint">観戦だけでも入れます。プレイする場合は「150bbで着席」を押してください。</p><div class="jj-lobby-actions"><button class="soft" data-open-table="${safe(t.id)}">観戦する</button><button class="primary" data-jj-join="${safe(t.id)}" ${full?'disabled':''}>${full?'満席':'150bbで着席'}</button></div></article>`;
    }).join('')||'<div class="card empty">テーブルがありません</div>';
    if(resultsBox)resultsBox.innerHTML=resultsState.ok?onlineLedgerHTML(resultsState.data):`<div class="empty">結果を取得できませんでした。<button class="tiny ghost" data-jj-online-retry>再試行</button></div>`;
    if(summaryBox){
      if(summaryState.ok){const s=summaryState.data||{};summaryBox.innerHTML=`<div><span>対象ハンド</span><b>${fmt(s.hands)}</b></div><div><span>無効ハンド</span><b>${fmt(s.voided_hands||0)}</b></div><div><span>累計レーキ（卓全体）</span><b>${fmt(s.rake_bb)}bb</b></div><div><span>総ポット</span><b>${fmt(s.gross_pot_bb)}bb</b></div><div><span>ランキング換算</span><b>1bb = 3pt</b></div>`}
      else summaryBox.innerHTML='<div class="empty">統計を取得できませんでした。<button class="tiny ghost" data-jj-online-retry>再試行</button></div>';
    }
  };

  document.addEventListener('click',e=>{
    const retry=e.target.closest('[data-jj-online-retry]');
    if(!retry)return;
    e.preventDefault();
    renderLobby().catch(err=>toast(err.message));
  });
""",
        "lobby results and statistics",
    )

    return source.replace(
        "  // v1.24.0 unified online-poker presentation layer.",
        f"  // {PLAYER_UX_MARKER}\n  // v1.24.0 unified online-poker presentation layer.",
        1,
    )
