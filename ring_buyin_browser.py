from __future__ import annotations

"""Final browser-layer adapter for variable Ring buy-ins."""

MARKER = "ring variable buy-in ui 2026-10-05"


_INJECTION = r"""
  // ring variable buy-in ui 2026-10-05
  function jjRingBuyinRange(source){
    const bbSize=Math.max(1,Number(source?.big_blind||100));
    const minRaw=source?.min_buyin_bb!==undefined?Number(source.min_buyin_bb):Number(source?.min_buyin||150*bbSize)/bbSize;
    const maxRaw=source?.max_buyin_bb!==undefined?Number(source.max_buyin_bb):Number(source?.max_buyin||150*bbSize)/bbSize;
    const min=Math.max(1,Math.round(minRaw||150));
    const max=Math.max(min,Math.round(maxRaw||min));
    const preferred=Number(source?.default_buyin_bb||150);
    return {min,max,value:Math.max(min,Math.min(max,Math.round(preferred||150)))};
  }

  function jjRingBuyinLabel(source){
    const r=jjRingBuyinRange(source);
    return r.min===r.max?String(r.min)+'bb':String(r.min)+'–'+String(r.max)+'bb';
  }

  function jjRingBuyinForm(kind,source,options={}){
    const tableId=options.tableId||'',seat=options.seat??'',r=jjRingBuyinRange(source),fixed=r.min===r.max;
    const title=kind==='rebuy'?'リバイ':kind==='seat'?'Seat '+String(Number(seat)+1)+' に着席':'テーブルに着席';
    const action=kind==='rebuy'?'リバイする':'着席する';
    const id=kind==='rebuy'?'jjRingRebuyForm':kind==='seat'?'jjRingSeatForm':'jjRingJoinForm';
    openModal('<h3>'+title+'</h3><p class="hint">バイイン範囲 '+r.min+'bb〜'+r.max+'bb</p><form id="'+id+'" class="stack"><input type="hidden" name="table_id" value="'+safe(tableId)+'">'+(kind==='seat'?'<input type="hidden" name="seat" value="'+Number(seat)+'">':'')+'<label>バイイン（BB）<input name="buyin_bb" type="number" min="'+r.min+'" max="'+r.max+'" step="1" value="'+r.value+'" inputmode="numeric" '+(fixed?'readonly':'')+' required></label><button class="primary">'+action+'</button></form>');
  }

  async function jjRingPrepareJoin(tableId){
    if(!tableId)return;
    try{
      let state=currentTableId===tableId?tableState:null;
      if(!state){
        const d=await api('/tables/'+tableId);
        state=d.state;
      }
      if((state?.seats||[]).some(p=>p.user_id===me?.id)){
        if(currentTableId!==tableId)await openTable(tableId);
        return;
      }
      jjRingBuyinForm('join',state,{tableId});
    }catch(err){toast(err.message)}
  }

  seatClick=async function(seat){
    if(!currentTableId||!tableState)return;
    if(tableState.seats.some(p=>p.user_id===me.id))return toast('すでに着席しています');
    if(tableState.seats.some(p=>Number(p.seat)===Number(seat)))return toast('その席は使用中です');
    jjRingBuyinForm('seat',tableState,{tableId:currentTableId,seat});
  };

  const jjRingBaseRenderTableControls=renderTableControls;
  renderTableControls=function(){
    jjRingBaseRenderTableControls();
    const el=$('#tableControls');
    if(el&&tableState){
      const label=jjRingBuyinLabel(tableState);
      if(label!=='150bb')el.innerHTML=el.innerHTML.replaceAll('150bb',label);
    }
  };

  const jjRingBaseRenderPokerRoom=renderPokerRoom;
  renderPokerRoom=function(){
    jjRingBaseRenderPokerRoom();
    if(!tableState)return;
    const range=jjRingBuyinLabel(tableState);
    const bbSize=Math.max(1,Number(tableState.big_blind||100));
    const pct=Math.max(0,Number(tableState.rake_percent||0));
    const cap=Math.max(0,Number(tableState.rake_cap||0));
    const meta=$('#roomMeta');
    if(meta)meta.textContent='6-max · 0.5/1bb · '+range+' buy-in · rake '+Number((pct*100).toFixed(2))+'% / '+Number((cap/bbSize).toFixed(2))+'bb cap';
    const potEl=$('#potDisplay');
    if(potEl){
      const pot=Number(totalPot()||0),estimated=Math.min(Math.floor(pot*pct),cap,pot);
      let potLabel=potEl.querySelector('span:not(.jj-ring-rake)'),potValue=potEl.querySelector('b'),rakeLabel=potEl.querySelector('.jj-ring-rake');
      if(!potLabel||!potValue){
        potEl.replaceChildren();
        potLabel=document.createElement('span');potLabel.textContent='POT';
        potValue=document.createElement('b');
        potEl.append(potLabel,potValue);
      }
      potValue.textContent=bb(pot);
      if(!rakeLabel){rakeLabel=document.createElement('span');rakeLabel.className='jj-ring-rake';potEl.appendChild(rakeLabel)}
      rakeLabel.textContent='RAKE ≤ '+bb(estimated);
    }
    const observer=document.querySelector('#jjObserverJoin');
    if(observer&&range!=='150bb')observer.innerHTML=observer.innerHTML.replaceAll('150bb',range);
  };

  renderLobby=async function(){
    if(currentTableId)return;
    $('#lobbyPanel').classList.remove('hidden');$('#pokerRoom').classList.add('hidden');
    const tables=await api('/tables');
    $('#tableCards').innerHTML=tables.map(t=>{
      const seated=Number(t.seated||0),active=Number(t.players||0),maxSeats=Number(t.max_seats||6),full=seated>=maxSeats,extra=[],range=jjRingBuyinLabel(t);
      if(seated!==active)extra.push('着席中 '+seated+'/'+maxSeats);
      if(Number(t.sitouts||0)>0)extra.push('一時離席 '+Number(t.sitouts||0));
      return '<article class="lobby-card jj-sub-public-table"><div class="eyebrow '+(t.status==='playing'?'status-live':'')+'">'+(t.status==='playing'?'● HAND IN PROGRESS':'OPEN TABLE')+'</div><h4>'+safe(t.name)+'</h4><div class="lobby-stats"><span>参加者 '+active+'/'+maxSeats+'</span>'+extra.map(x=>'<span>'+x+'</span>').join('')+'<span>0.5 / 1 bb</span><span>'+range+' buy-in</span></div><p class="hint">観戦だけでも入れます。プレイする場合はバイイン額を選んで着席してください。</p><div class="jj-lobby-actions"><button class="soft" data-open-table="'+safe(t.id)+'">観戦する</button><button class="primary" data-jj-join="'+safe(t.id)+'" '+(full?'disabled':'')+'>'+(full?'満席':'着席する · '+range)+'</button></div></article>';
    }).join('')||'<div class="card empty">テーブルがありません</div>';
  };

  document.addEventListener('click',e=>{
    const rebuy=e.target.closest('[data-table-presence="rebuy"]');
    if(rebuy&&!rebuy.disabled&&tableState&&currentTableId){
      e.preventDefault();e.stopImmediatePropagation();
      jjRingBuyinForm('rebuy',tableState,{tableId:currentTableId});
      return;
    }
    const join=e.target.closest('#jjJoinTableBtn,[data-jj-join]');
    if(join&&!join.disabled){
      e.preventDefault();e.stopImmediatePropagation();
      const tableId=join.dataset.jjJoin||currentTableId;
      jjRingPrepareJoin(tableId);
    }
  },true);

  document.addEventListener('submit',async e=>{
    const form=e.target;
    if(!['jjRingSeatForm','jjRingJoinForm','jjRingRebuyForm'].includes(form.id))return;
    e.preventDefault();e.stopImmediatePropagation();
    if(form.dataset.submitting)return;
    form.dataset.submitting='1';
    const button=form.querySelector('button');if(button)button.disabled=true;
    const fd=new FormData(form),tableId=String(fd.get('table_id')||currentTableId||''),buyinBb=Number(fd.get('buyin_bb'));
    try{
      if(form.id==='jjRingSeatForm'){
        const seat=Number(fd.get('seat'));
        tableState=await post('/tables/'+tableId+'/seat',{seat,buyin_bb:buyinBb});
        closeModal();renderPokerRoom();toast(String(buyinBb)+'bbで着席しました');
      }else if(form.id==='jjRingJoinForm'){
        const next=await post('/tables/'+tableId+'/join',{buyin_bb:buyinBb});
        closeModal();
        if(currentTableId===tableId){tableState=next;renderPokerRoom()}else await openTable(tableId);
        toast(String(buyinBb)+'bbで着席しました。進行中なら次ハンドから参加します');
      }else{
        tableState=await post('/tables/'+tableId+'/presence',{mode:'rebuy',buyin_bb:buyinBb});
        closeModal();renderPokerRoom();toast(String(buyinBb)+'bbでリバイしました');
      }
    }catch(err){toast(err.message)}
    finally{delete form.dataset.submitting;if(button)button.disabled=false}
  },true);
"""


def transform_app_js(js: str) -> str:
    if MARKER in js:
        return js

    render_user = "$('#wallet').textContent='6MAX · 150BB';$('#homeWallet').textContent='150';"
    if js.count(render_user) != 1:
        raise RuntimeError("Ring buy-in user summary drift")
    js = js.replace(
        render_user,
        "$('#wallet').textContent='6MAX · 2 TABLES';$('#homeWallet').textContent='2';",
        1,
    )

    home_table = '<span>${x.players}/6 · 0.5/1bb · 150bb start</span>'
    if js.count(home_table) != 1:
        raise RuntimeError("Ring buy-in Home table summary drift")
    js = js.replace(
        home_table,
        '<span>${x.players}/6 · 0.5/1bb · ${jjRingBuyinLabel(x)} buy-in</span>',
        1,
    )

    anchor = "\n})();"
    index = js.rfind(anchor)
    if index < 0:
        raise RuntimeError("Ring buy-in browser injection anchor missing")
    return js[:index] + "\n" + _INJECTION.rstrip() + js[index:]


__all__ = ["MARKER", "transform_app_js"]
