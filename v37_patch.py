from __future__ import annotations
from pathlib import Path
import re


def apply(root: Path) -> None:
    _server(root / 'server.py')
    _app(root / 'static' / 'app.js')
    _styles(root / 'static' / 'styles.css')
    _index(root / 'static' / 'index.html')
    _sw(root / 'static' / 'sw.js')


def _server(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    s = s.replace('version="1.18.4"', 'version="1.18.5"').replace('"version":"1.18.4"', '"version":"1.18.5"')
    s = s.replace('request.url.query == "v=36"', 'request.url.query == "v=37"')
    p.write_text(s, encoding='utf-8')


def _app(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    if 'v1.18.5 mobile poker action ergonomics' in s:
        return
    marker = '})();'
    pos = s.rfind(marker)
    if pos < 0:
        raise RuntimeError('v1.18.5 app closing marker missing')
    addon = r'''

  // v1.18.5 mobile poker action ergonomics.
  // The action console now follows the common mobile-poker hierarchy:
  // a maximum of three primary decisions, exact amounts on the action itself,
  // sizing as a separate secondary choice, and no redundant Fold when Check is free.
  function jjV185FmtBb(v){
    const n=Number(v||0);
    return `${(Math.round(n*100)/100).toFixed(n%1?1:0)}bb`;
  }

  function jjV185SyncRaiseUi(){
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

  renderActionBar=function(){
    const l=tableState.legal||{can_act:false},hero=jjHero();
    if(!hero){$('#actionBar').innerHTML='<span class="hint">着席するとアクションパネルが表示されます</span>';return}
    const handLabel=jjMadeHand();
    if(!l.can_act){
      $('#actionBar').innerHTML=`<div class="jj-hero-summary"><div class="jj-hero-cards">${(hero.cards||[]).map(cardHTML).join('')}</div><div><b>${safe(handLabel)}</b><span>${hero.sitting_out?'一時離席中':tableState.status==='playing'?'アクション待ち':'次のハンドを待機'}</span></div></div>`;
      return;
    }
    const isPre=tableState.hand?.phase==='preflop',bounds=jjRaiseBounds(),min=bounds.min||0,max=bounds.max||0,call=Number(l.call_amount||0);
    const presets=isPre?[['2.5x',2.5],['3x',3],['4x',4]]:[['33%',33],['50%',50],['75%',75],['POT',100]];
    let quick=presets.map(([label,val])=>isPre?`<button class="jj-size-btn" data-raise-bb="${val}">${label}</button>`:`<button class="jj-size-btn" data-pot-pct="${val}">${label}</button>`).join('');
    if(l.can_raise&&l.can_all_in)quick+=`<button class="jj-size-btn jj-allin-size" data-allin-size>ALL-IN</button>`;
    const raiseControls=l.can_raise&&max>0?`<div class="jj-sizing"><div class="jj-size-row">${quick}</div><div class="jj-raise-editor"><input id="raiseSlider" aria-label="ベット・レイズ額" type="range" min="${min}" max="${max}" step="0.5" value="${min}"><label><input id="raiseTo" aria-label="ベット・レイズ額 bb" type="number" inputmode="decimal" min="${min}" max="${max}" step="0.5" value="${min}"><span>bb</span></label><b id="jjRaiseAmount">${jjV185FmtBb(min)}</b></div></div>`:'';

    const actions=[];
    // Folding when checking costs nothing is never useful and is a common mobile mis-tap.
    if(!l.can_check)actions.push('<button class="jj-action-btn jj-fold" data-action="fold"><small>FOLD</small><b>フォールド</b></button>');
    if(l.can_check)actions.push('<button class="jj-action-btn jj-check" data-action="check"><small>CHECK</small><b>チェック</b></button>');
    else actions.push(`<button class="jj-action-btn jj-call" data-action="call"><small>CALL</small><b>コール ${jjV185FmtBb(call)}</b></button>`);
    if(l.can_raise)actions.push(`<button class="jj-action-btn jj-raise" id="jjRaiseAction" data-action="raise"><small>${l.can_check?'BET':'RAISE'}</small><b>${l.can_check?'ベット':'レイズ'} ${jjV185FmtBb(min)}</b></button>`);
    // If a normal raise is unavailable but an all-in is legal, keep it as a primary action.
    if(l.can_all_in&&!l.can_raise)actions.push('<button class="jj-action-btn jj-allin" data-action="allin"><small>ALL-IN</small><b>オールイン</b></button>');

    $('#actionBar').innerHTML=`<div class="jj-action-context"><div class="jj-hero-cards">${(hero.cards||[]).map(cardHTML).join('')}</div><div><span>${safe(handLabel)}</span>${call?`<b>コール額 ${jjV185FmtBb(call)}</b>`:'<b>あなたの番</b>'}</div></div>${raiseControls}<div class="jj-main-actions jj-actions-${actions.length}">${actions.join('')}</div>`;
    jjV185SyncRaiseUi();
  };

  document.addEventListener('click',e=>{
    const allinSize=e.target.closest('[data-allin-size]');
    if(allinSize){jjSetRaiseBb(jjRaiseBounds().max);return}
    const action=e.target.closest('#actionBar [data-action]');
    if(action){
      // Immediate visual acknowledgement also suppresses fast double taps while
      // the existing authoritative action request is in flight.
      document.querySelectorAll('#actionBar [data-action]').forEach(b=>b.classList.add('jj-action-locked'));
      action.classList.add('is-pressed');
      window.setTimeout(()=>document.querySelectorAll('#actionBar [data-action]').forEach(b=>b.classList.remove('jj-action-locked','is-pressed')),2200);
    }
  });
  document.addEventListener('input',e=>{
    if(e.target?.id==='raiseSlider'||e.target?.id==='raiseTo')requestAnimationFrame(jjV185SyncRaiseUi);
  });
'''
    s = s[:pos] + addon + s[pos:]
    p.write_text(s, encoding='utf-8')


def _styles(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    if 'v1.18.5 mobile poker usability polish' in s:
        return
    s += r'''

/* v1.18.5 mobile poker usability polish.
   Primary controls are thumb-sized and visually dominant; secondary sizing is
   visible at once instead of hidden in a horizontal scroll; the selected amount
   is reflected on the action button before committing it. */
@media (max-width:760px){
  body.jj-mobile-table-open #pokerRoom button,
  body.jj-mobile-table-open #pokerRoom input[type=range]{touch-action:manipulation}

  body.jj-mobile-table-open #pokerRoom .jj-seat-box .name{font-size:.68rem!important;line-height:1.15!important}
  body.jj-mobile-table-open #pokerRoom .jj-seat-box .stack{font-size:.72rem!important;font-variant-numeric:tabular-nums!important}
  body.jj-mobile-table-open #pokerRoom .jj-player-state{font-size:.52rem!important;letter-spacing:.05em!important}
  body.jj-mobile-table-open #pokerRoom .jj-seat.active .jj-seat-box{
    border-color:#ffd866!important;
    box-shadow:0 0 0 2px rgba(255,216,102,.38),0 0 22px rgba(255,202,76,.18),0 7px 18px rgba(0,0,0,.38)!important;
  }
  body.jj-mobile-table-open #pokerRoom .jj-seat.is-folded{opacity:.34!important}
  body.jj-mobile-table-open #pokerRoom .jj-seat.is-sitting{opacity:.48!important}

  body.jj-mobile-table-open.jj-mobile-poker-can-act #actionBar{
    max-height:none!important;
    overflow:visible!important;
    border-top:1px solid rgba(255,216,102,.28)!important;
  }
  body.jj-mobile-table-open .jj-action-context{height:auto!important;min-height:27px!important;margin-bottom:6px!important}
  body.jj-mobile-table-open .jj-action-context span{font-size:.64rem!important}
  body.jj-mobile-table-open .jj-action-context b{font-size:.78rem!important;font-variant-numeric:tabular-nums!important}

  /* Every common size is visible without horizontal scrolling. */
  body.jj-mobile-table-open .jj-sizing{display:block!important;margin-bottom:7px!important}
  body.jj-mobile-table-open .jj-size-row{
    display:grid!important;
    grid-template-columns:repeat(5,minmax(0,1fr))!important;
    gap:5px!important;
    overflow:visible!important;
    padding:0!important;
    margin-bottom:6px!important;
  }
  body.jj-mobile-table-open .jj-size-btn{
    min-width:0!important;
    min-height:40px!important;
    height:40px!important;
    padding:0 4px!important;
    border-radius:9px!important;
    font-size:.68rem!important;
    transition:background .12s ease,border-color .12s ease,transform .08s ease!important;
  }
  body.jj-mobile-table-open .jj-size-btn:active{transform:scale(.97)!important}
  body.jj-mobile-table-open .jj-size-btn.is-selected{
    background:#5a4718!important;
    border-color:#f3c95b!important;
    color:#fff5cb!important;
    box-shadow:inset 0 0 0 1px rgba(255,231,153,.18)!important;
  }
  body.jj-mobile-table-open .jj-allin-size{border-color:rgba(190,105,183,.72)!important;color:#f4d9f2!important}
  body.jj-mobile-table-open .jj-allin-size.is-selected{background:#5e315a!important;border-color:#df8cd7!important;color:#fff!important}

  body.jj-mobile-table-open .jj-raise-editor{grid-template-columns:minmax(0,1fr) 82px!important;gap:8px!important;align-items:center!important}
  body.jj-mobile-table-open .jj-raise-editor input[type=range]{height:40px!important;min-height:40px!important;margin:0!important}
  body.jj-mobile-table-open .jj-raise-editor label{height:40px!important;min-height:40px!important;border-radius:9px!important}
  body.jj-mobile-table-open .jj-raise-editor input[type=number]{min-height:40px!important;height:40px!important;font-size:16px!important}
  body.jj-mobile-table-open .jj-raise-editor>b{display:none!important}

  /* Two or three wide decisions are considerably safer than four narrow ones. */
  body.jj-mobile-table-open .jj-main-actions{display:grid!important;gap:7px!important}
  body.jj-mobile-table-open .jj-main-actions.jj-actions-1{grid-template-columns:1fr!important}
  body.jj-mobile-table-open .jj-main-actions.jj-actions-2{grid-template-columns:repeat(2,minmax(0,1fr))!important}
  body.jj-mobile-table-open .jj-main-actions.jj-actions-3{grid-template-columns:repeat(3,minmax(0,1fr))!important}
  body.jj-mobile-table-open .jj-action-btn{
    min-height:56px!important;
    height:56px!important;
    border-radius:12px!important;
    padding:0 5px!important;
    touch-action:manipulation!important;
    -webkit-tap-highlight-color:transparent!important;
  }
  body.jj-mobile-table-open .jj-action-btn small{font-size:.52rem!important;letter-spacing:.1em!important}
  body.jj-mobile-table-open .jj-action-btn b{font-size:.78rem!important;line-height:1.12!important;white-space:nowrap!important}
  body.jj-mobile-table-open .jj-action-btn.is-pressed{transform:scale(.975)!important;filter:brightness(1.14)!important}
  body.jj-mobile-table-open .jj-action-btn.jj-action-locked{pointer-events:none!important;opacity:.76!important}
  body.jj-mobile-table-open .jj-action-btn.jj-action-locked.is-pressed{opacity:1!important}

  body.jj-mobile-table-open #tableControls button{min-height:44px!important;height:44px!important}
  body.jj-mobile-table-open #backLobby{min-width:44px!important}
}

@media (max-width:380px) and (orientation:portrait){
  body.jj-mobile-table-open .jj-size-row{gap:4px!important}
  body.jj-mobile-table-open .jj-size-btn{font-size:.62rem!important;padding:0 2px!important}
  body.jj-mobile-table-open .jj-action-btn b{font-size:.72rem!important}
}

@media (prefers-reduced-motion:reduce){
  body.jj-mobile-table-open .jj-your-turn,
  body.jj-mobile-table-open .jj-card-deal,
  body.jj-mobile-table-open .jj-bet-pulse{animation:none!important}
  body.jj-mobile-table-open .jj-action-btn,
  body.jj-mobile-table-open .jj-size-btn{transition:none!important}
}
'''
    p.write_text(s, encoding='utf-8')


def _index(p: Path) -> None:
    s = p.read_text(encoding='utf-8').replace('?v=36', '?v=37')
    p.write_text(s, encoding='utf-8')


def _sw(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    s = re.sub(r'jj-arena-live-v\d+', 'jj-arena-live-v37', s)
    p.write_text(s, encoding='utf-8')
