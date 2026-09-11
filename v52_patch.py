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
    text = text.replace('version="1.23.0"', 'version="1.24.1"')
    text = text.replace('"version":"1.23.0"', '"version":"1.24.1"')
    text = text.replace('request.url.query == "v=51"', 'request.url.query == "v=53"')
    path.write_text(text, encoding="utf-8")


def _app(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "v1.24.0 unified online-poker presentation layer"
    if marker in text:
        return
    pos = text.rfind("})();")
    if pos < 0:
        raise RuntimeError("v1.24 app closing marker missing")

    addon = r'''

  // v1.24.0 unified online-poker presentation layer.
  // This is the authoritative final renderer for both desktop and mobile.
  // It deliberately stops relying on generic descendants such as
  // `.jj-action-context b`, which caused the v1.23 desktop card/call collision.
  const JJ_V124_DESKTOP_MQ=window.matchMedia('(min-width:761px)');
  const JJ_V124_STREET={preflop:'PREFLOP',flop:'FLOP',turn:'TURN',river:'RIVER',complete:'SHOWDOWN'};

  function jjV124FmtNumber(v,maxDecimals=1){
    const n=Number(v||0);
    if(!Number.isFinite(n))return '0';
    const p=Math.pow(10,maxDecimals),rounded=Math.round(n*p)/p;
    return Number.isInteger(rounded)?String(rounded):rounded.toFixed(maxDecimals).replace(/0+$/,'').replace(/\.$/,'');
  }

  function jjV124RawBb(chips,{ceil=false,maxDecimals=1}={}){
    const big=Math.max(1,Number(tableState?.big_blind||100));
    const value=Number(chips||0)/big;
    return `${ceil?Math.ceil(value):jjV124FmtNumber(value,maxDecimals)}bb`;
  }

  function jjV124SuitLabel(s){return({s:'スペード',h:'ハート',d:'ダイヤ',c:'クラブ'})[s]||''}
  function jjV124SuitName(s){return({s:'spade',h:'heart',d:'diamond',c:'club'})[s]||'unknown'}

  // Use spans for rank/suit. Old generic <b> selectors can no longer mutate a
  // card rank even if an older compatibility layer is still present upstream.
  cardHTML=function(c){
    if(!c||c==='??')return '<span class="card-face back" aria-label="伏せ札">JJ</span>';
    const rank=c[0]==='T'?'10':c[0],suit=c[1],name=jjV124SuitName(suit),glyph=suitChar(suit);
    return `<span class="card-face jj-four-suit suit-${name}" aria-label="${safe(rank)} ${safe(jjV124SuitLabel(suit))}"><span class="jj-card-rank">${safe(rank)}</span><span class="jj-card-suit">${glyph}</span></span>`;
  };

  function jjV124Hero(){return tableState?.seats?.find(p=>Number(p.user_id)===Number(me?.id))||null}
  function jjV124PotChips(){return Number(typeof jjTotalPot==='function'?jjTotalPot():0)||0}
  function jjV124EffectiveChips(hero){
    if(!hero)return 0;
    const opponents=(tableState?.seats||[]).filter(p=>Number(p.user_id)!==Number(hero.user_id)&&p.in_hand&&!p.folded&&Number(p.stack||0)>=0);
    const oppMax=opponents.length?Math.max(...opponents.map(p=>Number(p.stack||0))):Number(hero.stack||0);
    return Math.min(Number(hero.stack||0),oppMax);
  }
  function jjV124PreflopBaseBb(hero,l){
    const big=Math.max(1,Number(tableState?.big_blind||100));
    return Math.max(1,(Number(hero?.round_bet||0)+Number(l?.call_amount||0))/big);
  }
  function jjV124PresetTarget(kind,value,hero,l){
    if(kind==='pre')return jjClampRaiseBb(jjV124PreflopBaseBb(hero,l)*Number(value));
    return jjPotPctBb(Number(value));
  }

  function jjV124SizingMarkup(hero,l){
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

  function jjV124ActionButtons(l){
    const callChips=Number(l.call_amount||0),callText=jjV124RawBb(callChips,{maxDecimals:1});
    const bounds=jjRaiseBounds(),raiseAmount=Number($('#raiseTo')?.value||bounds.min||0);
    const actions=[];
    if(!l.can_check)actions.push('<button class="jj-action-btn jj-fold" data-action="fold"><small>FOLD</small><b>フォールド</b></button>');
    if(l.can_check){
      actions.push('<button class="jj-action-btn jj-check" data-action="check"><small>CHECK</small><b>チェック</b></button>');
    }else if(l.can_call){
      actions.push(`<button class="jj-action-btn jj-call" data-action="call"><small>CALL</small><b>コール <span id="jjV124CallButtonAmount">${safe(callText)}</span></b></button>`);
    }
    if(l.can_raise){
      actions.push(`<button class="jj-action-btn jj-raise" id="jjRaiseAction" data-action="raise"><small>${l.can_check?'BET':'RAISE'}</small><b>${l.can_check?'ベット':'レイズ'} ${safe(jjV185FmtBb(raiseAmount))}</b></button>`);
    }else if(l.can_all_in){
      actions.push('<button class="jj-action-btn jj-allin" data-action="allin"><small>ALL-IN</small><b>オールイン</b></button>');
    }
    return `<div class="jj-main-actions jj-actions-${actions.length}">${actions.join('')}</div>`;
  }

  function jjV124DecisionMeta(hero,l){
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
  document.addEventListener('click',e=>{
    const step=e.target.closest('[data-jj-raise-step]');
    if(step){
      e.preventDefault();e.stopPropagation();
      const current=Number($('#raiseTo')?.value||jjRaiseBounds().min||0);
      jjSetRaiseBb(current+Number(step.dataset.jjRaiseStep||0));
      if(typeof jjV185SyncRaiseUi==='function')jjV185SyncRaiseUi();
    }
  });

  // Desktop bet markers use explicit poker-table lanes rather than the old
  // seat-to-centre interpolation. Hole cards and bet chips can no longer share
  // the same visual lane. Mobile keeps the validated portrait geometry.
  if(typeof jjBetPos==='function'&&typeof jjVisualIndex==='function'){
    const jjV124MobileBetPos=jjBetPos;
    jjBetPos=function(actual){
      if(!JJ_V124_DESKTOP_MQ.matches)return jjV124MobileBetPos(actual);
      const map=[
        {left:61,top:68},{left:31,top:61},{left:31,top:35},
        {left:61,top:25},{left:69,top:35},{left:69,top:61},
      ];
      return map[jjVisualIndex(actual)]||jjV124MobileBetPos(actual);
    };
  }

  function jjV124PolishTableChrome(){
    if(!currentTableId||!tableState)return;
    const ready=$('#tableControls .jj-ready-count');
    if(ready&&/^次ハンド\s/.test(ready.textContent||''))ready.textContent=(ready.textContent||'').replace(/^次ハンド\s*/,'次ハンド参加予定 ');
    const sound=$('#jjSoundToggle');
    const head=$('#pokerRoom .room-head');
    if(JJ_V124_DESKTOP_MQ.matches&&sound&&head&&!head.contains(sound))head.appendChild(sound);
    document.body.classList.toggle('jj-v124-desktop-poker',JJ_V124_DESKTOP_MQ.matches&&!!currentTableId);
  }

  if(typeof renderPokerRoom==='function'){
    const jjV124BaseRenderPokerRoom=renderPokerRoom;
    renderPokerRoom=function(){
      jjV124BaseRenderPokerRoom();
      jjV124PolishTableChrome();
      if(tableState?.legal?.can_act){
        if(typeof jjV123ActionState==='function')jjV123ActionState();
        if(typeof jjV123ClockFeedback==='function')jjV123ClockFeedback();
      }
    };
  }

  JJ_V124_DESKTOP_MQ.addEventListener?.('change',()=>{
    jjV124PolishTableChrome();
    if(currentTableId&&tableState)requestAnimationFrame(()=>{try{renderPokerRoom()}catch{}});
  });
'''

    path.write_text(text[:pos] + addon + "\n" + text[pos:], encoding="utf-8")


def _styles(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    marker = "v1.24.0 online poker visual system"
    if marker in text:
        return

    addon = r'''

/* v1.24.0 online poker visual system
   One hierarchy across desktop/mobile: table first, decision facts second,
   sizing third, primary action last. Desktop and phone receive different layout
   rules instead of forcing one compressed control surface onto both. */
.card-face.jj-four-suit{white-space:nowrap!important;flex-direction:row!important;flex-wrap:nowrap!important;line-height:1!important}
.card-face.jj-four-suit .jj-card-rank,.card-face.jj-four-suit .jj-card-suit{display:inline-block!important;flex:0 0 auto!important;white-space:nowrap!important;writing-mode:horizontal-tb!important;word-break:keep-all!important}

#actionBar .jj-v124-decision-meta{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:1px;margin:0 0 10px;border:1px solid rgba(255,255,255,.08);border-radius:12px;overflow:hidden;background:rgba(255,255,255,.035)}
#actionBar .jj-v124-decision-meta>div{min-width:0;padding:7px 10px;border-right:1px solid rgba(255,255,255,.065)}
#actionBar .jj-v124-decision-meta>div:last-child{border-right:0}
#actionBar .jj-v124-decision-meta span{display:block;margin-bottom:2px;color:#82958c;font-size:.56rem;font-weight:900;letter-spacing:.11em;white-space:nowrap}
#actionBar .jj-v124-decision-meta strong{display:block;color:#edf5f1;font-size:.84rem;font-weight:900;line-height:1.15;white-space:nowrap;font-variant-numeric:tabular-nums}
#actionBar .jj-v124-decision-meta #jjV124CallAmount{color:#ffe39a}
#actionBar .jj-v124-time .jj-action-clock{display:block!important;margin:0!important;min-width:0!important;padding:0!important;border-radius:4px!important;font-size:.84rem!important;text-align:left!important;background:linear-gradient(90deg,rgba(231,190,83,.22) 0 var(--jj-v123-clock-pct,100%),transparent var(--jj-v123-clock-pct,100%) 100%)!important}

#actionBar .jj-v124-sizing{display:grid!important;grid-template-columns:auto minmax(260px,1fr)!important;gap:12px!important;align-items:center!important;margin:0 0 10px!important}
#actionBar .jj-v124-sizing .jj-size-row{display:flex!important;flex-wrap:nowrap!important;gap:6px!important;overflow:visible!important;margin:0!important;padding:0!important}
#actionBar .jj-v124-sizing .jj-size-btn{min-width:62px!important;height:42px!important;min-height:42px!important;padding:0 11px!important;border-radius:9px!important;font-size:.72rem!important;line-height:1!important;white-space:nowrap!important}
#actionBar .jj-v124-sizing .jj-size-btn small{display:none!important}
#actionBar .jj-v124-raise-editor{display:grid!important;grid-template-columns:minmax(160px,1fr) auto!important;gap:10px!important;align-items:center!important;min-width:0!important}
#actionBar .jj-v124-raise-editor>input[type=range]{width:100%!important;min-width:0!important;height:42px!important;margin:0!important}
#actionBar .jj-v124-stepper{display:grid;grid-template-columns:36px minmax(92px,110px) 36px;align-items:stretch;height:42px;border:1px solid #415048;border-radius:9px;background:#0b100f;overflow:hidden}
#actionBar .jj-v124-stepper>button{border:0;border-radius:0;background:#1b2521;color:#dfe9e4;font-size:1rem;font-weight:900;padding:0}
#actionBar .jj-v124-stepper>button:hover{background:#26332e}
#actionBar .jj-v124-stepper label{display:flex!important;align-items:center!important;min-width:0!important;height:42px!important;border:0!important;border-left:1px solid #35433d!important;border-right:1px solid #35433d!important;border-radius:0!important;background:transparent!important;overflow:hidden!important}
#actionBar .jj-v124-stepper input[type=number]{width:100%!important;min-width:0!important;height:40px!important;min-height:40px!important;padding:0 4px 0 8px!important;border:0!important;background:transparent!important;color:#fff!important;text-align:right!important;font-size:.95rem!important;font-weight:900!important;font-variant-numeric:tabular-nums!important}
#actionBar .jj-v124-stepper label span{flex:0 0 auto!important;padding:0 8px 0 2px!important;color:#93a79e!important;font-size:.62rem!important;font-weight:900!important;white-space:nowrap!important;writing-mode:horizontal-tb!important}

#actionBar .jj-main-actions{display:grid!important;gap:8px!important;width:100%!important}
#actionBar .jj-main-actions.jj-actions-1{grid-template-columns:1fr!important}
#actionBar .jj-main-actions.jj-actions-2{grid-template-columns:repeat(2,minmax(0,1fr))!important}
#actionBar .jj-main-actions.jj-actions-3{grid-template-columns:repeat(3,minmax(0,1fr))!important}
#actionBar .jj-main-actions.jj-actions-4{grid-template-columns:repeat(4,minmax(0,1fr))!important}
#actionBar .jj-action-btn{min-width:0!important}
#actionBar .jj-action-btn b{font-size:clamp(.9rem,1.15vw,1.08rem)!important;line-height:1.12!important;white-space:nowrap!important;letter-spacing:0!important}
#actionBar .jj-action-btn small{font-size:.56rem!important;line-height:1!important}
#actionBar .jj-v124-waiting{display:flex;align-items:center;justify-content:space-between;min-height:42px;padding:0 4px;color:#aebdb6;font-size:.78rem}
#actionBar .jj-v124-waiting strong{color:#e8f1ed;font-size:.88rem;font-variant-numeric:tabular-nums}

@media(min-width:761px){
  body.jj-v124-desktop-poker #pokerRoom .poker-zone{padding:12px 14px 14px!important}
  body.jj-v124-desktop-poker #pokerTable .felt-center{top:42%!important}
  body.jj-v124-desktop-poker #pokerRoom .jj-seat.is-hero .jj-hole{z-index:20!important;top:-78px!important}
  body.jj-v124-desktop-poker #pokerRoom .jj-seat.is-hero .jj-hole .card-face{width:54px!important;height:76px!important;font-size:1.22rem!important}
  body.jj-v124-desktop-poker #pokerRoom .jj-hole{z-index:12!important}
  body.jj-v124-desktop-poker #pokerRoom .jj-hole .card-face{position:relative!important;z-index:13!important}
  body.jj-v124-desktop-poker #pokerRoom .jj-bet-marker{z-index:9!important;max-width:88px!important;white-space:nowrap!important;pointer-events:none!important}
  body.jj-v124-desktop-poker #pokerRoom .jj-bet-marker b{font-size:.76rem!important}
  body.jj-v124-desktop-poker #pokerRoom .table-controls{min-height:40px!important;padding:5px 2px!important;margin:2px 0 6px!important}
  body.jj-v124-desktop-poker #pokerRoom .table-controls button{min-height:34px!important;height:34px!important;padding:0 11px!important;border-radius:9px!important;font-size:.7rem!important}
  body.jj-v124-desktop-poker #pokerRoom .jj-ready-count{font-size:.62rem!important}
  body.jj-v124-desktop-poker #pokerRoom .room-head .jj-sound-toggle{margin-left:auto!important;min-width:0!important;min-height:34px!important;height:34px!important;padding:0 10px!important;border-radius:9px!important;font-size:.7rem!important}
  body.jj-v124-desktop-poker #actionBar{margin-top:6px!important;padding:12px 14px 14px!important;border-radius:14px!important;background:linear-gradient(180deg,#111816,#090e0c)!important}
  body.jj-v124-desktop-poker #actionBar .jj-v123-action-status{min-height:26px!important;margin:0 0 7px!important;padding:4px 8px!important;font-size:.65rem!important}
  body.jj-v124-desktop-poker #actionBar .jj-v123-disabled-hints{margin:-1px 0 7px!important}
  body.jj-v124-desktop-poker #actionBar .jj-action-btn{min-height:62px!important;height:62px!important;border-radius:11px!important}
}

@media(max-width:1050px) and (min-width:761px){
  #actionBar .jj-v124-decision-meta{grid-template-columns:repeat(3,minmax(0,1fr))}
  #actionBar .jj-v124-decision-meta>div:nth-child(3){border-right:0}
  #actionBar .jj-v124-sizing{grid-template-columns:1fr!important}
}

@media(max-width:760px){
  body.jj-mobile-table-open #actionBar .jj-v124-decision-meta{grid-template-columns:repeat(3,minmax(0,1fr))!important;margin-bottom:6px!important;border-radius:9px!important}
  body.jj-mobile-table-open #actionBar .jj-v124-decision-meta>div{padding:4px 6px!important}
  body.jj-mobile-table-open #actionBar .jj-v124-decision-meta>div:nth-child(3){border-right:0!important}
  body.jj-mobile-table-open #actionBar .jj-v124-decision-meta span{font-size:.46rem!important;margin-bottom:1px!important}
  body.jj-mobile-table-open #actionBar .jj-v124-decision-meta strong{font-size:.66rem!important}
  body.jj-mobile-table-open #actionBar .jj-v124-time .jj-action-clock{font-size:.66rem!important}
  body.jj-mobile-table-open #actionBar .jj-v124-sizing{display:block!important;margin-bottom:6px!important}
  body.jj-mobile-table-open #actionBar .jj-v124-sizing .jj-size-row{display:grid!important;grid-template-columns:repeat(auto-fit,minmax(48px,1fr))!important;gap:5px!important;margin-bottom:5px!important}
  body.jj-mobile-table-open #actionBar .jj-v124-sizing .jj-size-btn{min-width:0!important;height:40px!important;min-height:40px!important;padding:0 4px!important;font-size:.65rem!important}
  body.jj-mobile-table-open #actionBar .jj-v124-raise-editor{grid-template-columns:minmax(0,1fr) auto!important;gap:7px!important}
  body.jj-mobile-table-open #actionBar .jj-v124-stepper{grid-template-columns:32px 78px 32px!important;height:40px!important}
  body.jj-mobile-table-open #actionBar .jj-v124-stepper label{height:40px!important;min-height:40px!important}
  body.jj-mobile-table-open #actionBar .jj-v124-stepper input[type=number]{height:38px!important;min-height:38px!important;font-size:16px!important;padding-left:4px!important}
  body.jj-mobile-table-open #actionBar .jj-v124-stepper label span{padding-right:5px!important;font-size:.55rem!important}
  body.jj-mobile-table-open #actionBar .jj-action-btn b{font-size:.78rem!important}
}
'''

    path.write_text(text.rstrip() + addon + "\n", encoding="utf-8")


def _index(path: Path) -> None:
    text = path.read_text(encoding="utf-8").replace("?v=51", "?v=53")
    path.write_text(text, encoding="utf-8")


def _sw(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"jj-arena-live-v(?:\d+)(?:-hotfix\d+)?", "jj-arena-live-v53", text)
    path.write_text(text, encoding="utf-8")
