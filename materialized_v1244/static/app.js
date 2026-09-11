(() => {
  const $ = (s, root=document) => root.querySelector(s);
  const $$ = (s, root=document) => [...root.querySelectorAll(s)];
  let me=null;
  let currentView='home';
  let rankMode='overall';
  let rankings=[];
  let currentTableId=null;
  let tableState=null;
  let tableMessages=[];
  let tableWS=null;
  let tablePoll=null;
  let tableHeartbeat=null;
  let tableReconnect=null;
  let tableClock=null;
  let wakeLock=null;
  let wasMyTurn=false;
  let actionBusy=false;
  let tableChatSig="";
  let handLogSig="";
  let quiz={count:0,score:0,q:null};

  const titles={home:['DASHBOARD','今日のJJ'],ranking:['LEADERBOARD','ランキング'],tables:['REALTIME NLH','オンラインテーブル'],points:['ADMIN','ポイント入力'],members:['ADMIN','ユーザー管理'],schedule:['CLUB CALENDAR','活動予定'],news:['BOARD','お知らせ'],lab:['POKER LAB','学習'],discussion:['OPEN TABLE','戦略議論']};
  const fmt=n=>Number(n||0).toLocaleString('ja-JP');
  const bb=(n,state=tableState)=>{const big=Number(state?.big_blind||100);const v=Number(n||0)/big;return `${v.toLocaleString('ja-JP',{maximumFractionDigits:2})}bb`};
  const safe=s=>String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const dateFmt=(s,opts={year:'numeric',month:'short',day:'numeric'})=>{try{return new Intl.DateTimeFormat('ja-JP',opts).format(new Date(s))}catch{return s}};
  const isoLocal=()=>{const d=new Date();d.setMinutes(d.getMinutes()-d.getTimezoneOffset());return d.toISOString().slice(0,16)};
  function toast(msg){const el=$('#toast');el.textContent=msg;el.classList.add('show');clearTimeout(el._t);el._t=setTimeout(()=>el.classList.remove('show'),2600)}
  async function acquireWakeLock(){try{if('wakeLock' in navigator&&document.visibilityState==='visible'&&currentTableId&&!wakeLock)wakeLock=await navigator.wakeLock.request('screen')}catch{wakeLock=null}}
  async function releaseWakeLock(){try{if(wakeLock)await wakeLock.release()}catch{}wakeLock=null}
  async function api(path,opts={}){const headers={...(opts.body?{'Content-Type':'application/json'}:{}),...(opts.headers||{})};const res=await fetch('/api'+path,{credentials:'same-origin',...opts,headers});if(res.status===401){logout(false);throw new Error('ログインが必要です')}let data=null;try{data=await res.json()}catch{}if(!res.ok)throw new Error(data?.detail||data?.message||`HTTP ${res.status}`);return data}
  function post(path,body={}){return api(path,{method:'POST',body:JSON.stringify(body)})}
  function patch(path,body={}){return api(path,{method:'PATCH',body:JSON.stringify(body)})}

  async function init(){bind();try{me=await api('/me');showApp();await refreshAll()}catch{showAuth()}}
  function showAuth(){$('#authView').classList.remove('hidden');$('#appView').classList.add('hidden')}
  function showApp(){$('#authView').classList.add('hidden');$('#appView').classList.remove('hidden');renderUser();switchView(currentView)}
  async function logout(remote=true){me=null;disconnectTable();if(remote){try{await fetch('/api/auth/logout',{method:'POST',credentials:'same-origin'})}catch{}}showAuth()}
  function renderUser(){if(!me)return;$('#userName').textContent=me.name;$('#userRole').textContent=me.role.toUpperCase();$('#wallet').textContent='6MAX · 150BB';$('#homeWallet').textContent='150';$$('.admin-only').forEach(el=>el.classList.toggle('hidden',me.role!=='admin'))}
  async function refreshMe(){me=await api('/me');renderUser()}

  function switchView(v){if((v==='points'||v==='members')&&me?.role!=='admin')v='home';currentView=v;$$('.view').forEach(x=>x.classList.toggle('active-view',x.id===v+'View'));let activeNav=null;$$('.nav').forEach(x=>{const on=x.dataset.view===v;x.classList.toggle('active',on);x.toggleAttribute('aria-current',on);if(on)activeNav=x});if(activeNav&&innerWidth<=760)activeNav.scrollIntoView({block:'nearest',inline:'center',behavior:'smooth'});$('#viewEyebrow').textContent=titles[v]?.[0]||'';$('#viewTitle').textContent=titles[v]?.[1]||'';if(v!=='tables'&&currentTableId)disconnectTable();refreshView(v).catch(e=>toast(e.message))}
  async function refreshView(v){if(v==='home')return renderHome();if(v==='ranking')return renderRanking();if(v==='tables')return renderLobby();if(v==='points')return renderPoints();if(v==='members')return renderMembers();if(v==='schedule')return renderSchedules();if(v==='news')return renderNews();if(v==='discussion')return renderThreads();if(v==='lab')return renderQuiz()}
  async function refreshAll(){await Promise.all([loadRankings(),renderHome()]);}

  async function loadRankings(month=null,season='fall'){const q=new URLSearchParams({season});if(month)q.set('month',month);rankings=await api('/rankings?'+q.toString());return rankings}
  async function renderHome(){const [r,s,n,t]=await Promise.all([api('/rankings'),api('/schedules'),api('/announcements'),api('/tables')]);rankings=r;const top=r[0];$('#heroLeader').textContent=top?.name||'—';$('#heroLeaderPoints').textContent=fmt(top?.points)+' pt';$('#homeTop').innerHTML=r.slice(0,5).map((p,i)=>`<article class="top-player card"><span class="rank">#${i+1}</span><strong>${safe(p.name)}</strong><b>${fmt(p.points)} pt</b><div class="hint">${p.games} entries</div></article>`).join('')||'<div class="empty">No data</div>';const upcoming=s.filter(x=>new Date(`${x.date}T${x.time||'00:00'}`)>=new Date()).slice(0,3);$('#homeSchedule').innerHTML=upcoming.length?upcoming.map(x=>`<div class="mini-item"><strong>${safe(x.title)}</strong><span>${safe(x.date)} ${safe(x.time)} · ${safe(x.room)}</span></div>`).join(''):'<div class="empty">予定はまだありません</div>';$('#homeTables').innerHTML=t.map(x=>`<div class="mini-item"><strong>${safe(x.name)}</strong><span>${x.players}/6 · 0.5/1bb · 150bb start</span></div>`).join('')||'<div class="empty">卓はありません</div>';$('#homeNews').innerHTML=n.slice(0,3).map(x=>`<div class="mini-item"><strong>${safe(x.title)}</strong><span>${safe(x.date)}</span></div>`).join('')||'<div class="empty">お知らせはありません</div>'}

  function monthOptions(){return ['2026-09','2026-10','2026-11','2026-12','2027-01','2027-02','2027-03']}
  async function renderRanking(){const month=rankMode==='month'?$('#rankMonth').value||monthOptions()[0]:null,season=rankMode==='archive'?'summer':'fall';await loadRankings(month,season);if(!$('#rankMonth').options.length)$('#rankMonth').innerHTML=monthOptions().map(m=>`<option>${m}</option>`).join('');$$('[data-rank-mode]').forEach(b=>b.classList.toggle('active',b.dataset.rankMode===rankMode));$('#rankMonth').disabled=rankMode!=='month';const q=$('#rankSearch').value.trim().toLowerCase();const rows=rankings.filter(x=>x.name.toLowerCase().includes(q));const label=rankMode==='archive'?'前期参考':'後期';$('#podium').innerHTML=rows.slice(0,3).map((p,i)=>`<article class="podium-card card"><div class="eyebrow">${label} #${i+1}</div><strong>${safe(p.name)}</strong><b>${fmt(p.points)} pt</b><div class="hint">Club ${fmt(p.club_points)} · Online ${p.online_points>=0?'+':''}${fmt(p.online_points)}</div></article>`).join('')||`<div class="card empty">${rankMode==='archive'?'前期データは参考表示です':'後期ランキングはまだ0件です'}</div>`;$('#rankBody').innerHTML=rows.map(p=>`<tr><td class="rank-num">#${p.rank}</td><td><strong>${safe(p.name)}</strong></td><td><b>${fmt(p.points)}</b></td><td>${fmt(p.club_points)}</td><td class="${p.online_points>=0?'positive':'negative'}">${p.online_points>=0?'+':''}${fmt(p.online_points)}</td><td>${p.online_hands||0}</td></tr>`).join('')}

  async function renderPoints(){if(me.role!=='admin')return;const [ents,names]=await Promise.all([api('/entries?limit=40'),api('/ranking-names')]);$('#playerNames').innerHTML=names.map(name=>`<option value="${safe(name)}"></option>`).join('');if(!$('#pointName').value)$('#pointName').value=me.name;$('#pointDate').min='2026-09-01T00:00';$('#pointDate').max='2027-03-31T23:59';$('#pointDate').value=$('#pointDate').value||isoLocal();if(!$('#pointInitial').options.length)setPointInitialOptions();pointCalc();$('#recentEntries').innerHTML=ents.map(e=>{const chips=pointDenoms.map(d=>[d,Number(e[`chip_${d}`]||0)]).filter(([,c])=>c>0).map(([d,c])=>`${d}×${c}`).join(' / ');return `<div class="list-item"><strong>${safe(e.name)} <span style="color:${e.points>=0?'var(--accent2)':'var(--danger)'}">${e.points>=0?'+':''}${fmt(e.points)}</span></strong><div class="hint">${dateFmt(e.date,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})} · ${safe(e.game||e.game_type)} · 残り ${fmt(e.remaining)}${chips?` · ${safe(chips)}`:''}</div></div>`}).join('')||'<div class="empty">後期の入力はまだありません</div>'}
  const pointDenoms=[1,5,10,25,100,500];
  const pointInitialOptions={ring:[{value:450,label:'450 / blind 1-3-3'},{value:900,label:'900 / blind 2-5-5'},{value:2000,label:'2000 / blind 5-10-10'}],tournament:[{value:300,label:'300 / tournament'},{value:400,label:'400 / tournament'},{value:500,label:'500 / tournament'},{value:600,label:'600 / tournament'},{value:800,label:'800 / tournament'},{value:1000,label:'1000 / tournament'}]};
  function setPointInitialOptions(){const game=$('#pointGame')?.value||'ring',sel=$('#pointInitial');if(!sel)return;const previous=Number(sel.value||0),opts=pointInitialOptions[game]||pointInitialOptions.ring;sel.innerHTML=opts.map(o=>`<option value="${o.value}">${o.label}</option>`).join('');if(opts.some(o=>o.value===previous))sel.value=String(previous);else sel.value=String(game==='ring'?450:400);pointCalc()}
  function chipCount(value){const n=Number(value||0);return Number.isFinite(n)&&n>=0?Math.floor(n):0}
  function pointCalc(){const initial=Number($('#pointInitial')?.value||0),re=chipCount($('#pointReentries')?.value),rem=pointDenoms.reduce((sum,d)=>sum+d*chipCount($(`#pointChip${d}`)?.value),0),p=rem-(re+1)*initial;if($('#pointRemainingPreview'))$('#pointRemainingPreview').textContent=fmt(rem);if($('#pointPreview'))$('#pointPreview').textContent=(p>=0?'+':'')+fmt(p)+' pt';return {remaining:rem,points:p}}

  async function renderSchedules(){const s=await api('/schedules');$('#scheduleList').innerHTML=s.length?s.map(x=>`<article class="schedule-card card"><div class="eyebrow">${safe(x.date)}</div><div class="date-big">${safe(x.time)}</div><h3>${safe(x.title)}</h3><b>教室 ${safe(x.room)}</b><p class="hint">${safe(x.note||'')}</p><div class="hint">追加: ${safe(x.creator||'JJ')}</div></article>`).join(''):'<div class="card empty">予定はまだありません。上の「予定追加」から登録できます。</div>'}
  async function renderNews(){const n=await api('/announcements');$('#newsGrid').innerHTML=n.length?n.map(x=>`<article class="news-card"><span class="tag">${x.kind==='external'?'EXTERNAL':'JJ'}</span><div class="hint">${safe(x.date)}</div><h3>${safe(x.title)}</h3><p>${safe(x.body)}</p>${x.url?`<a href="${safe(x.url)}" target="_blank" rel="noopener">詳細を見る →</a>`:''}</article>`).join(''):'<div class="card empty">お知らせはありません</div>'}
  async function renderThreads(){const ts=await api('/threads');$('#threads').innerHTML=ts.map(t=>`<article class="thread"><div class="thread-meta"><span>${safe(t.author_name)}</span><span>${dateFmt(t.created_at,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})}</span></div><h3>${safe(t.title)}</h3><p>${safe(t.body)}</p><div>${(t.replies||[]).map(r=>`<div class="reply"><b>${safe(r.author_name)}</b>${safe(r.body)}</div>`).join('')}</div><form class="reply-form" data-thread="${t.id}"><input maxlength="5000" required placeholder="返信する"><button class="soft">送信</button></form></article>`).join('')}

  async function renderMembers(){if(me.role!=='admin')return;const [members,names]=await Promise.all([api('/admin/members'),api('/ranking-names')]);const opts=names.map(name=>`<option value="${safe(name)}">${safe(name)}</option>`).join('');$('#memberList').innerHTML=members.map(m=>`<article class="card member-card"><div class="member-head"><div><strong>${safe(m.name)}</strong><div class="hint">${m.role==='admin'?'ADMIN':'MEMBER'} · Ranking: ${safe(m.ranking_name||m.name)}</div></div><span class="status-badge ${m.disabled?'danger-badge':'ok-badge'}">${m.disabled?'DISABLED':'ACTIVE'}</span></div><label>ランキング名<select data-ranking-name="${m.id}"><option value="${safe(m.ranking_name||m.name)}">${safe(m.ranking_name||m.name)}</option>${opts}</select></label><div class="button-row"><button class="soft" data-reset-pin="${m.id}">PINリセット</button>${m.role!=='admin'?`<button class="ghost" data-member-action="${m.disabled?'enable':'disable'}" data-member-id="${m.id}">${m.disabled?'利用再開':'一時停止'}</button>`:''}</div></article>`).join('')}

  function makeQuiz(){const pot=[40,60,80,100,120,150,200][Math.floor(Math.random()*7)],bet=[10,20,25,30,40,50,75][Math.floor(Math.random()*7)],correct=Math.round(bet/(pot+bet+bet)*100),set=new Set([correct]);while(set.size<4){const d=[-10,-7,-5,5,7,10][Math.floor(Math.random()*6)];set.add(Math.max(3,Math.min(60,correct+d)))}return{pot,bet,correct,choices:[...set].sort((a,b)=>a-b)}}
  function renderQuiz(){if(!quiz.q)quiz.q=makeQuiz();$('#quizStage').innerHTML=`<div class="hint">Pot ${quiz.q.pot} に相手が ${quiz.q.bet} bet</div><div class="pot-num">Call <b>${quiz.q.bet}</b></div><p>コールに必要な最低勝率は？</p>`;$('#quizChoices').innerHTML=quiz.choices??quiz.q.choices.map(x=>`<button data-quiz="${x}">${x}%</button>`).join('');$('#quizScore').textContent=`${quiz.score} / ${quiz.count}`}
  function answerQuiz(v){if(Number(v)===quiz.q.correct){quiz.score++;toast('Correct')}else toast(`正解 ${quiz.q.correct}%`);quiz.count++;if(quiz.count>=10){$('#quizStage').innerHTML=`<div class="pot-num">${quiz.score}/10</div><p>${quiz.score>=8?'Good pace.':'もう一周すると速くなります。'}</p>`;$('#quizChoices').innerHTML='';$('#quizScore').textContent=`${quiz.score} / 10`;return}quiz.q=makeQuiz();renderQuiz()}

  function onlineLedgerHTML(results){
    if(!results.length)return '<div class="empty">まだオンライン結果はありません</div>';
    const hands=[];const map=new Map();
    for(const r of results){if(!map.has(r.hand_id)){const h={id:r.hand_id,table_id:r.table_id,played_at:r.played_at,gross_pot_bb:r.gross_pot_bb,rake_bb:r.rake_bb,voided:Number(r.voided||0),void_reason:r.void_reason||'',players:[]};map.set(r.hand_id,h);hands.push(h)}map.get(r.hand_id).players.push(r)}
    return hands.slice(0,12).map(h=>`<article class="ledger-hand ${h.voided?'voided-result':''}"><div class="ledger-head"><div><strong>${safe(h.table_id==='jj-table-a'?'Table A':'Table B')}</strong><span>${dateFmt(h.played_at,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})} · Pot ${fmt(h.gross_pot_bb)}bb · Rake ${fmt(h.rake_bb)}bb</span></div>${h.voided?'<span class="status-badge off">VOID</span>':''}</div><div class="ledger-players">${h.players.map(r=>`<span>${safe(r.ranking_name)} <b class="${Number(r.result_bb)>=0?'positive':'negative'}">${Number(r.result_bb)>=0?'+':''}${fmt(r.result_bb)}bb</b> <em>${Number(r.points)>=0?'+':''}${fmt(r.points)}pt</em></span>`).join('')}</div>${h.void_reason?`<div class="hint">${safe(h.void_reason)}</div>`:''}${me.role==='admin'?`<button class="tiny ghost" data-void-hand="${safe(h.id)}" data-voided="${h.voided?'1':'0'}">${h.voided?'ランキングへ復帰':'結果を無効化'}</button>`:''}</article>`).join('');
  }

  async function renderLobby(){if(currentTableId)return;$('#lobbyPanel').classList.remove('hidden');$('#pokerRoom').classList.add('hidden');const [tables,results,summary]=await Promise.all([api('/tables'),api('/online/results?limit=72'),api('/online/summary')]);$('#tableCards').innerHTML=tables.map(t=>`<article class="lobby-card"><div class="eyebrow ${t.status==='playing'?'status-live':''}">${t.status==='playing'?'● HAND IN PROGRESS':'OPEN TABLE'}</div><h4>${safe(t.name)}</h4><div class="lobby-stats"><span>♟ ${t.players}/6</span><span>0.5 / 1 bb</span><span>150bb start</span></div><div class="rake-chip">RAKE 10% · ${fmt(t.rake_cap_bb)}bb CAP</div><p class="hint">空席を選ぶと150bbで着席。各ハンドのnet bbがランキングへ自動加算されます。</p><button class="primary full" data-open-table="${safe(t.id)}">テーブルを開く</button></article>`).join('')||'<div class="card empty">テーブルがありません</div>';$('#onlineResults').innerHTML=onlineLedgerHTML(results);$('#onlineSummary').innerHTML=`<div><span>Ranked hands</span><b>${fmt(summary.hands)}</b></div><div><span>Voided hands</span><b>${fmt(summary.voided_hands||0)}</b></div><div><span>Total rake</span><b>${fmt(summary.rake_bb)}bb</b></div><div><span>Gross pots</span><b>${fmt(summary.gross_pot_bb)}bb</b></div><div><span>Ranking rule</span><b>1bb = 3pt</b></div>`}
  async function openTable(id){currentTableId=id;$('#lobbyPanel').classList.add('hidden');$('#pokerRoom').classList.remove('hidden');await refreshMe();const data=await api('/tables/'+id);tableState=data.state;tableMessages=data.messages;renderPokerRoom();if(tableClock)clearInterval(tableClock);tableClock=setInterval(()=>{if(currentTableId&&tableState?.status==='playing')renderHandStatusOnly()},1000);await acquireWakeLock();connectTable(id)}
  function disconnectTable(){if(tableWS){tableWS.close();tableWS=null}if(tablePoll){clearInterval(tablePoll);tablePoll=null}if(tableHeartbeat){clearInterval(tableHeartbeat);tableHeartbeat=null}if(tableReconnect){clearTimeout(tableReconnect);tableReconnect=null}if(tableClock){clearInterval(tableClock);tableClock=null}releaseWakeLock();currentTableId=null;tableState=null;tableMessages=[];tableChatSig='';handLogSig='';wasMyTurn=false}
  function connectTable(id){if(tableHeartbeat){clearInterval(tableHeartbeat);tableHeartbeat=null}if(tableReconnect){clearTimeout(tableReconnect);tableReconnect=null}if(tableWS&&tableWS.readyState<2)tableWS.close();const proto=location.protocol==='https:'?'wss':'ws';tableWS=new WebSocket(`${proto}://${location.host}/ws/tables/${encodeURIComponent(id)}`);tableWS.onopen=()=>{if(tablePoll){clearInterval(tablePoll);tablePoll=null}tableHeartbeat=setInterval(()=>{if(tableWS?.readyState===WebSocket.OPEN)tableWS.send('ping')},15000)};tableWS.onmessage=e=>{try{const m=JSON.parse(e.data);if(m.type==='state'){tableState=m.state;tableMessages=m.messages||[];renderPokerRoom();refreshMe().catch(()=>{})}}catch{}};tableWS.onclose=()=>{if(tableHeartbeat){clearInterval(tableHeartbeat);tableHeartbeat=null}if(currentTableId===id&&!tablePoll)tablePoll=setInterval(async()=>{try{const d=await api('/tables/'+id);tableState=d.state;tableMessages=d.messages;renderPokerRoom()}catch{}},3000);if(currentTableId===id)tableReconnect=setTimeout(()=>connectTable(id),3000)}}
  function suitChar(c){return({c:'♣',d:'♦',h:'♥',s:'♠'})[c]||''}
  function cardHTML(c){if(!c||c==='??')return `<span class="card-face back">JJ</span>`;const r=c[0]==='T'?'10':c[0],s=suitChar(c[1]),red=['d','h'].includes(c[1]);return `<span class="card-face ${red?'red':''}">${r}${s}</span>`}
  function seatPosition(seat,max){const angle=(-90+seat*(360/max))*Math.PI/180;const rx=42,ry=39;return{left:50+Math.cos(angle)*rx,top:49+Math.sin(angle)*ry}}
  function totalPot(){return (tableState?.seats||[]).reduce((s,p)=>s+Number(p.contributed||0),0)}
  function renderHandStatusOnly(){if(!tableState)return;const phase=tableState.hand?.phase||'waiting',actionSeat=tableState.hand?.action_seat,acting=tableState.seats.find(p=>p.seat===actionSeat),deadline=tableState.hand?.action_deadline;let sec='';if(deadline){const left=Math.max(0,Math.ceil((new Date(deadline)-new Date())/1000));sec=` · ${left}s`}const el=$('#handStatus');if(el)el.textContent=tableState.status==='playing'?`${phase.toUpperCase()}${acting?' · '+acting.name+' to act':''}${sec}`:'開始待ち'}
  function renderPokerRoom(){if(!tableState)return;const myTurn=!!tableState.legal?.can_act;if(myTurn&&!wasMyTurn&&navigator.vibrate)navigator.vibrate(60);wasMyTurn=myTurn;$('#roomTitle').textContent=tableState.name;$('#roomMeta').textContent='6-max · 0.5/1bb · 150bb · rake 10% / 5bb cap';$('#boardCards').innerHTML=(tableState.hand?.board||[]).map(cardHTML).join('');const pot=totalPot(),estRake=Math.min(pot*0.10,Number(tableState.rake_cap||500));$('#potDisplay').textContent=`Pot ${bb(pot)} · rake ${bb(estRake)} max`;renderHandStatusOnly();$('#seatLayer').innerHTML=Array.from({length:6},(_,seat)=>renderSeat(seat)).join('');const result=tableState.last_result;$('#resultBanner').classList.toggle('hidden',!result||!(tableState.seats||[]).length);if(result){const mine=(result.net_results||[]).find(x=>x.user_id===me.id);$('#resultBanner').innerHTML=`<b>${safe(result.message)}</b>${mine?`<span>Your result: <strong class="${Number(mine.bb)>=0?'positive':'negative'}">${Number(mine.bb)>=0?'+':''}${fmt(mine.bb)}bb / ${Number(mine.bb)>=0?'+':''}${fmt(Number(mine.bb)*3)}pt</strong></span>`:''}`;}renderTableControls();renderActionBar();renderTableChat();renderHandLog()}
  function renderSeat(seat){const p=tableState.seats.find(x=>x.seat===seat),pos=seatPosition(seat,6),isAct=tableState.hand?.action_seat===seat,isButton=tableState.button_seat===seat;if(!p)return `<div class="seat seat-empty" style="left:${pos.left}%;top:${pos.top}%"><button class="soft" data-seat="${seat}">＋ Seat ${seat+1}</button></div>`;const hole=(p.cards||[]).map(cardHTML).join('');return `<div class="seat ${isAct?'active':''} ${p.busted?'busted':''}" style="left:${pos.left}%;top:${pos.top}%"><div class="seat-box">${isButton?'<span class="dealer">D</span>':''}<div class="hole">${hole}</div><div class="name">${safe(p.name)}${p.user_id===me.id?' · YOU':''}</div><div class="stack">${bb(p.stack)}${p.busted?' · BUSTED':''}</div><div class="bet">${p.round_bet?`Bet ${bb(p.round_bet)}`:''}${p.folded?' FOLDED':''}${p.all_in?' ALL-IN':''}</div></div></div>`}
  function renderTableControls(){const seated=tableState.seats.find(p=>p.user_id===me.id),canStart=tableState.status!=='playing'&&tableState.seats.filter(p=>p.stack>0).length>=2&&!!seated&&seated.stack>0;$('#tableControls').innerHTML=`${canStart?'<button class="primary" id="startHandBtn">Deal / Start Hand</button>':''}${seated&&seated.stack<=0&&tableState.status!=='playing'?'<button class="primary" id="rebuyBtn">150bbでリバイ</button>':''}${seated&&tableState.status!=='playing'?'<button class="ghost" id="leaveSeatBtn">テーブルから退席</button>':''}${!seated?'<span class="hint">空席をクリックして150bbで着席してください</span>':''}${seated&&seated.stack<=0?'<span class="bust-note">0bbです。次のハンドには参加できません。リバイ（150bb）またはテーブルから退席を選んでください。</span>':''}`}
  function renderActionBar(){const l=tableState.legal||{can_act:false};if(!l.can_act){$('#actionBar').innerHTML='<span class="hint">あなたのアクションを待っていません</span>';return}const callLabel=l.can_check?'Check':`Call ${bb(l.call_amount)}`;let raise='';if(l.can_raise&&l.max_raise_to>0){const min=l.min_raise_to||l.max_raise_to,max=l.max_raise_to;raise=`<input id="raiseTo" type="number" step="0.5" min="${Number(min)/tableState.big_blind}" max="${Number(max)/tableState.big_blind}" value="${Number(min)/tableState.big_blind}"><button class="soft" data-action="raise">Raise to (bb)</button>`}$('#actionBar').innerHTML=`<button class="danger" data-action="fold">Fold</button><button class="primary" data-action="${l.can_check?'check':'call'}">${callLabel}</button>${raise}${l.can_all_in?`<button class="soft" data-action="allin">All-in ${bb(l.max_raise_to)}</button>`:''}`}
  function renderTableChat(){const sig=tableMessages.map(m=>`${m.id||''}:${m.created_at||''}:${m.body||''}`).join('|');if(sig===tableChatSig)return;tableChatSig=sig;const el=$('#tableMessages');el.innerHTML=tableMessages.map(m=>`<div class="chat-message"><b>${safe(m.author_name)}</b> ${safe(m.body)}<time>${dateFmt(m.created_at,{hour:'2-digit',minute:'2-digit'})}</time></div>`).join('');el.scrollTop=el.scrollHeight}
  function renderHandLog(){const logs=tableState.hand?.log||[],sig=logs.join('|');if(sig===handLogSig)return;handLogSig=sig;$('#handLog').innerHTML=[...logs].reverse().map(x=>`<div>${safe(x)}</div>`).join('')||'<div>まだハンド履歴はありません</div>'}

  function openModal(html){$('#modalBody').innerHTML=html;$('#modal').showModal()}
  function closeModal(){$('#modal').close()}

  function bind(){
    $('#pinForm').addEventListener('submit',async e=>{e.preventDefault();try{const d=await post('/auth/pin',{name:$('#loginName').value,pin:$('#loginPin').value});me=d.user;$('#loginPin').value='';showApp();await refreshAll();toast(d.created?'アカウントを作成しました':'ログインしました')}catch(err){toast(err.message)}});
    $('#logoutBtn').addEventListener('click',()=>logout(true));$('#headerLogoutBtn').addEventListener('click',()=>logout(true));$('#accountBtn').addEventListener('click',()=>openModal(`<h3>アカウント設定</h3><p class="hint">${safe(me.name)} · Ranking: ${safe(me.ranking_name||me.name)}</p><form id="pinChangeForm" class="stack"><label>現在の6桁PIN<input name="current_pin" type="password" inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" required></label><label>新しい6桁PIN<input name="new_pin" type="password" inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" required></label><button class="primary">PINを変更</button></form>`));$$('.nav').forEach(b=>b.addEventListener('click',()=>switchView(b.dataset.view)));document.addEventListener('click',async e=>{const j=e.target.closest('[data-jump]');if(j)return switchView(j.dataset.jump);const rt=e.target.closest('[data-rank-mode]');if(rt){rankMode=rt.dataset.rankMode;return renderRanking().catch(x=>toast(x.message))}const op=e.target.closest('[data-open-table]');if(op)return openTable(op.dataset.openTable).catch(x=>toast(x.message));const st=e.target.closest('[data-seat]');if(st)return seatClick(Number(st.dataset.seat));const act=e.target.closest('[data-action]');if(act)return doAction(act.dataset.action);const q=e.target.closest('[data-quiz]');if(q)return answerQuiz(q.dataset.quiz);const ma=e.target.closest('[data-member-action]');if(ma){try{const id=Number(ma.dataset.memberId),act=ma.dataset.memberAction;await patch(`/admin/members/${id}`,act==='disable'?{disabled:true}:{disabled:false});toast('ユーザー設定を更新しました');return renderMembers()}catch(err){return toast(err.message)}}const rp=e.target.closest('[data-reset-pin]');if(rp){const pin=prompt('新しい6桁PINを入力してください');if(!pin)return;if(!/^\d{6}$/.test(pin))return toast('PINは6桁の数字で入力してください');try{await post(`/admin/members/${rp.dataset.resetPin}/reset-pin`,{pin});toast('PINをリセットしました');return}catch(err){return toast(err.message)}}const vh=e.target.closest('[data-void-hand]');if(vh){try{const was=vh.dataset.voided==='1',reason=was?'':(prompt('無効化理由（ランキング監査ログに残ります）','誤操作・不正対戦等')||'管理者による無効化');await patch(`/admin/online-hands/${encodeURIComponent(vh.dataset.voidHand)}/void`,{voided:!was,reason});toast(was?'ランキングへ復帰しました':'オンライン結果をランキングから除外しました');return renderLobby()}catch(err){return toast(err.message)}}});
    $('#rankMonth').addEventListener('change',()=>rankMode==='month'&&renderRanking());$('#rankSearch').addEventListener('input',()=>renderRanking());$('#memberList').addEventListener('change',async e=>{const sel=e.target.closest('[data-ranking-name]');if(!sel)return;try{await patch(`/admin/members/${sel.dataset.rankingName}`,{ranking_name:sel.value});toast('ランキング名を更新しました')}catch(err){toast(err.message)}});$('#pointGame').addEventListener('change',setPointInitialOptions);['pointInitial','pointReentries'].forEach(id=>$('#'+id).addEventListener('input',pointCalc));$$('.point-chip-count').forEach(inp=>inp.addEventListener('input',pointCalc));setPointInitialOptions();
    $('#pointForm').addEventListener('submit',async e=>{e.preventDefault();try{const payload={name:$('#pointName').value.trim(),date:$('#pointDate').value,reentries:chipCount($('#pointReentries').value),initial:Number($('#pointInitial').value),game_type:$('#pointGame').value};pointDenoms.forEach(d=>payload[`chip_${d}`]=chipCount($(`#pointChip${d}`).value));const result=await post('/entries',payload);toast(`公式ポイントを記録しました（残り ${fmt(result.remaining)} / ${result.points>=0?'+':''}${fmt(result.points)}pt）`);$$('.point-chip-count').forEach(inp=>inp.value='');$('#pointReentries').value='0';$('#pointDate').value=isoLocal();pointCalc();await renderPoints()}catch(err){toast(err.message)}});
    $('#addScheduleBtn').addEventListener('click',()=>openModal(`<h3>活動予定を追加</h3><form id="scheduleForm" class="stack"><label>日付<input name="date" type="date" required></label><label>時間<input name="time" type="time" required></label><label>教室<input name="room" required placeholder="17403"></label><label>タイトル<input name="title" value="JJ活動" required></label><label>メモ<textarea name="note" rows="3"></textarea></label><button class="primary">追加</button></form>`));
    $('#addNewsBtn').addEventListener('click',()=>openModal(`<h3>お知らせを投稿</h3><form id="newsForm" class="stack"><label>種類<select name="kind"><option value="club">JJ</option><option value="external">外部イベント</option></select></label><label>日付<input name="date" type="date" value="${new Date().toISOString().slice(0,10)}" required></label><label>タイトル<input name="title" required></label><label>本文<textarea name="body" rows="5" required></textarea></label><label>URL<input name="url" type="url" placeholder="https://"></label><button class="primary">投稿</button></form>`));
    $('#newThreadBtn').addEventListener('click',()=>openModal(`<h3>新しい戦略議論</h3><form id="threadForm" class="stack"><label>タイトル<input name="title" required></label><label>本文<textarea name="body" rows="7" required placeholder="Stack / Position / Action / Board / 自分の考え"></textarea></label><button class="primary">投稿</button></form>`));
    $('#backLobby').addEventListener('click',()=>{disconnectTable();$('#lobbyPanel').classList.remove('hidden');$('#pokerRoom').classList.add('hidden');renderLobby()});
    $('#tableControls').addEventListener('click',async e=>{if(e.target.id==='startHandBtn'){try{await post(`/tables/${currentTableId}/start`);toast('Hand started')}catch(err){toast(err.message)}}if(e.target.id==='rebuyBtn'){try{await post(`/tables/${currentTableId}/rebuy`);toast('150bbでリバイしました')}catch(err){toast(err.message)}}if(e.target.id==='leaveSeatBtn'){try{await post(`/tables/${currentTableId}/leave`);const d=await api('/tables/'+currentTableId);tableState=d.state;tableMessages=d.messages||[];renderPokerRoom();await refreshMe();toast('テーブルから退席しました')}catch(err){toast(err.message)}}});
    $('#tableChatForm').addEventListener('submit',async e=>{e.preventDefault();const inp=$('#tableChatInput'),body=inp.value.trim();if(!body||!currentTableId)return;inp.value='';try{await post(`/tables/${currentTableId}/chat`,{body})}catch(err){toast(err.message)}});
    $$('[data-side-tab]').forEach(b=>b.addEventListener('click',()=>{$$('[data-side-tab]').forEach(x=>x.classList.toggle('active',x===b));$('#tableChatPanel').classList.toggle('hidden',b.dataset.sideTab!=='chat');$('#handLogPanel').classList.toggle('hidden',b.dataset.sideTab!=='log')}));
    $('#restartQuiz').addEventListener('click',()=>{quiz={count:0,score:0,q:makeQuiz()};renderQuiz()});$('#modalClose').addEventListener('click',closeModal);$('#modal').addEventListener('click',e=>{if(e.target===$('#modal'))closeModal()});
    $('#modalBody').addEventListener('submit',async e=>{e.preventDefault();const fd=new FormData(e.target);try{if(e.target.id==='scheduleForm'){await post('/schedules',Object.fromEntries(fd));closeModal();toast('予定を追加しました');return renderSchedules()}if(e.target.id==='newsForm'){await post('/announcements',Object.fromEntries(fd));closeModal();toast('投稿しました');return renderNews()}if(e.target.id==='threadForm'){await post('/threads',Object.fromEntries(fd));closeModal();toast('議論を開始しました');return renderThreads()}if(e.target.id==='seatForm'){const o=Object.fromEntries(fd);await post(`/tables/${currentTableId}/seat`,{seat:Number(o.seat)});closeModal();toast('150bbで着席しました');return}if(e.target.id==='pinChangeForm'){await post('/auth/change-pin',Object.fromEntries(fd));closeModal();toast('PINを変更しました')}}catch(err){toast(err.message)}});
    $('#threads').addEventListener('submit',async e=>{const f=e.target.closest('.reply-form');if(!f)return;e.preventDefault();const inp=$('input',f);try{await post(`/threads/${f.dataset.thread}/replies`,{body:inp.value.trim()});inp.value='';renderThreads()}catch(err){toast(err.message)}})
  }
  async function seatClick(seat){if(!currentTableId||tableState.status==='playing')return toast('ハンド中は着席できません');if(tableState.seats.some(p=>p.user_id===me.id))return toast('すでに着席しています');openModal(`<h3>Seat ${seat+1} に着席</h3><p class="hint">6-max · 0.5/1bb · 150bb start</p><form id="seatForm" class="stack"><input type="hidden" name="seat" value="${seat}"><button class="primary">150bbで着席する</button></form>`)}
  async function doAction(action){if(!currentTableId||actionBusy)return;actionBusy=true;$$('#actionBar button').forEach(b=>b.disabled=true);const body={action};if(action==='raise')body.amount=Math.round(Number($('#raiseTo')?.value||0)*Number(tableState.big_blind||100));try{const next=await post(`/tables/${currentTableId}/action`,body);tableState=next;renderPokerRoom()}catch(err){toast(err.message)}finally{actionBusy=false}}

  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&currentTableId)acquireWakeLock()});
  init();
  if('serviceWorker' in navigator && location.protocol.startsWith('http')) navigator.serviceWorker.register('/static/sw.js').catch(()=>{});


  // Japanese article fallbacks are embedded from the server's verified list.
  // Both study surfaces stay Japanese even when the API is unavailable.
  const jjJapaneseArticleFallback=[{"title": "リンプポットをどうプレイするか", "url": "https://japan.gtowizard.com/blog/is-limping-pimping/", "source": "GTO Wizard Japan", "language": "ja", "published_at": "2026-08-22T00:00:00+09:00", "topic": "エクスプロイト / 理論", "summary": "日本語で読めるGTO Wizard公式記事。リンプポットへの対応をスタック別に整理します。"}, {"title": "バブルとFTバブルの違い", "url": "https://japan.gtowizard.com/blog/money-bubble-vs-final-table-bubble/", "source": "GTO Wizard Japan", "language": "ja", "published_at": "2026-08-09T00:00:00+09:00", "topic": "ICM / トーナメント", "summary": "バブルとファイナルテーブル・バブルで戦略がどう変わるかを扱う日本語記事です。"}, {"title": "なぜ自分のソリューションはGTO Wizardと違うのか？", "url": "https://japan.gtowizard.com/blog/why-doesnt-my-solution-match-gto-wizard/", "source": "GTO Wizard Japan", "language": "ja", "published_at": "2026-08-09T00:00:00+09:00", "topic": "GTO / ソルバー", "summary": "ソルバー間の差や入力条件による解の変化を理解するための日本語記事です。"}, {"title": "GTO Wizardになる方法", "url": "https://japan.gtowizard.com/blog/how-to-become-a-gto-wizard/", "source": "GTO Wizard Japan", "language": "ja", "published_at": "2023-12-01T00:00:00+09:00", "topic": "学習法", "summary": "GTO学習を体系的に進めるための公式ガイドです。"}];
  function jjStudyJapaneseText(value){
    const text=String(value||'').normalize('NFKC'),letters=text.match(/\p{L}/gu)||[],japanese=text.match(/[ぁ-んァ-ヶ一-龠々]/g)||[];
    return /[ぁ-んァ-ヶ]/.test(text)&&japanese.length>=2&&japanese.length/Math.max(1,letters.length)>=0.3;
  }
  function jjJapaneseStudyArticles(items){
    const seen=new Set();
    return (Array.isArray(items)?items:[]).filter(item=>{
      if(!item||!/^ja(?:[-_]jp)?$/i.test(String(item.language||''))||!jjStudyJapaneseText(item.title)||(item.summary&&!jjStudyJapaneseText(item.summary)))return false;
      try{
        const url=new URL(item.url);
        const path=decodeURIComponent(url.pathname),parts=path.replace(/^\/+|\/+$/g,'').split('/');
        if(url.protocol!=='https:'||url.hostname!=='japan.gtowizard.com'||url.port||url.username||url.password||!path.startsWith('/blog/')||parts.length!==2||['','.','..','news','videos'].includes(parts[1].toLowerCase())||path.includes('\\')||url.search)return false;
        url.hash='';
        if(seen.has(url.href))return false;
        seen.add(url.href);
        return true;
      }catch{return false}
    }).map(item=>({...item,source:'GTO Wizard Japan',summary:jjStudyJapaneseText(item.summary)?item.summary:''}));
  }
  function studyWeekSeed(){
    const now=new Date(),d=new Date(now.getFullYear(),now.getMonth(),now.getDate());
    const day=(d.getDay()+6)%7; d.setDate(d.getDate()-day);
    return Number(`${d.getFullYear()}${String(d.getMonth()+1).padStart(2,'0')}${String(d.getDate()).padStart(2,'0')}`);
  }
  function studyIndex(length){let x=(studyWeekSeed()^0x43a5f17)>>>0;x^=x<<13;x^=x>>>17;x^=x<<5;return Math.abs(x>>>0)%length}
  function studyCard(a,compact=false){return `<article class="study-card ${compact?'compact':''}"><div class="study-card-top"><span class="study-kind">日本語記事</span><span class="study-time">${safe(a.topic||'ポーカー学習')}</span></div><h4>${safe(a.title)}</h4><p>${safe(a.summary)}</p><div class="study-meta"><span>GTO Wizard Japan · ${safe(String(a.published_at||'').slice(0,10))}</span><a href="${safe(a.url)}" target="_blank" rel="noopener noreferrer">日本語で読む <b>↗</b></a></div></article>`}
  function renderWeeklyStudy(){
    const articles=jjJapaneseStudyArticles(jjJapaneseArticleFallback);
    const offset=articles.length?studyIndex(articles.length):0;
    const selected=articles.slice(offset).concat(articles.slice(0,offset)).slice(0,2);
    const cards=compact=>selected.map(a=>studyCard(a,compact)).join('')||'<div class="empty">共有できる日本語記事がありません</div>';
    const home=$('#homeView');
    if(home&&!$('#weeklyStudyHome')){
      const block=document.createElement('section');block.id='weeklyStudyHome';block.className='weekly-study weekly-study-home';
      block.innerHTML=`<div class="study-head"><div><div class="eyebrow">WEEKLY STUDY</div><h3>今週の日本語記事</h3><p>公開日にかかわらず、日本語で読める記事から毎週選んでいます。</p></div><button class="soft" data-jump="lab">Poker Labで見る</button></div><div class="study-grid">${cards(true)}</div>`;
      const anchor=home.querySelector('.home-columns');if(anchor)anchor.insertAdjacentElement('beforebegin',block);else home.appendChild(block);
    }
    const lab=$('#labView');
    if(lab&&!$('#weeklyStudyLab')){
      const block=document.createElement('section');block.id='weeklyStudyLab';block.className='weekly-study weekly-study-lab card';
      block.innerHTML=`<div class="study-head"><div><div class="eyebrow">CURATED BY JJ · EXTERNAL</div><h3>今週のGTO Wizard Japan</h3><p>日本語記事への入口を紹介します。本文の転載はしていません。</p></div><a class="study-all" href="https://japan.gtowizard.com/blog/" target="_blank" rel="noopener noreferrer">日本語の記事一覧 ↗</a></div><div class="study-grid">${cards(false)}</div><div class="study-foot">GTO Wizard Japanの外部記事を紹介する非提携の学習リンクです。JJ Arenaのポイントやオンライン対戦結果には影響しません。</div>`;
      const first=lab.firstElementChild;if(first)first.insertAdjacentElement('beforebegin',block);else lab.appendChild(block);
    }
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',renderWeeklyStudy,{once:true});else renderWeeklyStudy();


  // v1.10 mobile-first operations. Desktop layout remains unchanged.
  const mobileBreakpoint=760;
  const quickPointDenoms=[1,5,10,25,100,500];
  const quickPointInitials={
    ring:[{value:450,label:'450 · 1-3-3'},{value:900,label:'900 · 2-5-5'},{value:2000,label:'2000 · 5-10-10'}],
    tournament:[{value:300,label:'300 · Tournament'},{value:400,label:'400 · Tournament'},{value:500,label:'500 · Tournament'},{value:600,label:'600 · Tournament'},{value:800,label:'800 · Tournament'},{value:1000,label:'1000 · Tournament'}]
  };
  const isMobileUX=()=>window.matchMedia(`(max-width:${mobileBreakpoint}px)`).matches;

  function mobileScrollTop(){
    if(!isMobileUX())return;
    try{window.scrollTo({top:0,left:0,behavior:'instant'})}catch{window.scrollTo(0,0)}
    const main=$('.main');if(main&&main.scrollTop)main.scrollTop=0;
  }

  function quickCount(v){const n=Number(v||0);return Number.isFinite(n)&&n>=0?Math.floor(n):0}
  function quickPointSetInitials(){
    const game=$('#quickPointGame')?.value||'ring',sel=$('#quickPointInitial');if(!sel)return;
    const opts=quickPointInitials[game]||quickPointInitials.ring,old=Number(sel.value||0);
    sel.innerHTML=opts.map(o=>`<option value="${o.value}">${o.label}</option>`).join('');
    sel.value=String(opts.some(o=>o.value===old)?old:opts[0].value);quickPointCalc();
  }
  function quickPointCalc(){
    const initial=Number($('#quickPointInitial')?.value||0),re=quickCount($('#quickPointReentries')?.value);
    const remaining=quickPointDenoms.reduce((sum,d)=>sum+d*quickCount($(`#quickPointChip${d}`)?.value),0);
    const points=remaining-(re+1)*initial;
    if($('#quickPointRemaining'))$('#quickPointRemaining').textContent=fmt(remaining);
    if($('#quickPointPreview'))$('#quickPointPreview').textContent=`${points>=0?'+':''}${fmt(points)} pt`;
    return {remaining,points};
  }
  async function quickPointLoadNames(){
    const dl=$('#quickPlayerNames');if(!dl||dl.dataset.loaded==='1')return;
    try{const names=await api('/ranking-names');dl.innerHTML=names.map(name=>`<option value="${safe(name)}"></option>`).join('');dl.dataset.loaded='1'}catch{}
  }
  function quickPointCard(){
    const card=document.createElement('section');card.id='mobileQuickPointCard';card.className='mobile-quick-point card';
    card.innerHTML=`<div class="mobile-section-title"><div><div class="eyebrow">QUICK ENTRY</div><h3>ポイント入力</h3></div><span>ADMIN</span></div>
      <form id="quickPointForm" class="quick-point-form">
        <label class="quick-player">プレイヤー<input id="quickPointName" required list="quickPlayerNames" autocomplete="off" placeholder="名前"></label><datalist id="quickPlayerNames"></datalist>
        <label>ゲーム<select id="quickPointGame"><option value="ring">リング</option><option value="tournament">トーナメント</option></select></label>
        <label>初期点<select id="quickPointInitial"></select></label>
        <label>リエントリー<input id="quickPointReentries" type="number" inputmode="numeric" min="0" step="1" value="0"></label>
        <label class="quick-date">日時<input id="quickPointDate" type="datetime-local" min="2026-09-01T00:00" max="2027-03-31T23:59" required></label>
        <div class="quick-chip-block"><div class="quick-chip-head"><strong>残りチップ</strong><span>空欄 = 0枚</span></div><div class="quick-chip-grid">${quickPointDenoms.map(d=>`<label><span>${d}点</span><input id="quickPointChip${d}" type="number" inputmode="numeric" min="0" step="1" placeholder="0"></label>`).join('')}</div></div>
        <div class="quick-point-total"><span>残り <b id="quickPointRemaining">0</b></span><strong id="quickPointPreview">0 pt</strong></div>
        <button class="primary quick-submit">この結果を記録</button>
      </form>`;
    return card;
  }
  function ensureQuickPointHome(){
    const home=$('#homeView');if(!home)return;
    const existing=$('#mobileQuickPointCard');
    if(me?.role!=='admin'){if(existing)existing.remove();return}
    if(existing)return;
    const card=quickPointCard();
    const hero=home.querySelector('.hero-grid');if(hero)hero.insertAdjacentElement('beforebegin',card);else home.prepend(card);
    $('#quickPointName').value=me?.ranking_name||me?.name||'';$('#quickPointDate').value=isoLocal();quickPointSetInitials();quickPointLoadNames();
    $('#quickPointGame').addEventListener('change',quickPointSetInitials);
    $('#quickPointInitial').addEventListener('change',quickPointCalc);$('#quickPointReentries').addEventListener('input',quickPointCalc);
    quickPointDenoms.forEach(d=>$(`#quickPointChip${d}`).addEventListener('input',quickPointCalc));
    $('#quickPointName').addEventListener('focus',quickPointLoadNames,{once:true});
    $('#quickPointForm').addEventListener('submit',async e=>{e.preventDefault();const btn=e.submitter;try{
      if(btn){btn.disabled=true;btn.textContent='記録中…'}
      const payload={name:$('#quickPointName').value.trim(),date:$('#quickPointDate').value,reentries:quickCount($('#quickPointReentries').value),initial:Number($('#quickPointInitial').value),game_type:$('#quickPointGame').value};
      quickPointDenoms.forEach(d=>payload[`chip_${d}`]=quickCount($(`#quickPointChip${d}`).value));
      const result=await post('/entries',payload);toast(`記録しました · ${result.points>=0?'+':''}${fmt(result.points)}pt`);
      quickPointDenoms.forEach(d=>$(`#quickPointChip${d}`).value='');$('#quickPointReentries').value='0';$('#quickPointDate').value=isoLocal();quickPointCalc();
      await renderHome();
    }catch(err){toast(err.message)}finally{if(btn){btn.disabled=false;btn.textContent='この結果を記録'}}});
  }

  function ensureDesktopPointShortcut(){
    const row=$('#homeView .hero .button-row');if(!row||$('#homePointShortcut'))return;
    const b=document.createElement('button');b.id='homePointShortcut';b.className='soft admin-home-point';b.dataset.jump='points';b.textContent='＋ ポイント入力';row.appendChild(b);
  }

  function mobileNavIcon(view){return ({home:'⌂',ranking:'♛',points:'＋',tables:'♠',more:'•••'})[view]||'•'}
  function ensureMobileDock(){
    if($('#mobileDock'))return;
    const dock=document.createElement('nav');dock.id='mobileDock';dock.className='mobile-only mobile-dock';dock.setAttribute('aria-label','スマートフォン用ナビゲーション');
    dock.innerHTML=`<button data-mobile-view="home"><b>${mobileNavIcon('home')}</b><span>ホーム</span></button><button data-mobile-view="ranking"><b>${mobileNavIcon('ranking')}</b><span>順位</span></button><button id="mobilePointNav" class="mobile-point-nav" data-mobile-view="points"><b>${mobileNavIcon('points')}</b><span>入力</span></button><button data-mobile-view="tables"><b>${mobileNavIcon('tables')}</b><span>卓</span></button><button data-mobile-more><b>${mobileNavIcon('more')}</b><span>その他</span></button>`;
    document.body.appendChild(dock);
    dock.addEventListener('click',e=>{const v=e.target.closest('[data-mobile-view]')?.dataset.mobileView;if(v){switchView(v);syncMobileNavigation();closeMobileMore();mobileScrollTop();return}if(e.target.closest('[data-mobile-more]'))openMobileMore()});
  }
  function ensureMobileMore(){
    if($('#mobileMore'))return;
    const overlay=document.createElement('div');overlay.id='mobileMore';overlay.className='mobile-only mobile-more hidden';overlay.innerHTML='<div class="mobile-more-backdrop" data-close-mobile-more></div><section class="mobile-more-sheet" role="dialog" aria-modal="true" aria-label="その他のメニュー"><div class="sheet-grab"></div><div class="mobile-more-head"><div><div class="eyebrow">MENU</div><h3>その他</h3></div><button class="sheet-close" data-close-mobile-more aria-label="閉じる">×</button></div><div id="mobileMoreLinks" class="mobile-more-links"></div></section>';
    document.body.appendChild(overlay);overlay.addEventListener('click',e=>{if(e.target.closest('[data-close-mobile-more]'))closeMobileMore();const b=e.target.closest('[data-more-view]');if(b){switchView(b.dataset.moreView);syncMobileNavigation();closeMobileMore();mobileScrollTop()}});
  }
  function rebuildMobileMore(){
    ensureMobileMore();const box=$('#mobileMoreLinks');if(!box)return;
    const skip=new Set(['home','ranking','tables','points']);
    const items=[...$$('.sidebar .nav')].filter(n=>n.dataset.view&&!skip.has(n.dataset.view)&&!n.classList.contains('hidden'));
    box.innerHTML=items.map(n=>`<button data-more-view="${safe(n.dataset.view)}"><span>${safe(n.textContent.trim())}</span><b>›</b></button>`).join('')+`<button data-mobile-logout class="danger-link"><span>ログアウト</span><b>›</b></button>`;
    const out=$('[data-mobile-logout]');if(out)out.onclick=()=>{closeMobileMore();logout(true)};
  }
  function openMobileMore(){rebuildMobileMore();$('#mobileMore')?.classList.remove('hidden');document.body.classList.add('mobile-sheet-open')}
  function closeMobileMore(){$('#mobileMore')?.classList.add('hidden');document.body.classList.remove('mobile-sheet-open')}
  function syncMobileNavigation(){
    ensureMobileDock();ensureMobileMore();
    const point=$('#mobilePointNav');if(point)point.classList.toggle('hidden',me?.role!=='admin');
    $$('#mobileDock [data-mobile-view]').forEach(b=>{const on=b.dataset.mobileView===currentView;b.classList.toggle('active',on);b.toggleAttribute('aria-current',on)});
    if(me?.role==='admin'){ensureQuickPointHome();ensureDesktopPointShortcut()}else{$('#mobileQuickPointCard')?.remove();$('#homePointShortcut')?.remove()}
  }

  // A view change on a phone always starts at the top. This intentionally does not preserve per-view scroll.
  document.addEventListener('click',e=>{if(!isMobileUX())return;if(e.target.closest('[data-view],[data-jump],[data-mobile-view],[data-more-view]'))requestAnimationFrame(mobileScrollTop)},true);
  const activeViewObserver=new MutationObserver(muts=>{if(!isMobileUX())return;if(muts.some(m=>m.type==='attributes'&&m.attributeName==='class'&&m.target.classList?.contains('view')))requestAnimationFrame(mobileScrollTop)});

  function initMobileOperations(){
    ensureMobileDock();ensureMobileMore();syncMobileNavigation();
    const app=$('#appView');if(app)activeViewObserver.observe(app,{subtree:true,attributes:true,attributeFilter:['class']});
    const roleObserver=new MutationObserver(()=>syncMobileNavigation());if(app)roleObserver.observe(app,{attributes:true,attributeFilter:['class']});
    window.addEventListener('resize',()=>{syncMobileNavigation();if(!isMobileUX())closeMobileMore()},{passive:true});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',initMobileOperations,{once:true});else initMobileOperations();


  // v1.13 optional member profiles. Everything is voluntary and member-only.
  let profileDraftAvatar='';
  const profileInitials=name=>(String(name||'?').trim().slice(0,2)||'?');
  function profileAvatarHtml(p,cls='profile-avatar'){
    return p?.avatar_data?`<img class="${cls}" src="${safe(p.avatar_data)}" alt="${safe(p.name||'プロフィール')}のアイコン">`:`<div class="${cls} profile-avatar-fallback">${safe(profileInitials(p?.name))}</div>`;
  }
  function profileMeta(p){
    const school=[p.grade,p.faculty,p.department].filter(Boolean).join(' · '),items=[];
    if(school)items.push(`<span>🎓 ${safe(school)}</span>`);if(p.hometown)items.push(`<span>⌂ ${safe(p.hometown)}</span>`);if(p.hobbies)items.push(`<span>♧ ${safe(p.hobbies)}</span>`);
    return items.join('');
  }
  async function profileImageData(file){
    if(!file)return '';
    if(!/^image\/(jpeg|png|webp)$/.test(file.type))throw new Error('JPEG / PNG / WebP画像を選んでください');
    if(file.size>8*1024*1024)throw new Error('元画像は8MB以下にしてください');
    const url=URL.createObjectURL(file);
    try{
      const img=await new Promise((resolve,reject)=>{const i=new Image();i.onload=()=>resolve(i);i.onerror=()=>reject(new Error('画像を読み込めません'));i.src=url});
      const size=160,canvas=document.createElement('canvas');canvas.width=size;canvas.height=size;const ctx=canvas.getContext('2d',{alpha:false});
      const scale=Math.max(size/img.naturalWidth,size/img.naturalHeight),w=img.naturalWidth*scale,h=img.naturalHeight*scale;
      ctx.fillStyle='#f4f7f5';ctx.fillRect(0,0,size,size);ctx.drawImage(img,(size-w)/2,(size-h)/2,w,h);
      let data=canvas.toDataURL('image/webp',.78);if(!data.startsWith('data:image/webp'))data=canvas.toDataURL('image/jpeg',.78);
      if(data.length>145000){data=canvas.toDataURL('image/jpeg',.62)}
      if(data.length>145000)throw new Error('画像を十分に圧縮できません。別の画像を選んでください');
      return data;
    }finally{URL.revokeObjectURL(url)}
  }
  function profileSettingsHtml(p){
    profileDraftAvatar=p.avatar_data||'';
    return `<div class="profile-settings-shell"><div class="profile-settings-head">${profileAvatarHtml(p,'profile-avatar profile-avatar-xl')}<div><div class="eyebrow">MEMBER PROFILE</div><h3>アカウント設定</h3><p class="hint">プロフィールはすべて任意です。ログイン済みのJJメンバーにだけ公開されます。</p></div></div>
      <form id="profileForm" class="profile-form stack">
        <div class="profile-avatar-actions"><label class="soft profile-upload">アイコンを選ぶ<input id="profileAvatarInput" type="file" accept="image/jpeg,image/png,image/webp" hidden></label><button type="button" class="ghost" id="profileAvatarRemove">アイコンを削除</button></div>
        <div class="profile-school-grid"><label>学年<input name="grade" maxlength="20" value="${safe(p.grade||'')}" placeholder="例：3年"></label><label>学部<input name="faculty" maxlength="80" value="${safe(p.faculty||'')}" placeholder="例：文学部"></label><label>学科<input name="department" maxlength="80" value="${safe(p.department||'')}" placeholder="例：英米文学科"></label></div>
        <label>出身<input name="hometown" maxlength="80" value="${safe(p.hometown||'')}" placeholder="例：大阪 / 兵庫県"></label>
        <label>趣味<input name="hobbies" maxlength="250" value="${safe(p.hobbies||'')}" placeholder="ポーカー、映画、旅行 など"></label>
        <label>自己紹介<textarea name="bio" maxlength="600" rows="4" placeholder="自由に記入できます">${safe(p.bio||'')}</textarea></label>
        <label class="profile-visibility"><span><b>プロフィールをメンバーに公開</b><small>OFFの場合、名前以外のプロフィール詳細は表示されません。</small></span><input name="visible" type="checkbox" ${p.visible?'checked':''}></label>
        <button class="primary full">プロフィールを保存</button>
      </form>
      <div class="profile-settings-divider"></div>
      <section class="jj-account-security"><div><div class="eyebrow">SECURITY</div><h4>ログインPIN</h4><p class="hint">ログインに使う6桁PINは、本人だけが現在のPINを使って変更できます。変更後は他端末のログインを解除します。</p></div><button class="primary" type="button" id="openPinSettings">PINを変更</button></section>
      <div class="profile-settings-actions"><button class="soft" type="button" id="openMemberDirectory">メンバー一覧を見る</button></div></div>`;
  }
  async function openProfileSettings(){
    try{const p=await api('/profile/me');openModal(profileSettingsHtml(p));setTimeout(()=>$('#profileAvatarInput')?.focus?.(),0)}catch(err){toast(err.message)}
  }
  async function openMemberDirectory(){
    try{const list=await api('/profiles');openModal(`<div class="member-directory-head"><div><div class="eyebrow">JJ MEMBERS</div><h3>メンバー</h3><p class="hint">プロフィール設定は任意です。非公開の人は詳細を表示しません。</p></div><button class="soft" type="button" id="editMyProfileFromDirectory">自分を編集</button></div><div class="profile-directory">${list.map(p=>`<article class="profile-card ${p.visible?'':'profile-private'}"><div class="profile-card-head">${profileAvatarHtml(p)}<div><strong>${safe(p.ranking_name||p.name)}</strong><small>${p.role==='admin'?'ADMIN':'MEMBER'}${p.visible?'':' · 非公開'}</small></div></div>${p.visible?`<div class="profile-card-meta">${profileMeta(p)}</div>${p.bio?`<p>${safe(p.bio)}</p>`:''}`:'<p class="hint">プロフィールは非公開です。</p>'}</article>`).join('')}</div>`)}catch(err){toast(err.message)}
  }
  function openPinSettings(){
    openModal(`<div class="jj-pin-change-shell"><div class="eyebrow">LOGIN SECURITY</div><h3>6桁PINを変更</h3><p class="hint">現在のPINを確認したうえで、新しいPINへ変更します。管理者を含め、現在のPINそのものを画面から読み出すことはできません。</p><form id="pinChangeConfirmForm" class="stack" autocomplete="off"><label>現在の6桁PIN<input name="current_pin" type="password" inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" autocomplete="current-password" required placeholder="••••••"></label><label>新しい6桁PIN<input name="new_pin" type="password" inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" autocomplete="new-password" required placeholder="••••••"></label><label>新しい6桁PIN（確認）<input name="confirm_pin" type="password" inputmode="numeric" pattern="[0-9]{6}" minlength="6" maxlength="6" autocomplete="new-password" required placeholder="••••••"></label><div class="jj-pin-change-note">変更後もこの端末ではログインを維持し、ほかの端末のセッションは失効します。</div><button class="primary">PINを変更</button></form></div>`);
  }
  function updateProfileAvatarPreview(){
    const old=$('.profile-settings-head .profile-avatar-xl');if(!old)return;
    const wrap=document.createElement('div');wrap.innerHTML=profileDraftAvatar?`<img class="profile-avatar profile-avatar-xl" src="${safe(profileDraftAvatar)}" alt="アイコンプレビュー">`:`<div class="profile-avatar profile-avatar-xl profile-avatar-fallback">${safe(profileInitials(me?.name))}</div>`;
    old.replaceWith(wrap.firstElementChild);
  }
  // Capture the existing account button before the legacy PIN-only modal handler runs.
  document.addEventListener('click',async e=>{
    if(e.target.closest('#accountBtn')){e.preventDefault();e.stopImmediatePropagation();return openProfileSettings()}
    if(e.target.closest('#openMemberDirectory')){e.preventDefault();return openMemberDirectory()}
    if(e.target.closest('#editMyProfileFromDirectory')){e.preventDefault();return openProfileSettings()}
    if(e.target.closest('#openPinSettings')){e.preventDefault();return openPinSettings()}
    if(e.target.closest('#profileAvatarRemove')){e.preventDefault();profileDraftAvatar='';return updateProfileAvatarPreview()}
  },true);
  document.addEventListener('change',async e=>{
    if(e.target.id!=='profileAvatarInput')return;
    try{profileDraftAvatar=await profileImageData(e.target.files?.[0]);updateProfileAvatarPreview();toast('アイコンを準備しました。保存すると反映されます')}catch(err){toast(err.message);e.target.value=''}
  },true);
  document.addEventListener('submit',async e=>{
    if(e.target.id!=='profileForm')return;e.preventDefault();e.stopImmediatePropagation();const fd=new FormData(e.target),btn=e.submitter;
    try{if(btn){btn.disabled=true;btn.textContent='保存中…'}const saved=await post('/profile/me',{grade:fd.get('grade')||'',faculty:fd.get('faculty')||'',department:fd.get('department')||'',hometown:fd.get('hometown')||'',hobbies:fd.get('hobbies')||'',bio:fd.get('bio')||'',avatar_data:profileDraftAvatar,visible:fd.get('visible')==='on'});closeModal();toast('プロフィールを保存しました')}
    catch(err){toast(err.message)}finally{if(btn){btn.disabled=false;btn.textContent='プロフィールを保存'}}
  },true);


  // v1.14 poker-table redesign — continuous play, unanimous first READY,
  // prominent street bets, poker-standard sizing presets, and hero-first layout.
  let jjPrevBoardCount=0,jjPrevHandId=null,jjPrevBets={};
  const jjSeatCoords=[
    {left:50,top:83},{left:16,top:66},{left:15,top:25},
    {left:50,top:10},{left:85,top:25},{left:84,top:66}
  ];
  const jjStreetLabel={preflop:'PREFLOP',flop:'FLOP',turn:'TURN',river:'RIVER',complete:'SHOWDOWN'};

  function jjHeroSeat(){return tableState?.seats?.find(p=>p.user_id===me?.id)?.seat ?? 0}
  function jjVisualIndex(actual){return ((Number(actual)-jjHeroSeat()+6)%6+6)%6}
  function jjSeatPos(actual){return jjSeatCoords[jjVisualIndex(actual)]||jjSeatCoords[0]}
  function jjBetPos(actual){const p=jjSeatPos(actual);return{left:50+(p.left-50)*.61,top:48+(p.top-48)*.59}}
  function jjPlayerState(p){
    if(p.sitting_out)return '一時離席';if(p.sit_out_next)return '次ハンドから一時離席';if(p.all_in)return 'ALL-IN';if(p.folded)return 'FOLDED';if(p.ready)return 'READY';return '';
  }
  function jjBoardHtml(cards){
    const handId=tableState?.hand?.id||null;
    if(handId!==jjPrevHandId){jjPrevHandId=handId;jjPrevBoardCount=0;jjPrevBets={}}
    const before=jjPrevBoardCount;
    const html=(cards||[]).map((c,i)=>{
      let h=cardHTML(c).replace('card-face ',`card-face jj-board-card ${i>=before?'jj-card-deal ':''}`);
      if(i>=before&&!h.includes('style="'))h=h.replace('>',` style="animation-delay:${Math.min(i-before,4)*90}ms">`);
      return h;
    }).join('');
    jjPrevBoardCount=(cards||[]).length;
    return html;
  }
  function jjMadeHand(){
    const hero=tableState?.seats?.find(p=>p.user_id===me?.id),board=tableState?.hand?.board||[],cards=[...(hero?.cards||[]),...board].filter(c=>c&&c!=='??');
    if(cards.length<2)return '';
    const ranks=cards.map(c=>'23456789TJQKA'.indexOf(c[0])+2),counts={};ranks.forEach(r=>counts[r]=(counts[r]||0)+1);
    const suits={};cards.forEach(c=>(suits[c[1]]||(suits[c[1]]=[])).push('23456789TJQKA'.indexOf(c[0])+2));
    const uniq=[...new Set(ranks)].sort((a,b)=>a-b);if(uniq.includes(14))uniq.unshift(1);
    const straight=uniq.some((_,i)=>i+4<uniq.length&&uniq[i+4]-uniq[i]===4);
    const flush=Object.values(suits).some(v=>v.length>=5);
    if(cards.length>=5&&straight&&flush)return 'Straight / Flush possible';
    const vals=Object.values(counts);if(vals.some(v=>v===4))return 'Four of a Kind';if(vals.includes(3)&&vals.filter(v=>v>=2).length>=2)return 'Full House';if(flush)return 'Flush';if(straight)return 'Straight';if(vals.some(v=>v===3))return 'Three of a Kind';if(vals.filter(v=>v===2).length>=2)return 'Two Pair';if(vals.some(v=>v===2))return 'One Pair';return board.length?'High Card':'Preflop';
  }
  function jjTotalPot(){return (tableState?.seats||[]).reduce((sum,p)=>sum+Number(p.contributed||0),0)}
  totalPot=jjTotalPot;

  renderSeat=function(seat){
    const p=tableState.seats.find(x=>x.seat===seat),pos=jjSeatPos(seat);
    if(!p)return `<div class="seat jj-seat seat-empty" style="left:${pos.left}%;top:${pos.top}%"><button class="jj-empty-seat" data-seat="${seat}">＋</button></div>`;
    const isAct=tableState.hand?.action_seat===seat,isButton=tableState.button_seat===seat,isHero=p.user_id===me.id,state=jjPlayerState(p),hole=(p.cards||[]).map(cardHTML).join('');
    const statusClass=p.sitting_out?' is-sitting':p.folded?' is-folded':'';
    return `<div class="seat jj-seat ${isAct?'active':''}${isHero?' is-hero':''}${statusClass}" style="left:${pos.left}%;top:${pos.top}%"><div class="seat-box jj-seat-box">${isButton?'<span class="dealer">D</span>':''}<div class="jj-player-top"><span class="jj-avatar">${safe(String(p.name||'?').slice(0,1))}</span><div><div class="name">${safe(p.name)}${isHero?' · YOU':''}</div><div class="stack">${bb(p.stack)}</div></div></div>${hole?`<div class="hole jj-hole">${hole}</div>`:''}${state?`<div class="jj-player-state">${state}</div>`:''}</div></div>`;
  };

  function jjRenderBetMarkers(){
    const layer=$('#seatLayer');if(!layer)return;
    const markers=(tableState?.seats||[]).filter(p=>Number(p.round_bet||0)>0).map(p=>{
      const pos=jjBetPos(p.seat),now=Number(p.round_bet||0),old=Number(jjPrevBets[p.user_id]||0),pulse=now>old?' jj-bet-pulse':'';jjPrevBets[p.user_id]=now;
      return `<div class="jj-bet-marker${pulse}" style="left:${pos.left}%;top:${pos.top}%"><i></i><b>${bb(now)}</b></div>`;
    }).join('');
    layer.insertAdjacentHTML('beforeend',markers);
  }

  renderPokerRoom=function(){
    if(!tableState)return;
    const hero=tableState.seats.find(p=>p.user_id===me.id),phase=tableState.hand?.phase||'waiting',actionSeat=tableState.hand?.action_seat,acting=tableState.seats.find(p=>p.seat===actionSeat),deadline=tableState.hand?.action_deadline;
    $('#roomTitle').textContent=tableState.name;$('#roomMeta').textContent='6-max · 0.5/1bb · 150bb · auto deal';
    $('#boardCards').innerHTML=jjBoardHtml(tableState.hand?.board||[]);$('#potDisplay').innerHTML=`<span>POT</span><b>${bb(jjTotalPot())}</b>`;
    let sec='';if(deadline){sec=Math.max(0,Math.ceil((new Date(deadline)-new Date())/1000));sec=` · ${sec}s`}
    const isMine=acting?.user_id===me.id;
    $('#handStatus').innerHTML=tableState.status==='playing'?`<b>${jjStreetLabel[phase]||String(phase).toUpperCase()}</b><span class="${isMine?'jj-your-turn':''}">${isMine?'YOUR TURN':acting?`${safe(acting.name)} TO ACT`:''}${sec}</span>`:tableState.session_active?'<b>次ハンド</b><span>自動ディール待機中</span>':'<b>開始準備</b><span>全員が準備OKで開始</span>';
    $('#seatLayer').innerHTML=Array.from({length:6},(_,seat)=>renderSeat(seat)).join('');jjRenderBetMarkers();
    const result=tableState.last_result;$('#resultBanner').classList.toggle('hidden',!result||!(tableState.seats||[]).length);if(result)$('#resultBanner').textContent=result.message;
    renderTableControls();renderActionBar();renderTableChat();renderHandLog();
    const zone=$('.poker-zone');zone?.classList.toggle('jj-action-on',!!tableState.legal?.can_act);zone?.classList.toggle('jj-hero-seated',!!hero);
  };

  renderTableControls=function(){
    const seated=tableState.seats.find(p=>p.user_id===me.id),active=(tableState.seats||[]).filter(p=>p.stack>0&&!p.sitting_out),ready=active.filter(p=>p.ready).length;
    if(!seated){$('#tableControls').innerHTML='<span class="hint">空席を選んで150bbで着席</span>';return}
    if(seated.stack<=0){$('#tableControls').innerHTML='<div class="jj-table-control-left"><span class="jj-control-note">BUSTED · 0bb</span></div><div class="jj-table-control-right"><button class="primary" data-table-presence="rebuy" '+(tableState.status==='playing'?'disabled':'')+'>リバイ（150bb）</button><button class="ghost" id="leaveSeatBtn">テーブルから退席</button></div>';return}
    let primary='';
    if(seated.sitting_out)primary='<button class="primary" data-table-presence="return">復帰する</button>';
    else if(seated.sit_out_next)primary='<button class="soft" data-table-presence="cancel_sitout">一時離席予約を取消</button>';
    else primary='<button class="ghost jj-sitout-btn" data-table-presence="sitout">次ハンドから一時離席</button>';
    let readyButton='';
    if(tableState.status!=='playing'&&!tableState.session_active&&!seated.sitting_out){readyButton=`<button class="primary jj-ready-btn ${seated.ready?'is-ready':''}" id="jjReadyBtn" ${seated.ready?'disabled':''}>${seated.ready?'✓ 準備OK':`準備 ${ready}/${Math.max(active.length,2)}`}</button>`}
    const leave=(tableState.status!=='playing'&&seated.sitting_out)?'<button class="ghost" id="leaveSeatBtn">席を完全に離れる</button>':'';
    $('#tableControls').innerHTML=`<div class="jj-table-control-left">${readyButton}<span class="jj-ready-count">${tableState.session_active?'自動進行':`準備 ${ready}/${active.length}`}</span></div><div class="jj-table-control-right">${primary}${leave}</div>`;
  };

  function jjHero(){return tableState?.seats?.find(p=>p.user_id===me?.id)}
  function jjRaiseBounds(){const l=tableState?.legal||{},big=Number(tableState?.big_blind||100);return{min:Number(l.min_raise_to||l.max_raise_to||0)/big,max:Number(l.max_raise_to||0)/big}}
  function jjClampRaiseBb(v){const b=jjRaiseBounds();return Math.max(b.min,Math.min(b.max,Number(v||b.min)))}
  function jjSetRaiseBb(v){const value=jjClampRaiseBb(v),inp=$('#raiseTo'),slider=$('#raiseSlider');if(inp)inp.value=(Math.round(value*100)/100);if(slider)slider.value=value;if($('#jjRaiseAmount'))$('#jjRaiseAmount').textContent=`${value.toFixed(value%1?1:0)}bb`}
  function jjPotPctBb(pct){
    const hero=jjHero(),l=tableState.legal||{},big=Number(tableState.big_blind||100),call=Number(l.call_amount||0),pot=jjTotalPot(),currentRound=Number(hero?.round_bet||0);
    const target=currentRound+call+(pot+call)*(Number(pct)/100);return jjClampRaiseBb(target/big);
  }

  renderActionBar=function(){
    const l=tableState.legal||{can_act:false},hero=jjHero();
    if(!hero){$('#actionBar').innerHTML='<span class="hint">着席するとアクションパネルが表示されます</span>';return}
    const handLabel=jjMadeHand();
    if(!l.can_act){$('#actionBar').innerHTML=`<div class="jj-hero-summary"><div class="jj-hero-cards">${(hero.cards||[]).map(cardHTML).join('')}</div><div><b>${safe(handLabel)}</b><span>${hero.sitting_out?'一時離席中':tableState.status==='playing'?'アクション待ち':'次のハンドを待機'}</span></div></div>`;return}
    const isPre=tableState.hand?.phase==='preflop',bounds=jjRaiseBounds(),min=bounds.min||0,max=bounds.max||0,call=Number(l.call_amount||0);
    const unopenedPre=isPre&&Number(tableState.hand?.current_bet||0)<=Number(tableState.big_blind||100);
    const presets=unopenedPre?[['2.5x',2.5],['3x',3],['4x',4]]:[[ '33%',33],[ '50%',50],[ '75%',75],[ 'POT',100]];
    const quick=presets.map(([label,val])=>unopenedPre?`<button class="jj-size-btn" data-raise-bb="${val}">${label}</button>`:`<button class="jj-size-btn" data-pot-pct="${val}">${label}</button>`).join('');
    const raiseControls=l.can_raise&&max>0?`<div class="jj-sizing"><div class="jj-size-row">${quick}</div><div class="jj-raise-editor"><input id="raiseSlider" type="range" min="${min}" max="${max}" step="0.5" value="${min}"><label><input id="raiseTo" type="number" inputmode="decimal" min="${min}" max="${max}" step="0.5" value="${min}"><span>bb</span></label><b id="jjRaiseAmount">${min}bb</b></div></div>`:'';
    const callButton=l.can_check?'<button class="jj-action-btn jj-check" data-action="check"><small>CHECK</small><b>チェック</b></button>':`<button class="jj-action-btn jj-call" data-action="call"><small>CALL</small><b>${bb(call)}</b></button>`;
    const raiseButton=l.can_raise?`<button class="jj-action-btn jj-raise" data-action="raise"><small>${l.can_check?'BET':'RAISE'}</small><b>実行</b></button>`:'';
    const allin=l.can_all_in?'<button class="jj-action-btn jj-allin" data-action="allin"><small>ALL-IN</small><b>MAX</b></button>':'';
    $('#actionBar').innerHTML=`<div class="jj-action-context"><div class="jj-hero-cards">${(hero.cards||[]).map(cardHTML).join('')}</div><div><span>${safe(handLabel)}</span>${call?`<b>TO CALL ${bb(call)}</b>`:'<b>YOUR ACTION</b>'}</div></div>${raiseControls}<div class="jj-main-actions"><button class="jj-action-btn jj-fold" data-action="fold"><small>FOLD</small><b>フォールド</b></button>${callButton}${raiseButton}${allin}</div>`;
  };

  document.addEventListener('click',async e=>{
    const ready=e.target.closest('#jjReadyBtn');if(ready){try{ready.disabled=true;await post(`/tables/${currentTableId}/start`);toast('開始準備を完了しました')}catch(err){toast(err.message)}return}
    const presence=e.target.closest('[data-table-presence]');if(presence){try{await post(`/tables/${currentTableId}/presence`,{mode:presence.dataset.tablePresence});toast(presence.dataset.tablePresence==='sitout'?'一時離席を設定しました':presence.dataset.tablePresence==='return'?'次ハンドから参加します':presence.dataset.tablePresence==='rebuy'?'150bbでリバイしました':presence.dataset.tablePresence==='unready'?'開始準備を取り消しました':'一時離席予約を取り消しました')}catch(err){toast(err.message)}return}
    const pct=e.target.closest('[data-pot-pct]');if(pct){jjSetRaiseBb(jjPotPctBb(Number(pct.dataset.potPct)));return}
    const rbb=e.target.closest('[data-raise-bb]');if(rbb){jjSetRaiseBb(Number(rbb.dataset.raiseBb));return}
  });
  document.addEventListener('input',e=>{if(e.target.id==='raiseSlider')jjSetRaiseBb(e.target.value);if(e.target.id==='raiseTo'&&$('#raiseSlider'))$('#raiseSlider').value=jjClampRaiseBb(e.target.value)});


  // v1.15 responsive poker workspace. The table is sized from its real column,
  // not from the viewport, so the felt can never invade chat/log or create a
  // horizontal page scrollbar. This wrapper preserves the v1.14 game UI logic.
  function jjFitPokerWorkspace(){
    const room=$('#pokerRoom'),zone=$('#pokerRoom .poker-zone');
    if(!room||!zone||room.classList.contains('hidden'))return;
    const zoneWidth=Math.max(300,zone.clientWidth-24),vh=Math.max(560,window.innerHeight||800);
    let height;
    if(window.innerWidth<=760){height=Math.max(430,Math.min(560,vh*.62));}
    else{height=Math.max(500,Math.min(680,zoneWidth*.61,vh*.74));}
    room.style.setProperty('--jj-stage-h',`${Math.round(height)}px`);
  }

  const jjV15RenderPokerRoom=renderPokerRoom;
  renderPokerRoom=function(){
    jjV15RenderPokerRoom();
    requestAnimationFrame(jjFitPokerWorkspace);
  };

  renderHandStatusOnly=function(){
    if(!tableState)return;
    const el=$('#handStatus');if(!el)return;
    const phase=tableState.hand?.phase||'waiting',actionSeat=tableState.hand?.action_seat,
      acting=tableState.seats.find(p=>p.seat===actionSeat),deadline=tableState.hand?.action_deadline;
    let sec='';
    if(deadline){const left=Math.max(0,Math.ceil((new Date(deadline)-new Date())/1000));sec=` · ${left}s`;}
    if(tableState.status==='playing'){
      const mine=acting?.user_id===me?.id;
      el.innerHTML=`<b>${jjStreetLabel[phase]||String(phase).toUpperCase()}</b><span class="${mine?'jj-your-turn':''}">${mine?'YOUR TURN':acting?`${safe(acting.name)} TO ACT`:''}${sec}</span>`;
    }else if(tableState.session_active){
      el.innerHTML='<b>次ハンド</b><span>自動ディール</span>';
    }else{
      el.innerHTML='<b>開始準備</b><span>全員が準備OKで開始</span>';
    }
  };

  let jjFitTimer=null;
  window.addEventListener('resize',()=>{
    clearTimeout(jjFitTimer);
    jjFitTimer=setTimeout(jjFitPokerWorkspace,80);
  },{passive:true});


  // v1.15.1 exact hero hand label. This is display-only and does not affect
  // showdown evaluation or payouts, which remain server-authoritative.
  jjMadeHand=function(){
    const hero=tableState?.seats?.find(p=>p.user_id===me?.id),board=tableState?.hand?.board||[],
      cards=[...(hero?.cards||[]),...board].filter(c=>c&&c!=='??');
    if(cards.length<2)return '';
    const value=c=>'23456789TJQKA'.indexOf(c[0])+2;
    const straightHigh=values=>{
      const u=[...new Set(values)].sort((a,b)=>a-b);if(u.includes(14))u.unshift(1);
      let best=0,run=1;
      for(let i=1;i<u.length;i++){
        if(u[i]===u[i-1]+1){run++;if(run>=5)best=u[i];}else if(u[i]!==u[i-1])run=1;
      }
      return best;
    };
    const ranks=cards.map(value),counts={};ranks.forEach(r=>counts[r]=(counts[r]||0)+1);
    if(board.length===0)return counts[ranks[0]]===2?'Pocket Pair':'Preflop';
    const suits={};cards.forEach(c=>(suits[c[1]]||(suits[c[1]]=[])).push(value(c)));
    const flushValues=Object.values(suits).filter(v=>v.length>=5);
    if(flushValues.some(v=>straightHigh(v)))return 'Straight Flush';
    const groups=Object.entries(counts).map(([r,n])=>({r:Number(r),n})).sort((a,b)=>b.n-a.n||b.r-a.r);
    if(groups.some(g=>g.n===4))return 'Four of a Kind';
    const trips=groups.filter(g=>g.n>=3),pairs=groups.filter(g=>g.n>=2);
    if(trips.length>=1&&pairs.some(g=>g.r!==trips[0].r))return 'Full House';
    if(flushValues.length)return 'Flush';
    if(straightHigh(ranks))return 'Straight';
    if(trips.length)return 'Three of a Kind';
    if(groups.filter(g=>g.n>=2).length>=2)return 'Two Pair';
    if(groups.some(g=>g.n>=2))return 'One Pair';
    return 'High Card';
  };


  // v1.16 playable table state machine.
  // Fixed 150bb means seating needs no modal. A seat click is one atomic API
  // action, including during an active hand (server queues that player 一時離席).
  let jjSeatBusy=false;
  seatClick=async function(seat){
    if(!currentTableId||jjSeatBusy)return;
    if(tableState?.seats?.some(p=>p.user_id===me?.id))return toast('すでに着席しています');
    if(tableState?.seats?.some(p=>Number(p.seat)===Number(seat)))return toast('その席は使用中です');
    jjSeatBusy=true;
    const button=document.querySelector(`[data-seat="${Number(seat)}"]`);
    if(button)button.disabled=true;
    try{
      const wasPlaying=tableState?.status==='playing';
      tableState=await post(`/tables/${currentTableId}/seat`,{seat:Number(seat)});
      renderPokerRoom();
      toast(wasPlaying?'着席しました。次ハンドから参加を押すと参加します':'150bbで着席しました。全員が準備OKになると開始します');
    }catch(err){
      toast(err.message);
      try{const d=await api('/tables/'+currentTableId);tableState=d.state;tableMessages=d.messages||[];renderPokerRoom()}catch{}
    }finally{jjSeatBusy=false;if(button)button.disabled=false}
  };

  renderTableControls=function(){
    const seated=tableState?.seats?.find(p=>p.user_id===me?.id);
    const nextPlayers=(tableState?.seats||[]).filter(p=>Number(p.stack)>0&&!p.sitting_out&&!p.sit_out_next);
    const ready=nextPlayers.filter(p=>p.ready).length;
    if(!seated){
      $('#tableControls').innerHTML='<div class="jj-table-control-left"><span class="hint">空席の「座る」を押すと150bbで着席します</span></div>';
      return;
    }
    const canLeaveNow=!seated.in_hand;
    if(Number(seated.stack)<=0){
      $('#tableControls').innerHTML=`<div class="jj-table-control-left"><span class="jj-control-note">BUSTED · 0bb</span></div><div class="jj-table-control-right"><button class="primary" data-table-presence="rebuy" ${tableState.status==='playing'?'disabled':''}>リバイ（150bb）</button>${canLeaveNow?'<button class="ghost" id="leaveSeatBtn">テーブルから退席</button>':''}</div>`;
      return;
    }
    let presence='';
    if(seated.sitting_out){
      const label=tableState.session_active?'次ハンドから参加':'テーブルに戻る';
      presence=`<button class="primary" data-table-presence="return">${label}</button>`;
    }else if(seated.sit_out_next){
      presence='<button class="soft" data-table-presence="cancel_sitout">一時離席予約を取消</button>';
    }else if(tableState.status==='playing'){
      presence='<button class="ghost jj-sitout-btn" data-table-presence="sitout">次ハンドから一時離席</button>';
    }else{
      presence='<button class="ghost jj-sitout-btn" data-table-presence="sitout">一時離席する</button>';
    }
    let readyButton='';
    if(tableState.status!=='playing'&&!tableState.session_active&&!seated.sitting_out){
      readyButton=seated.ready
        ? '<button class="soft jj-ready-btn is-ready" data-table-presence="unready">✓ 準備OK · 取消</button>'
        : '<button class="primary jj-ready-btn" id="jjReadyBtn">準備OK</button>';
    }
    const countText=tableState.session_active?`次ハンド ${nextPlayers.length}/6`:`準備 ${ready}/${nextPlayers.length}`;
    const leave=canLeaveNow?'<button class="ghost" id="leaveSeatBtn">テーブルから退席</button>':'';
    $('#tableControls').innerHTML=`<div class="jj-table-control-left">${readyButton}<span class="jj-ready-count">${countText}</span></div><div class="jj-table-control-right">${presence}${leave}</div>`;
  };

  renderLobby=async function(){
    if(currentTableId)return;
    $('#lobbyPanel').classList.remove('hidden');$('#pokerRoom').classList.add('hidden');
    const tables=await api('/tables');
    $('#tableCards').innerHTML=tables.map(t=>{
      const extra=[];
      if(Number(t.seated||0)!==Number(t.players||0))extra.push(`着席中 ${Number(t.seated||0)}/6`);
      if(Number(t.sitouts||0)>0)extra.push(`一時離席 ${Number(t.sitouts||0)}`);
      return `<article class="lobby-card"><div class="eyebrow ${t.status==='playing'?'status-live':''}">${t.status==='playing'?'● HAND IN PROGRESS':'OPEN TABLE'}</div><h4>${safe(t.name)}</h4><div class="lobby-stats"><span>プレイ中 ${Number(t.players||0)}/6</span>${extra.map(x=>`<span>${x}</span>`).join('')}<span>0.5 / 1 bb</span><span>150bb start</span></div><p class="hint">ハンド中でも空席を予約できます。途中着席は一時離席状態で入り、本人が「次ハンドから参加」を押すまで配られません。</p><button class="primary full" data-open-table="${safe(t.id)}">テーブルを開く</button></article>`;
    }).join('')||'<div class="card empty">テーブルがありません</div>';
  };


  // v1.16.2 unmistakable primary seating.
  // Seat markers remain optional; every observer gets a large persistent JOIN
  // control on the table and the lobby also exposes direct seating.
  let jjJoinBusy=false;

  async function jjJoinTable(tableId,{openAfter=false}={}){
    if(!tableId||jjJoinBusy)return;
    jjJoinBusy=true;
    document.querySelectorAll('[data-jj-join],#jjJoinTableBtn').forEach(b=>b.disabled=true);
    try{
      const state=await post(`/tables/${tableId}/join`);
      if(openAfter||currentTableId!==tableId){
        await openTable(tableId);
      }else{
        tableState=state;
        renderPokerRoom();
      }
      toast('150bbで着席しました。進行中なら次ハンドから参加します');
    }catch(err){
      toast(err.message);
      if(currentTableId===tableId){
        try{const d=await api('/tables/'+tableId);tableState=d.state;tableMessages=d.messages||[];renderPokerRoom()}catch{}
      }
    }finally{
      jjJoinBusy=false;
      document.querySelectorAll('[data-jj-join],#jjJoinTableBtn').forEach(b=>b.disabled=false);
    }
  }

  function jjRenderPrimaryJoin(){
    const table=$('#pokerTable');
    if(!table||!tableState||!me)return;
    table.querySelector('#jjObserverJoin')?.remove();
    const seated=(tableState.seats||[]).some(p=>p.user_id===me.id);
    if(seated)return;
    const full=(tableState.seats||[]).length>=Number(tableState.max_seats||6);
    const el=document.createElement('div');
    el.id='jjObserverJoin';
    el.className='jj-observer-join';
    el.innerHTML=full
      ? '<div><b>TABLE FULL</b><span>空席ができるまで観戦できます</span></div><button class="ghost" disabled>満席</button>'
      : '<div><b>JOIN TABLE</b><span>150bb · プレイマネー</span></div><button class="primary" id="jjJoinTableBtn">着席してプレイ</button>';
    table.appendChild(el);
  }

  const jjV162RenderPokerRoom=renderPokerRoom;
  renderPokerRoom=function(){
    jjV162RenderPokerRoom();
    jjRenderPrimaryJoin();
  };

  renderTableControls=function(){
    const seated=tableState?.seats?.find(p=>p.user_id===me?.id);
    const nextPlayers=(tableState?.seats||[]).filter(p=>Number(p.stack)>0&&!p.sitting_out&&!p.sit_out_next);
    const ready=nextPlayers.filter(p=>p.ready).length;
    if(!seated){
      const full=(tableState?.seats||[]).length>=Number(tableState?.max_seats||6);
      $('#tableControls').innerHTML=`<div class="jj-table-control-left"><b class="jj-control-title">観戦中</b><span class="hint">${full?'現在は満席です':'150bbで参加できます'}</span></div><div class="jj-table-control-right"><button class="primary jj-join-control" data-jj-join="${safe(currentTableId||'')}" ${full?'disabled':''}>${full?'満席':'着席する · 150bb'}</button></div>`;
      return;
    }
    const canLeaveNow=!seated.in_hand;
    if(Number(seated.stack)<=0){
      $('#tableControls').innerHTML=`<div class="jj-table-control-left"><span class="jj-control-note">BUSTED · 0bb</span></div><div class="jj-table-control-right"><button class="primary" data-table-presence="rebuy" ${tableState.status==='playing'?'disabled':''}>リバイ（150bb）</button>${canLeaveNow?'<button class="ghost" id="leaveSeatBtn">テーブルから退席</button>':''}</div>`;
      return;
    }
    let presence='';
    if(seated.sitting_out){
      const label=tableState.session_active?'次ハンドから参加':'テーブルに戻る';
      presence=`<button class="primary" data-table-presence="return">${label}</button>`;
    }else if(seated.sit_out_next){
      presence='<button class="soft" data-table-presence="cancel_sitout">一時離席予約を取消</button>';
    }else if(tableState.status==='playing'){
      presence='<button class="ghost jj-sitout-btn" data-table-presence="sitout">次ハンドから一時離席</button>';
    }else{
      presence='<button class="ghost jj-sitout-btn" data-table-presence="sitout">一時離席する</button>';
    }
    let readyButton='';
    if(tableState.status!=='playing'&&!tableState.session_active&&!seated.sitting_out){
      readyButton=seated.ready
        ? '<button class="soft jj-ready-btn is-ready" data-table-presence="unready">✓ 準備OK · 取消</button>'
        : '<button class="primary jj-ready-btn" id="jjReadyBtn">準備OK</button>';
    }
    const countText=tableState.session_active?`次ハンド ${nextPlayers.length}/6`:`準備 ${ready}/${nextPlayers.length}`;
    const leave=canLeaveNow?'<button class="ghost" id="leaveSeatBtn">テーブルから退席</button>':'';
    $('#tableControls').innerHTML=`<div class="jj-table-control-left">${readyButton}<span class="jj-ready-count">${countText}</span></div><div class="jj-table-control-right">${presence}${leave}</div>`;
  };

  renderLobby=async function(){
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

  document.addEventListener('click',async e=>{
    const join=e.target.closest('#jjJoinTableBtn,[data-jj-join]');
    if(!join)return;
    e.preventDefault();
    const tableId=join.dataset.jjJoin||currentTableId;
    await jjJoinTable(tableId,{openAfter:currentTableId!==tableId});
  });


  // v1.17 mobile poker shell.
  // The general-purpose mobile navigation must not compete with poker controls.
  // A live table becomes an immersive surface with one compact table header,
  // one felt, and one action console.
  const jjMobilePokerMq=window.matchMedia('(max-width:760px)');

  function jjV17Hero(){return tableState?.seats?.find(p=>p.user_id===me?.id)||null}
  function jjV17SyncMobilePoker(){
    const mobile=jjMobilePokerMq.matches;
    const open=mobile&&!!currentTableId&&!!tableState;
    const hero=open?jjV17Hero():null;
    const canAct=!!(open&&hero&&tableState?.legal?.can_act);
    const playing=!!(open&&hero&&tableState?.status==='playing');
    const observer=!!(open&&!hero);
    document.body.classList.toggle('jj-mobile-table-open',open);
    document.body.classList.toggle('jj-mobile-poker-seated',!!hero&&open);
    document.body.classList.toggle('jj-mobile-poker-observer',observer);
    document.body.classList.toggle('jj-mobile-poker-can-act',canAct);
    document.body.classList.toggle('jj-mobile-poker-hand',playing);
    const zone=$('#pokerRoom .poker-zone');
    if(zone){
      zone.classList.toggle('jj-mobile-observer',observer);
      zone.classList.toggle('jj-mobile-can-act',canAct);
      zone.classList.toggle('jj-mobile-hand-live',playing);
    }
    const roomMeta=$('#roomMeta');
    if(open&&roomMeta){
      const active=(tableState.seats||[]).filter(p=>Number(p.stack)>0&&!p.sitting_out&&!p.sit_out_next).length;
      roomMeta.textContent=hero?`${bb(hero.stack)} · ${active}/6`:`観戦 · ${active}/6`;
    }
  }

  // Keep all six seats comfortably inside the phone felt. The previous top seat
  // was too close to the clipped edge on Safari.
  const jjV17DesktopSeatPos=jjSeatPos;
  jjSeatPos=function(actual){
    if(!jjMobilePokerMq.matches)return jjV17DesktopSeatPos(actual);
    const coords=[
      {left:50,top:80},{left:15,top:65},{left:16,top:28},
      {left:50,top:16},{left:84,top:28},{left:85,top:65}
    ];
    return coords[jjVisualIndex(actual)]||coords[0];
  };
  jjBetPos=function(actual){
    const p=jjSeatPos(actual);
    return {left:50+(p.left-50)*.58,top:48+(p.top-48)*.57};
  };

  const jjV17RenderPokerRoom=renderPokerRoom;
  renderPokerRoom=function(){
    jjV17RenderPokerRoom();
    jjV17SyncMobilePoker();
    // Observer seating has exactly one primary CTA on phones. The secondary
    // table-control duplicate is visually suppressed by the mobile shell CSS.
    const result=$('#resultBanner');
    if(result&&tableState?.last_result)result.setAttribute('role','status');
  };

  const jjV17OpenTable=openTable;
  openTable=async function(id){
    if(jjMobilePokerMq.matches)document.body.classList.add('jj-mobile-table-open');
    try{
      await jjV17OpenTable(id);
      jjV17SyncMobilePoker();
      if(jjMobilePokerMq.matches)window.scrollTo(0,0);
    }catch(err){
      document.body.classList.remove('jj-mobile-table-open','jj-mobile-poker-seated','jj-mobile-poker-observer','jj-mobile-poker-can-act','jj-mobile-poker-hand');
      throw err;
    }
  };

  const jjV17DisconnectTable=disconnectTable;
  disconnectTable=function(){
    jjV17DisconnectTable();
    document.body.classList.remove('jj-mobile-table-open','jj-mobile-poker-seated','jj-mobile-poker-observer','jj-mobile-poker-can-act','jj-mobile-poker-hand');
  };

  jjMobilePokerMq.addEventListener?.('change',()=>{jjV17SyncMobilePoker();requestAnimationFrame(()=>{try{jjFitPokerWorkspace()}catch{}})});


  // v1.18.4 portrait-first table geometry.
  // Mobile poker apps commonly keep the hero at the bottom, arrange opponents
  // around a tall oval, place the board/pot in the visual center, and reserve
  // the thumb zone at the bottom for betting controls. Only portrait phones use
  // these coordinates; desktop and landscape retain the existing layout.
  const jjPortraitPokerMq=window.matchMedia('(max-width:760px) and (orientation:portrait)');
  const jjV184SeatPos=jjSeatPos;
  jjSeatPos=function(actual){
    if(!jjPortraitPokerMq.matches)return jjV184SeatPos(actual);
    const coords=[
      {left:50,top:82},
      {left:13,top:64},
      {left:18,top:31},
      {left:50,top:15},
      {left:82,top:31},
      {left:87,top:64},
    ];
    return coords[jjVisualIndex(actual)]||coords[0];
  };
  jjBetPos=function(actual){
    if(!jjPortraitPokerMq.matches){
      const p=jjSeatPos(actual);
      return {left:50+(p.left-50)*.58,top:48+(p.top-48)*.57};
    }
    const p=jjSeatPos(actual);
    return {left:50+(p.left-50)*.53,top:46+(p.top-46)*.53};
  };
  jjPortraitPokerMq.addEventListener?.('change',()=>{
    if(currentTableId&&tableState){renderPokerRoom();requestAnimationFrame(()=>{try{jjFitPokerWorkspace()}catch{}})}
  });


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
    const earned=Number(quiz.earned||0);
    if(quiz.count>=10&&!quiz.q){
      $('#quizStage').innerHTML=`<div class="pot-num">${quiz.score}/10</div><p>${quiz.score>=8?'Good pace.':'もう一周すると速くなります。'}</p><div class="jj-quiz-reward">今回の獲得 <b>+${earned}pt</b></div>`;
      $('#quizChoices').innerHTML='';
      $('#quizScore').textContent=`正解 ${quiz.score} / 10 · 獲得 +${earned}pt`;
      return;
    }
    if(!quiz.q||!quiz.q.id){
      $('#quizStage').innerHTML='<div class="hint">問題を読み込み中…</div>';
      $('#quizChoices').innerHTML='';
      jjV186LoadQuiz();
      return;
    }
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


  // v1.19.2 Japanese-first learning share.
  // Articles prioritize the official Japanese GTO Wizard feed. Videos are
  // intentionally restricted server-side to curated, trusted poker sources.
  let jjV192LearningBusy=false;

  function jjV192LearningShell(){
    let shell=$('#jjLearningShare');
    if(shell)return shell;
    const home=$('#homeView');
    if(!home)return null;
    shell=document.createElement('section');
    shell.id='jjLearningShare';
    shell.className='jj-learning-share';
    shell.innerHTML=`<div class="jj-learning-head"><div><div class="eyebrow">POKER STUDY</div><h2>今日の学び</h2><p>記事は日本語で読めるものだけを表示。動画は信頼できるポーカー発信元から選定しています。</p></div><span class="jj-learning-policy">日本語記事のみ</span></div><div class="jj-learning-columns"><section class="jj-learning-column"><div class="jj-learning-title"><b>ARTICLE</b><span>GTO Wizard Japan</span></div><div id="jjLearningArticles" class="jj-learning-list"><div class="card empty">読み込み中…</div></div></section><section class="jj-learning-column"><div class="jj-learning-title"><b>YOUTUBE</b><span>解説・モチベーション</span></div><div id="jjLearningVideos" class="jj-video-list"><div class="card empty">読み込み中…</div></div></section></div>`;
    home.appendChild(shell);
    jjV192RenderArticles(jjJapaneseArticleFallback);
    return shell;
  }

  function jjV192StudyDate(value){
    if(!value)return '';
    try{return new Intl.DateTimeFormat('ja-JP',{year:'numeric',month:'short',day:'numeric'}).format(new Date(value))}catch{return ''}
  }

  function jjV192RenderArticles(items){
    const box=$('#jjLearningArticles');if(!box)return;
    const filtered=jjJapaneseStudyArticles(items);
    const selected=filtered.length?filtered:jjJapaneseStudyArticles(jjJapaneseArticleFallback);
    box.innerHTML=selected.slice(0,5).map(item=>`<a class="jj-study-card" href="${safe(item.url)}" target="_blank" rel="noopener noreferrer"><div class="jj-study-meta"><span class="jj-study-source">GTO Wizard Japan</span>${item.topic?`<span>${safe(item.topic)}</span>`:''}</div><h3>${safe(item.title||'')}</h3>${item.summary?`<p>${safe(item.summary)}</p>`:''}<footer><span>${safe(jjV192StudyDate(item.published_at))}</span><b>日本語で読む →</b></footer></a>`).join('')||'<div class="card empty">共有できる日本語記事がありません</div>';
  }

  function jjV192VideoLabel(category){return category==='motivation'?'MOTIVATION':'STRATEGY'}
  function jjV192VideoLabelJa(category){return category==='motivation'?'モチベーション':'戦略解説'}

  function jjV192RenderVideos(items){
    const box=$('#jjLearningVideos');if(!box)return;
    const ordered=[...(items||[])].sort((a,b)=>{
      const ac=a.category==='strategy'?0:1,bc=b.category==='strategy'?0:1;
      return ac-bc||String(b.published_at||'').localeCompare(String(a.published_at||''));
    });
    box.innerHTML=ordered.slice(0,5).map(item=>`<a class="jj-video-card" href="${safe(item.url||'#')}" target="_blank" rel="noopener noreferrer">${item.thumbnail?`<div class="jj-video-thumb"><img src="${safe(item.thumbnail)}" alt="" loading="lazy" referrerpolicy="no-referrer"><span>▶</span></div>`:''}<div class="jj-video-copy"><div class="jj-study-meta"><span class="jj-video-kind ${item.category==='motivation'?'is-motivation':''}">${jjV192VideoLabel(item.category)}</span><span>${safe(item.source||'')}</span></div><h3>${safe(item.title||'')}</h3><p>${safe(item.reason||jjV192VideoLabelJa(item.category))}</p><footer><span>${safe(jjV192StudyDate(item.published_at))}</span><b>YouTube →</b></footer></div></a>`).join('')||'<div class="card empty">共有できる動画がありません</div>';
  }

  async function jjV192RenderLearning(){
    if(jjV192LearningBusy)return;
    const shell=jjV192LearningShell();if(!shell)return;
    jjV192LearningBusy=true;
    try{
      const data=await api('/learning-content');
      jjV192RenderArticles(data.articles||[]);
      jjV192RenderVideos(data.videos||[]);
      shell.dataset.loaded='1';
    }catch(err){
      const videos=$('#jjLearningVideos');
      jjV192RenderArticles(jjJapaneseArticleFallback);
      if(videos)videos.innerHTML='<div class="card empty">動画を取得できませんでした。時間をおいて再読み込みしてください。</div>';
    }finally{jjV192LearningBusy=false}
  }

  const jjV192BaseRenderHome=renderHome;
  renderHome=async function(){
    const result=await jjV192BaseRenderHome();
    jjV192LearningShell();
    jjV192RenderLearning();
    return result;
  };


  // v1.19.3 member PIN self-service.
  // Use a dedicated form id so the older two-field handler cannot submit before
  // the confirmation field is checked.
  document.addEventListener('submit',async event=>{
    if(event.target.id!=='pinChangeConfirmForm')return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const form=event.target,fd=new FormData(form),button=event.submitter;
    const current=String(fd.get('current_pin')||'').trim();
    const next=String(fd.get('new_pin')||'').trim();
    const confirmPin=String(fd.get('confirm_pin')||'').trim();
    if(!/^\d{6}$/.test(current)||!/^\d{6}$/.test(next)||!/^\d{6}$/.test(confirmPin))return toast('PINは6桁の数字で入力してください');
    if(next!==confirmPin)return toast('新しいPINが一致しません');
    if(current===next)return toast('現在と異なるPINを設定してください');
    try{
      if(button){button.disabled=true;button.textContent='変更中…'}
      await post('/auth/change-pin',{current_pin:current,new_pin:next});
      form.reset();
      closeModal();
      toast('PINを変更しました');
    }catch(err){toast(err.message)}
    finally{if(button){button.disabled=false;button.textContent='PINを変更'}}
  },true);


  // v1.19.4 UI foundation and accessibility.
  // This layer is deliberately presentation-only: no ranking, points, auth,
  // tournament, or poker-engine semantics are changed here.
  let jjV194ConnectionNode=null;

  function jjV194EnsureConnectionStatus(){
    if(jjV194ConnectionNode?.isConnected)return jjV194ConnectionNode;
    let node=document.getElementById('jjConnectionStatus');
    if(!node){
      node=document.createElement('div');
      node.id='jjConnectionStatus';
      node.className='jj-connection-status';
      node.setAttribute('role','status');
      node.setAttribute('aria-live','polite');
      node.hidden=true;
      document.body.appendChild(node);
    }
    jjV194ConnectionNode=node;
    return node;
  }

  function jjV194UpdateConnectionStatus(){
    const node=jjV194EnsureConnectionStatus();
    const offline=navigator.onLine===false;
    node.hidden=!offline;
    node.textContent=offline?'オフラインです。接続が戻るまで操作結果は確定しない場合があります。':'';
    document.documentElement.classList.toggle('jj-is-offline',offline);
  }

  function jjV194EnhanceDom(root=document){
    document.documentElement.lang='ja';
    const toast=document.getElementById('toast');
    if(toast){
      toast.setAttribute('role','status');
      toast.setAttribute('aria-live','polite');
      toast.setAttribute('aria-atomic','true');
    }
    const login=document.getElementById('pinForm');
    if(login)login.setAttribute('aria-describedby','authMessage');
    const loginName=document.getElementById('loginName');
    if(loginName){
      loginName.setAttribute('autocapitalize','none');
      loginName.setAttribute('spellcheck','false');
      loginName.setAttribute('enterkeyhint','next');
    }
    const loginPin=document.getElementById('loginPin');
    if(loginPin)loginPin.setAttribute('enterkeyhint','go');
    const account=document.getElementById('accountBtn');
    if(account&&!account.getAttribute('aria-label'))account.setAttribute('aria-label','アカウント設定を開く');
    const actionBar=document.getElementById('actionBar');
    if(actionBar){
      actionBar.setAttribute('role','region');
      actionBar.setAttribute('aria-label','ポーカー操作');
    }
    const quiz=document.getElementById('quizChoices');
    if(quiz){
      quiz.setAttribute('role','group');
      quiz.setAttribute('aria-label','クイズの回答候補');
    }
    root.querySelectorAll?.('a[target="_blank"]').forEach(link=>{
      const rel=new Set(String(link.getAttribute('rel')||'').split(/\s+/).filter(Boolean));
      rel.add('noopener');rel.add('noreferrer');
      link.setAttribute('rel',[...rel].join(' '));
    });
    root.querySelectorAll?.('button[disabled],input[disabled],select[disabled],textarea[disabled]').forEach(el=>el.setAttribute('aria-disabled','true'));
  }

  function jjV194Boot(){
    jjV194EnhanceDom(document);
    jjV194UpdateConnectionStatus();
    window.addEventListener('online',jjV194UpdateConnectionStatus,{passive:true});
    window.addEventListener('offline',jjV194UpdateConnectionStatus,{passive:true});
    const observer=new MutationObserver(records=>{
      for(const record of records){
        for(const node of record.addedNodes){
          if(node?.nodeType===1)jjV194EnhanceDom(node);
        }
      }
    });
    observer.observe(document.body,{childList:true,subtree:true});
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',jjV194Boot,{once:true});
  else jjV194Boot();


  // v1.20.0 private hand history and analytics.
  // This is a private self-review layer and does not alter rankings or poker rules.
  titles.analysis=['HAND REVIEW','ハンド分析'];
  const jjAnalysisState={range:'all',position:'',result:'all',showdown:'all',street:'',bookmarked:false,q:'',offset:0,limit:30,total:0,summary:null,hands:[],loading:false};
  const jjRate=v=>v?.value==null?'—':`${Number(v.value).toFixed(1).replace(/\.0$/,'')}%`;
  const jjSigned=v=>{const n=Number(v||0);return `${n>0?'+':''}${Number.isInteger(n)?n:n.toFixed(2).replace(/0+$/,'').replace(/\.$/,'')}bb`};
  const jjN=v=>Number(v?.n||0);
  const jjCardSet=cards=>(cards||[]).map(c=>cardHTML(c)).join('');
  const jjAnalysisDate=v=>v?dateFmt(v,{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}):'—';
  const jjMetric=(label,metric,detail='')=>`<article class="jj-stat"><span>${safe(label)}</span><strong>${safe(jjRate(metric))}</strong><small>${jjN(metric)} samples${detail?` · ${safe(detail)}`:''}</small></article>`;

  function jjEnsureAnalysisUI(){
    if($('#analysisView'))return;
    const nav=document.createElement('button');nav.className='nav';nav.dataset.view='analysis';nav.innerHTML='⌁ <span>ハンド分析</span>';
    const tableNav=$('.sidebar .nav[data-view="tables"]');if(tableNav)tableNav.insertAdjacentElement('afterend',nav);else $('.sidebar nav')?.appendChild(nav);
    nav.addEventListener('click',()=>switchView('analysis'));
    const view=document.createElement('section');view.id='analysisView';view.className='view';
    view.innerHTML=`
      <div class="jj-analysis-hero"><div><div class="eyebrow">PRIVATE PERFORMANCE LAB</div><h3>自分のプレイを、数字とハンドで振り返る。</h3><p>オンライン卓で確定した自分のハンドだけを記録します。統計はGTO判定ではなく、実際のプレイ頻度と収支の傾向です。</p></div><div class="jj-analysis-hero-actions"><label>期間<select id="jjAnalysisRange"><option value="all">全期間</option><option value="90d">90日</option><option value="30d">30日</option><option value="7d">7日</option></select></label><button class="soft" id="jjAnalysisRefresh">更新</button><button class="soft" id="jjAnalysisCsv">CSV</button></div></div>
      <div id="jjAnalysisKpis" class="jj-analysis-kpis"></div>
      <section class="card jj-analysis-chart-card"><div class="section-head"><div><div class="eyebrow">RESULT TREND</div><h3>累積収支</h3></div><span id="jjAnalysisTrendMeta" class="hint"></span></div><div id="jjAnalysisTrend" class="jj-analysis-trend"></div></section>
      <div class="jj-analysis-grid"><section class="card panel"><div class="section-head"><div><div class="eyebrow">CORE STATS</div><h3>プリフロップ / ポストフロップ</h3></div></div><div id="jjAnalysisStats" class="jj-stat-grid"></div></section><section class="card panel"><div class="section-head"><div><div class="eyebrow">PATTERN CHECK</div><h3>要確認の傾向</h3></div></div><div id="jjAnalysisSignals" class="jj-signal-list"></div></section></div>
      <div class="jj-analysis-grid"><section class="card panel"><div class="section-head"><div><div class="eyebrow">POSITION</div><h3>ポジション別</h3></div></div><div id="jjAnalysisPositions" class="jj-dimension-table"></div></section><section class="card panel"><div class="section-head"><div><div class="eyebrow">STACK DEPTH</div><h3>開始時Effective Stack別</h3></div></div><div id="jjAnalysisStacks" class="jj-dimension-table"></div></section></div>
      <section class="card panel jj-session-panel"><div class="section-head"><div><div class="eyebrow">SESSIONS</div><h3>セッション履歴</h3><p>30分以上プレイが空くと別セッションとして集計します。</p></div></div><div id="jjAnalysisSessions" class="jj-session-grid"></div></section>
      <section class="jj-hand-browser"><div class="section-head"><div><div class="eyebrow">HAND HISTORY</div><h3>ハンド履歴</h3><p>ポジション、勝敗、到達ストリート、ショーダウン、ブックマークで絞り込めます。</p></div><span id="jjHandCount" class="table-rule">0 HANDS</span></div><div class="card jj-hand-filters"><input id="jjHandSearch" placeholder="Hand ID / 卓 / Position"><select id="jjHandPosition"><option value="">全ポジション</option><option>UTG</option><option>HJ</option><option>CO</option><option>BTN</option><option>BTN/SB</option><option>SB</option><option>BB</option></select><select id="jjHandResult"><option value="all">勝敗: すべて</option><option value="win">勝ち</option><option value="loss">負け</option><option value="even">±0</option></select><select id="jjHandStreet"><option value="">到達: すべて</option><option value="flop">Flop+</option><option value="turn">Turn+</option><option value="river">River</option></select><select id="jjHandShowdown"><option value="all">Showdown: すべて</option><option value="yes">あり</option><option value="no">なし</option></select><label class="jj-bookmark-filter"><input id="jjHandBookmarked" type="checkbox"> ★のみ</label><button class="ghost" id="jjHandFilterReset">リセット</button></div><div id="jjHandList" class="jj-hand-list"></div><button id="jjHandMore" class="soft full hidden">さらに読み込む</button></section>`;
    $('.main')?.appendChild(view);jjBindAnalysisUI();jjEnsureAnalysisHomeShortcut();
  }

  function jjEnsureAnalysisHomeShortcut(){const home=$('#homeView');if(!home||$('#jjAnalysisHomeShortcut'))return;const section=document.createElement('section');section.id='jjAnalysisHomeShortcut';section.className='card jj-analysis-home';section.innerHTML=`<div><div class="eyebrow">HAND REVIEW</div><h3>直近のプレイを振り返る</h3><p>オンライン卓のハンド履歴、VPIP/PFR、ポジション別収支、リプレイを自分だけで確認できます。</p></div><button class="primary" type="button">ハンド分析を開く</button>`;section.querySelector('button').addEventListener('click',()=>switchView('analysis'));const hero=home.querySelector('.hero-grid');if(hero)hero.insertAdjacentElement('afterend',section);else home.prepend(section)}

  function jjBindAnalysisUI(){
    $('#jjAnalysisRange')?.addEventListener('change',e=>{jjAnalysisState.range=e.target.value;jjAnalysisState.offset=0;jjAnalysisLoad(true)});$('#jjAnalysisRefresh')?.addEventListener('click',()=>jjAnalysisLoad(true));$('#jjAnalysisCsv')?.addEventListener('click',()=>jjDownload(`/analysis/export.csv?range=${encodeURIComponent(jjAnalysisState.range)}`,'jj-hand-analysis.csv'));
    let timer;$('#jjHandSearch')?.addEventListener('input',e=>{clearTimeout(timer);timer=setTimeout(()=>{jjAnalysisState.q=e.target.value.trim();jjAnalysisState.offset=0;jjLoadHands(true)},250)});$('#jjHandPosition')?.addEventListener('change',e=>{jjAnalysisState.position=e.target.value;jjAnalysisState.offset=0;jjLoadHands(true)});$('#jjHandResult')?.addEventListener('change',e=>{jjAnalysisState.result=e.target.value;jjAnalysisState.offset=0;jjLoadHands(true)});$('#jjHandStreet')?.addEventListener('change',e=>{jjAnalysisState.street=e.target.value;jjAnalysisState.offset=0;jjLoadHands(true)});$('#jjHandShowdown')?.addEventListener('change',e=>{jjAnalysisState.showdown=e.target.value;jjAnalysisState.offset=0;jjLoadHands(true)});$('#jjHandBookmarked')?.addEventListener('change',e=>{jjAnalysisState.bookmarked=e.target.checked;jjAnalysisState.offset=0;jjLoadHands(true)});
    $('#jjHandFilterReset')?.addEventListener('click',()=>{Object.assign(jjAnalysisState,{position:'',result:'all',showdown:'all',street:'',bookmarked:false,q:'',offset:0});$('#jjHandSearch').value='';$('#jjHandPosition').value='';$('#jjHandResult').value='all';$('#jjHandStreet').value='';$('#jjHandShowdown').value='all';$('#jjHandBookmarked').checked=false;jjLoadHands(true)});$('#jjHandMore')?.addEventListener('click',()=>{jjAnalysisState.offset=jjAnalysisState.hands.length;jjLoadHands(false)});$('#jjHandList')?.addEventListener('click',e=>{const b=e.target.closest('[data-hand-open]');if(b)jjOpenHand(b.dataset.handOpen).catch(err=>toast(err.message))});
  }

  async function jjAnalysisRender(){jjEnsureAnalysisUI();return jjAnalysisLoad(true)}
  // v1.20.1 analysis request/replay stabilization
  async function jjAnalysisLoad(resetHands=false){const seq=Number(jjAnalysisState.analysisRequestSeq||0)+1,requestedRange=jjAnalysisState.range;jjAnalysisState.analysisRequestSeq=seq;if(resetHands)jjAnalysisState.handRequestSeq=Number(jjAnalysisState.handRequestSeq||0)+1;jjAnalysisState.loading=true;$('#analysisView')?.classList.add('jj-loading');try{const summary=await api(`/analysis/summary?range=${encodeURIComponent(requestedRange)}`);if(seq!==jjAnalysisState.analysisRequestSeq||requestedRange!==jjAnalysisState.range)return;jjAnalysisState.summary=summary;jjRenderAnalysisSummary(summary);if(resetHands){jjAnalysisState.offset=0;await jjLoadHands(true)}}finally{if(seq===jjAnalysisState.analysisRequestSeq){jjAnalysisState.loading=false;$('#analysisView')?.classList.remove('jj-loading')}}}

  function jjRenderAnalysisSummary(data){const o=data?.overall||{},net=Number(o.net_bb||0),bb100=o.bb_per_100;$('#jjAnalysisKpis').innerHTML=`<article class="card jj-analysis-kpi"><span>Hands</span><strong>${fmt(o.hands||0)}</strong><small>完全記録ハンド</small></article><article class="card jj-analysis-kpi"><span>Net</span><strong class="${net>=0?'positive':'negative'}">${safe(jjSigned(net))}</strong><small>実収支</small></article><article class="card jj-analysis-kpi"><span>bb / 100</span><strong class="${Number(bb100||0)>=0?'positive':'negative'}">${bb100==null?'—':safe(jjSigned(bb100))}</strong><small>EVではありません</small></article><article class="card jj-analysis-kpi"><span>Avg decision</span><strong>${o.avg_decision_seconds==null?'—':safe(String(o.avg_decision_seconds))+'s'}</strong><small>${fmt(o.decision_sample||0)} actions</small></article>`;
    $('#jjAnalysisStats').innerHTML=[jjMetric('VPIP',o.vpip),jjMetric('PFR',o.pfr),jjMetric('3bet',o.three_bet),jjMetric('Fold to 3bet',o.fold_to_three_bet),jjMetric('Steal',o.steal),jjMetric('Fold BB to Steal',o.fold_bb_to_steal),jjMetric('Flop Cbet',o.cbet),jjMetric('Fold to Cbet',o.fold_to_cbet),jjMetric('WTSD',o.wtsd),jjMetric('W$SD',o.wsd),`<article class="jj-stat"><span>Aggression Factor</span><strong>${o.aggression_factor==null?'—':safe(String(o.aggression_factor))}</strong><small>Raise+Bet / Call</small></article>`,`<article class="jj-stat"><span>Aggression %</span><strong>${o.aggression_frequency==null?'—':safe(String(o.aggression_frequency))+'%'}</strong><small>postflop actions</small></article>`].join('');
    $('#jjAnalysisSignals').innerHTML=(data.signals||[]).map(x=>`<article class="jj-signal ${safe(x.severity)}"><span>${safe(x.metric)}</span><strong>${safe(x.title)}</strong><p>${safe(x.detail)}</p></article>`).join('');jjRenderDimension('#jjAnalysisPositions',data.positions||[],'Position');jjRenderDimension('#jjAnalysisStacks',data.stack_bands||[],'Stack');jjRenderSessions(data.sessions||[]);jjRenderTrend(data.trend||[])}

  function jjRenderDimension(selector,rows,label){const box=$(selector);if(!box)return;if(!rows.length){box.innerHTML='<div class="empty">データがまだありません</div>';return}box.innerHTML=`<div class="jj-dim-row head"><span>${label}</span><span>Hands</span><span>Net</span><span>VPIP</span><span>PFR</span></div>`+rows.map(r=>`<div class="jj-dim-row"><strong>${safe(r.key)}</strong><span>${fmt(r.hands)}</span><span class="${Number(r.net_bb)>=0?'positive':'negative'}">${safe(jjSigned(r.net_bb))}</span><span>${safe(jjRate(r.vpip))}</span><span>${safe(jjRate(r.pfr))}</span></div>`).join('')}
  function jjRenderSessions(rows){const box=$('#jjAnalysisSessions');if(!box)return;box.innerHTML=rows.length?rows.map(s=>`<article class="jj-session"><div><span>${safe(jjAnalysisDate(s.started_at))}</span><strong>${safe((s.tables||[]).join(' / ')||'Session')}</strong></div><b class="${Number(s.net_bb)>=0?'positive':'negative'}">${safe(jjSigned(s.net_bb))}</b><small>${fmt(s.hands)} hands · ${s.bb_per_100==null?'—':safe(jjSigned(s.bb_per_100))}/100</small></article>`).join(''):'<div class="empty">セッションはまだありません</div>'}
  function jjRenderTrend(points){const box=$('#jjAnalysisTrend'),meta=$('#jjAnalysisTrendMeta');if(!box)return;if(!points.length){box.innerHTML='<div class="empty">ハンドが記録されると収支曲線を表示します。</div>';if(meta)meta.textContent='';return}const vals=points.map(p=>Number(p.cumulative_bb||0)),min=Math.min(0,...vals),max=Math.max(0,...vals),span=Math.max(1,max-min),w=900,h=220,pad=22;const xy=points.map((p,i)=>[pad+(w-pad*2)*(points.length===1?.5:i/(points.length-1)),pad+(h-pad*2)*(1-(Number(p.cumulative_bb)-min)/span)]),path=xy.map((p,i)=>`${i?'L':'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' '),zeroY=pad+(h-pad*2)*(1-(0-min)/span);box.innerHTML=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="累積収支グラフ"><line x1="${pad}" y1="${zeroY}" x2="${w-pad}" y2="${zeroY}" class="jj-chart-zero"/><path d="${path}" class="jj-chart-line" vector-effect="non-scaling-stroke"/></svg>`;if(meta)meta.textContent=`${jjSigned(vals.at(-1))} · ${fmt(points.length)} plotted`}

  function jjHandQuery(){const q=new URLSearchParams({limit:String(jjAnalysisState.limit),offset:String(jjAnalysisState.offset),range:jjAnalysisState.range,result:jjAnalysisState.result,showdown:jjAnalysisState.showdown});if(jjAnalysisState.position)q.set('position',jjAnalysisState.position);if(jjAnalysisState.street)q.set('street',jjAnalysisState.street);if(jjAnalysisState.bookmarked)q.set('bookmarked','true');if(jjAnalysisState.q)q.set('q',jjAnalysisState.q);return q}
  async function jjLoadHands(reset){const box=$('#jjHandList');if(!box)return;if(!reset&&jjAnalysisState.handLoading)return;if(reset){jjAnalysisState.offset=0;box.innerHTML='<div class="empty">読み込み中…</div>'}const seq=Number(jjAnalysisState.handRequestSeq||0)+1,query=jjHandQuery().toString();jjAnalysisState.handRequestSeq=seq;jjAnalysisState.handLoading=true;try{const data=await api('/analysis/hands?'+query);if(seq!==jjAnalysisState.handRequestSeq)return;jjAnalysisState.total=Number(data.total||0);jjAnalysisState.hands=reset?(data.items||[]):[...jjAnalysisState.hands,...(data.items||[])];jjRenderHands()}finally{if(seq===jjAnalysisState.handRequestSeq)jjAnalysisState.handLoading=false}}
  function jjRenderHands(){const rows=jjAnalysisState.hands,box=$('#jjHandList');if(!box)return;$('#jjHandCount').textContent=`${fmt(jjAnalysisState.total)} HANDS`;box.innerHTML=rows.length?rows.map(h=>`<article class="card jj-hand-card" data-hand-open="${safe(h.hand_id)}" tabindex="0" role="button" aria-label="ハンド ${safe(h.hand_id)} を開く"><div class="jj-hand-card-top"><div><span>${safe(jjAnalysisDate(h.completed_at))} · ${safe(h.table_name||h.table_id)}</span><strong>#${safe(String(h.hand_no||h.hand_id))} · ${safe(h.position||'—')}</strong></div><div class="jj-hand-card-result ${Number(h.net_bb)>=0?'positive':'negative'}">${safe(jjSigned(h.net_bb))}</div></div><div class="jj-hand-card-body"><div class="cards jj-mini-cards">${jjCardSet(h.cards)}</div><div class="cards jj-mini-board">${jjCardSet(h.board)}</div><div class="jj-hand-tags">${h.bookmarked?'<span>★</span>':''}${(h.tags||[]).map(t=>`<span>${safe(t)}</span>`).join('')}${h.went_showdown?'<span>SD</span>':''}${h.partial_capture?'<span>PARTIAL</span>':''}</div></div><div class="jj-hand-card-foot"><span>Effective ${Number(h.effective_stack_bb||0).toFixed(1)}bb</span><span>${safe(String(h.reached_street||'preflop').toUpperCase())}</span><b>Review →</b></div></article>`).join(''):'<div class="card empty jj-analysis-empty"><strong>分析ハンドはまだありません</strong><p>v1.20.0以降にJJ Arenaのオンライン卓で完了したハンドから、自動でここへ記録されます。</p></div>';box.querySelectorAll('[data-hand-open]').forEach(el=>el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();jjOpenHand(el.dataset.handOpen).catch(err=>toast(err.message))}}));$('#jjHandMore').classList.toggle('hidden',rows.length>=jjAnalysisState.total)}

  async function jjOpenHand(handId){const data=await api(`/analysis/hands/${encodeURIComponent(handId)}`),h=data.hand||{},players=data.players||[],actions=data.actions||[],hero=players.find(p=>Number(p.user_id)===Number(me.id))||players[0];openModal(`<div class="jj-review-shell"><div class="jj-review-head"><div><div class="eyebrow">HAND REVIEW</div><h3>${safe(h.table_name||h.table_id)} · #${safe(String(h.hand_no||h.hand_id))}</h3><p>${safe(jjAnalysisDate(h.completed_at))} · ${safe(hero?.position||'—')} · Effective ${Number(hero?.effective_stack_bb||0).toFixed(1)}bb</p></div><div class="jj-review-net ${Number(hero?.net_bb)>=0?'positive':'negative'}">${safe(jjSigned(hero?.net_bb))}</div></div><div class="jj-review-summary"><div><span>Hero</span><div class="cards">${jjCardSet(hero?.cards)}</div></div><div><span>Board</span><div class="cards">${jjCardSet(h.board)}</div></div><div><span>Result</span><strong>${safe((h.summary||{}).message||h.result_type||'—')}</strong></div></div>${h.partial_capture?'<div class="notice">このハンドは機能導入・再起動の途中から取得されたため、集計統計からは除外しています。</div>':''}<section class="jj-replayer"><div class="section-head"><div><div class="eyebrow">REPLAYER</div><h4>テーブル状態</h4></div><span id="jjReplayCounter"></span></div><div id="jjReplayStage"></div><div class="jj-replay-controls"><button class="soft" id="jjReplayPrev">← 前へ</button><button class="primary" id="jjReplayNext">次へ →</button></div></section><section class="jj-action-review"><div class="eyebrow">ACTION TIMELINE</div><div class="jj-action-timeline">${actions.map(a=>jjActionRow(a,hero)).join('')||'<div class="empty">アクション記録なし</div>'}</div></section><form id="jjHandReviewForm" class="jj-review-form stack"><label class="jj-review-bookmark"><input name="bookmarked" type="checkbox" ${data.review?.bookmarked?'checked':''}> ★ このハンドをブックマーク</label><label>タグ<input name="tags" value="${safe((data.review?.tags||[]).join(', '))}" placeholder="例: 3bet pot, bluff catch, review"></label><label>自分用メモ<textarea name="note" rows="5" maxlength="4000" placeholder="判断理由、気づき、次回確認する点">${safe(data.review?.note||'')}</textarea></label><div class="jj-review-actions"><button class="primary" type="submit">レビューを保存</button><button class="soft" type="button" id="jjExportHand">HHテキスト</button></div></form><p class="hint">相手のホールカードはショーダウンで公開された場合だけ表示します。通常のフォールドハンドでは確認できません。</p></div>`);let replayIndex=0;const renderReplay=()=>{const snaps=data.snapshots||[],snap=snaps[Math.min(replayIndex,Math.max(0,snaps.length-1))];jjRenderReplayStage(snap?.state||{},players,hero?.user_id);$('#jjReplayCounter').textContent=snaps.length?`${replayIndex+1} / ${snaps.length}`:'—';$('#jjReplayPrev').disabled=replayIndex<=0;$('#jjReplayNext').disabled=!snaps.length||replayIndex>=snaps.length-1};$('#jjReplayPrev').onclick=()=>{replayIndex=Math.max(0,replayIndex-1);renderReplay()};$('#jjReplayNext').onclick=()=>{replayIndex=Math.min((data.snapshots||[]).length-1,replayIndex+1);renderReplay()};renderReplay();$('#jjExportHand').onclick=()=>jjDownload(`/analysis/hands/${encodeURIComponent(handId)}/export.txt`,`jj-${handId}.txt`);$('#jjHandReviewForm').onsubmit=async e=>{e.preventDefault();const fd=new FormData(e.target),tags=String(fd.get('tags')||'').split(',').map(x=>x.trim()).filter(Boolean);try{await api(`/analysis/hands/${encodeURIComponent(handId)}/review`,{method:'PUT',body:JSON.stringify({bookmarked:fd.get('bookmarked')==='on',note:String(fd.get('note')||''),tags})});toast('ハンドレビューを保存しました');await jjLoadHands(true)}catch(err){toast(err.message)}}}

  function jjActionRow(a,hero){const mine=Number(a.user_id)===Number(hero?.user_id),act=String(a.action||''),label=act==='fold'?'Fold':act==='check'?'Check':act==='call'?'Call':act==='allin_call'?'Call all-in':act==='allin_raise'?'All-in raise':act==='raise'?'Raise':act,amount=act.includes('raise')||act==='raise'?` → ${a.to_bb==null?'':Number(a.to_bb).toFixed(1).replace(/\.0$/,'')}bb`:act.includes('call')?` ${Number(a.amount_bb||0).toFixed(1).replace(/\.0$/,'')}bb`:'';return `<div class="jj-action-row ${mine?'hero':''}"><span>${safe(String(a.street||'').toUpperCase())}</span><strong>${safe(a.player_name)} · ${safe(label)}${safe(amount)}</strong><small>${a.decision_seconds==null?'':`${Number(a.decision_seconds).toFixed(1)}s`}${a.timed_out?' · TIMEOUT':''}</small></div>`}
  function jjRenderReplayStage(state,players,heroId){const box=$('#jjReplayStage');if(!box)return;if(!state?.hand){box.innerHTML='<div class="empty">リプレイ用スナップショットがありません</div>';return}const cardsById=new Map(players.map(p=>[Number(p.user_id),p.cards||[]])),seats=state.seats||[],max=6,phase=String(state.hand.phase||'').toLowerCase(),showdownVisible=phase==='complete';box.innerHTML=`<div class="jj-replay-table"><div class="jj-replay-center"><div class="cards">${jjCardSet(state.hand.board||[])}</div><b>${safe(String(state.hand.phase||'').toUpperCase())}</b></div>${seats.map(p=>{const angle=(-90+Number(p.seat||0)*(360/max))*Math.PI/180,left=50+Math.cos(angle)*41,top=49+Math.sin(angle)*37,cards=cardsById.get(Number(p.user_id))||[],hero=Number(p.user_id)===Number(heroId),revealed=showdownVisible&&cards.some(c=>c!=='??'),shown=hero?cards:revealed?cards:(p.in_hand?['??','??']:[]);return `<div class="jj-replay-seat ${hero?'hero':''} ${p.folded?'folded':''}" style="left:${left}%;top:${top}%"><strong>${safe(p.name)}</strong><span>${(Number(p.stack||0)/Math.max(1,Number(state.big_blind||100))).toFixed(1)}bb</span>${shown.length?`<div class="cards jj-tiny-cards">${jjCardSet(shown)}</div>`:''}</div>`}).join('')}</div>`}
  async function jjDownload(path,filename){try{const res=await fetch('/api'+path,{headers:authHeaders()});if(!res.ok)throw new Error(`HTTP ${res.status}`);const blob=await res.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=filename;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(err){toast('出力に失敗しました: '+err.message)}}

  const jjV120RefreshView=refreshView;refreshView=async function(v){if(v==='analysis')return jjAnalysisRender();return jjV120RefreshView(v)};
  function jjV120Boot(){jjEnsureAnalysisUI()}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',jjV120Boot,{once:true});else jjV120Boot();

  // v1.20.2 websocket token privacy: same-origin session cookie authenticates WSS; no credential is placed in the URL.


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
    hub.addEventListener('click',jjV121HomeClick);
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
  function jjV121HomeClick(e){
    const go=e.target.closest('[data-jj-go]');if(go)switchView(go.dataset.jjGo);
    const hand=e.target.closest('[data-jj-hand]');if(hand){switchView('analysis');setTimeout(()=>jjOpenHand?.(hand.dataset.jjHand).catch(err=>toast(err.message)),100)}
  }
  if(typeof renderHome==='function'){
    const jjV121OldRenderHome=renderHome;
    renderHome=async function(){const r=await jjV121OldRenderHome();await jjV121LoadHomeHub();return r};
    jjV121EnsureHomeHub();
  }



  // v1.22.0 readable quiz and visual hand review.
  // Quiz difficulty belongs in the decision, not in decoding unexplained jargon.
  const jjV122RenderQuizBase=renderQuiz;
  function jjV122QuizTerms(q){
    const terms=q?.glossary||[];
    if(!terms.length)return '';
    return `<div class="jj-quiz-terms" aria-label="問題に出てくる言葉">${terms.map(x=>`<div><b>${safe(x.term)}</b><span>${safe(x.meaning)}</span></div>`).join('')}</div>`;
  }
  renderQuiz=function(){
    jjV122RenderQuizBase();
    if(quiz?.lastResult||quiz?.q?.done||!quiz?.q?.id)return;
    const prompt=$('#quizStage .jj-quiz-prompt');
    if(prompt&&!$('#quizStage .jj-quiz-terms'))prompt.insertAdjacentHTML('afterend',jjV122QuizTerms(quiz.q));
  };

  const jjV122StreetOrder=['preflop','flop','turn','river'];
  const jjV122StreetName={preflop:'PREFLOP',flop:'FLOP',turn:'TURN',river:'RIVER'};
  const jjV122ActionName={fold:'フォールド',check:'チェック',call:'コール',bet:'ベット',raise:'レイズ',allin_call:'オールインをコール',allin_raise:'オールイン',allin:'オールイン'};
  const jjV122Num=v=>Number(v||0).toFixed(1).replace(/\.0$/,'');
  const jjV122Bb=(chips,bb)=>bb>0?`${jjV122Num(Number(chips||0)/bb)}bb`:`${fmt(Number(chips||0))}`;
  function jjV122StreetBoard(board,street){const n={preflop:0,flop:3,turn:4,river:5}[street]||0;return (board||[]).slice(0,n)}
  function jjV122ActionAmount(a){
    const act=String(a.action||'');
    if(act==='raise'||act==='allin_raise')return a.to_bb==null?'':`to ${jjV122Num(a.to_bb)}bb`;
    if(act==='bet'||act==='call'||act==='allin_call'||act==='allin')return Number(a.amount_bb||0)>0?`${jjV122Num(a.amount_bb)}bb`:'';
    return '';
  }
  function jjV122ActionTimeline(actions,hero,h){
    const groups=new Map(jjV122StreetOrder.map(s=>[s,[]]));
    (actions||[]).forEach(a=>{const s=String(a.street||'preflop').toLowerCase();if(!groups.has(s))groups.set(s,[]);groups.get(s).push(a)});
    const bb=Number(h.big_blind||0),board=h.board||[];
    return [...groups.entries()].filter(([,rows])=>rows.length).map(([street,rows])=>{
      const streetBoard=jjV122StreetBoard(board,street);
      return `<section class="jj-v122-street"><header><div><span>${safe(jjV122StreetName[street]||street.toUpperCase())}</span>${streetBoard.length?`<div class="cards jj-v122-street-board">${jjCardSet(streetBoard)}</div>`:'<small>HOLE CARDS</small>'}</div><b>${rows.length} actions</b></header><div class="jj-v122-actions">${rows.map(a=>{
        const mine=Number(a.user_id)===Number(hero?.user_id),amount=jjV122ActionAmount(a),pot=jjV122Bb(a.pot_before,bb),facing=Number(a.facing_chips||0)>0?jjV122Bb(a.facing_chips,bb):'';
        return `<article class="jj-v122-action ${mine?'hero':''} ${a.timed_out?'timeout':''}"><div class="jj-v122-action-player"><span>${mine?'YOU':safe(a.player_name)}</span>${mine?`<small>${safe(a.player_name)}</small>`:''}</div><div class="jj-v122-action-main"><strong>${safe(jjV122ActionName[String(a.action||'')]||String(a.action||''))}</strong>${amount?`<b>${safe(amount)}</b>`:''}</div><div class="jj-v122-action-context"><span>Pot ${safe(pot)}</span>${facing?`<span>Facing ${safe(facing)}</span>`:''}${a.decision_seconds==null?'':`<span>${jjV122Num(a.decision_seconds)}s</span>`}${a.timed_out?'<em>TIMEOUT</em>':''}</div></article>`;
      }).join('')}</div></section>`;
    }).join('')||'<div class="empty">アクション記録なし</div>';
  }

  jjOpenHand=async function(handId){
    const data=await api(`/analysis/hands/${encodeURIComponent(handId)}`),h=data.hand||{},players=data.players||[],actions=data.actions||[],hero=players.find(p=>Number(p.user_id)===Number(me.id))||players[0]||{};
    const net=Number(hero.net_bb||0),start=Number(hero.starting_stack_bb||0),effective=Number(hero.effective_stack_bb||0),bb=Number(h.big_blind||0),result=(h.summary||{}).message||h.result_type||'—';
    const timeline=jjV122ActionTimeline(actions,hero,h);
    openModal(`<div class="jj-review-shell jj-v122-review">
      <header class="jj-v122-review-head">
        <div class="jj-v122-title"><div class="eyebrow">HAND REVIEW</div><h3>${safe(h.table_name||h.table_id)} · #${safe(String(h.hand_no||h.hand_id))}</h3><p>${safe(jjAnalysisDate(h.completed_at))}</p></div>
        <div class="jj-v122-result"><span>RESULT</span><strong class="${net>=0?'positive':'negative'}">${safe(jjSigned(net))}</strong><small>${safe(result)}</small></div>
      </header>
      <section class="jj-v122-cards-zone">
        <div class="jj-v122-hero-hand"><span>YOUR HAND</span><div class="cards">${jjCardSet(hero.cards)}</div></div>
        <div class="jj-v122-board"><span>BOARD</span><div class="cards">${jjCardSet(h.board)}</div></div>
      </section>
      <div class="jj-v122-facts">
        <div><span>POSITION</span><strong>${safe(hero.position||'—')}</strong></div>
        <div><span>START</span><strong>${start?`${jjV122Num(start)}bb`:'—'}</strong></div>
        <div><span>EFFECTIVE</span><strong>${effective?`${jjV122Num(effective)}bb`:'—'}</strong></div>
        <div><span>BLINDS</span><strong>${bb?`${fmt(h.small_blind||0)} / ${fmt(bb)}`:'—'}</strong></div>
        <div><span>REACHED</span><strong>${safe(String(h.reached_street||'preflop').toUpperCase())}</strong></div>
        <div><span>SHOWDOWN</span><strong>${h.showdown?'YES':'NO'}</strong></div>
      </div>
      ${h.partial_capture?'<div class="notice">このハンドは記録開始・再起動の途中から取得されたため、集計統計からは除外しています。</div>':''}
      <div class="jj-v122-review-grid">
        <main class="jj-v122-review-main">
          <section class="jj-v122-timeline-panel"><div class="section-head"><div><div class="eyebrow">ACTION FLOW</div><h4>アクションの流れ</h4><p>ストリートごとに、ポットとベット額を確認できます。自分の判断は強調表示しています。</p></div></div>${timeline}</section>
          <details class="jj-v122-replay-details"><summary><span><b>テーブルリプレイ</b><small>必要なときだけ盤面全体を確認</small></span><span id="jjReplayCounter"></span></summary><div class="jj-replayer"><div id="jjReplayStage"></div><div class="jj-replay-controls"><button class="soft" id="jjReplayPrev">← 前へ</button><button class="primary" id="jjReplayNext">次へ →</button></div></div></details>
        </main>
        <aside class="jj-v122-review-side">
          <form id="jjHandReviewForm" class="jj-review-form stack jj-v122-note-card">
            <div><div class="eyebrow">YOUR REVIEW</div><h4>このハンドから残すこと</h4><p>判断理由や、次に同じ状況が来たとき確認したいことを記録します。</p></div>
            <label class="jj-review-bookmark"><input name="bookmarked" type="checkbox" ${data.review?.bookmarked?'checked':''}> ★ ブックマーク</label>
            <label>タグ<input name="tags" value="${safe((data.review?.tags||[]).join(', '))}" placeholder="例: 3bet pot, bluff catch"></label>
            <label>メモ<textarea name="note" rows="8" maxlength="4000" placeholder="例：ターンで相手の続行レンジを狭く見積もりすぎた">${safe(data.review?.note||'')}</textarea></label>
            <div class="jj-review-actions"><button class="primary" type="submit">保存</button><button class="soft" type="button" id="jjExportHand">HHテキスト</button></div>
          </form>
          <p class="jj-v122-privacy">相手のホールカードは、ショーダウンで実際に公開された場合だけ表示します。</p>
        </aside>
      </div>
    </div>`);
    let replayIndex=0;
    const renderReplay=()=>{const snaps=data.snapshots||[],snap=snaps[Math.min(replayIndex,Math.max(0,snaps.length-1))];jjRenderReplayStage(snap?.state||{},players,hero?.user_id);if($('#jjReplayCounter'))$('#jjReplayCounter').textContent=snaps.length?`${replayIndex+1} / ${snaps.length}`:'—';if($('#jjReplayPrev'))$('#jjReplayPrev').disabled=replayIndex<=0;if($('#jjReplayNext'))$('#jjReplayNext').disabled=!snaps.length||replayIndex>=snaps.length-1};
    if($('#jjReplayPrev'))$('#jjReplayPrev').onclick=()=>{replayIndex=Math.max(0,replayIndex-1);renderReplay()};
    if($('#jjReplayNext'))$('#jjReplayNext').onclick=()=>{replayIndex=Math.min((data.snapshots||[]).length-1,replayIndex+1);renderReplay()};
    renderReplay();
    $('#jjExportHand').onclick=()=>jjDownload(`/analysis/hands/${encodeURIComponent(handId)}/export.txt`,`jj-${handId}.txt`);
    $('#jjHandReviewForm').onsubmit=async e=>{e.preventDefault();const fd=new FormData(e.target),tags=String(fd.get('tags')||'').split(',').map(x=>x.trim()).filter(Boolean);try{await api(`/analysis/hands/${encodeURIComponent(handId)}/review`,{method:'PUT',body:JSON.stringify({bookmarked:fd.get('bookmarked')==='on',note:String(fd.get('note')||''),tags})});toast('ハンドレビューを保存しました');await jjLoadHands(true)}catch(err){toast(err.message)}};
  };



  // v1.20.3 mobile bet-marker/call-amount hotfix.
  // legal.call_amount is returned by the server in raw table chips. The older
  // mobile renderer formatted that raw integer as BB, so 2,500 chips at a
  // 100-chip big blind was shown as 2,500bb instead of 25bb. Keep the action
  // request unchanged and fix presentation through the existing raw-chip -> BB
  // converter used elsewhere in the table UI.
  if(typeof renderActionBar==='function'){
    const jjMobileHotfixRenderActionBar=renderActionBar;
    renderActionBar=function(){
      jjMobileHotfixRenderActionBar();
      const l=tableState?.legal||{};
      if(!l.can_act||l.can_check)return;
      const callLabel=bb(Number(l.call_amount||0));
      const callButton=$('#actionBar .jj-call b');
      if(callButton)callButton.textContent=`コール ${callLabel}`;
      const contextAmount=$('#actionBar .jj-action-context b');
      if(contextAmount&&Number(l.call_amount||0)>0)contextAmount.textContent=`コール額 ${callLabel}`;
    };
  }

  // Portrait geometry: the generic seat-to-center interpolation puts the hero
  // blind/bet marker directly over the enlarged hero hole cards and puts the
  // 12-o'clock marker too close to the community cards. Move only those two
  // high-risk positions; the four side seats retain the established geometry.
  if(typeof jjBetPos==='function' && typeof jjVisualIndex==='function'){
    const jjMobileHotfixBetPos=jjBetPos;
    jjBetPos=function(actual){
      const p=jjMobileHotfixBetPos(actual);
      if(!window.matchMedia('(max-width:760px) and (orientation:portrait)').matches)return p;
      const visual=jjVisualIndex(actual);
      if(visual===0)return {left:p.left,top:56.5};
      if(visual===3)return {left:p.left,top:27};
      return p;
    };
  }


  // v1.23.0 mobile poker second-pass interaction UX.
  // Mobile-first: four-colour suits, integer stack display, explicit action
  // state, sound/haptics, safer all-ins, and latency acknowledgement.
  const JJ_V123_SOUND_KEY='jj_poker_sound_v123';
  // v1.23.0 sound storage fallback: isolated tests/private contexts may not expose localStorage.
  function jjV123StoredSound(){try{return typeof localStorage==='undefined'||localStorage.getItem(JJ_V123_SOUND_KEY)!=='0'}catch{return true}}
  let jjV123SoundEnabled=jjV123StoredSound();
  let jjV123Audio=null;
  let jjV123WasHeroTurn=false;
  let jjV123LastRunoutStage='';
  let jjV123ClockWarnedFor='';
  // v1.23.0 final mobile interaction audit.
  let jjV123AllinConfirmUntil=0;
  let jjV123AllinConfirmKey='';

  function jjV123AllinKey(action,selected){
    const hand=tableState?.hand||{};
    return `${hand.id||''}:${hand.action_seat??''}:${action}:${Number(selected||0).toFixed(2)}`;
  }

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

  const jjV123BaseRenderSeat=typeof renderSeat==='function'?renderSeat:null;
  if(jjV123BaseRenderSeat)renderSeat=function(seat){
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

    const hintItems=[];
    if(l.can_act&&!l.can_raise&&reasons.raise)hintItems.push(`レイズ不可：${reasons.raise}`);
    if(l.can_act&&l.can_check&&reasons.fold)hintItems.push('Foldは誤操作防止で非表示：Checkで無料に続行できます');
    let hints=$('#jjV123DisabledHints',bar);
    if(hintItems.length){
      if(!hints){
        status?.insertAdjacentHTML('afterend','<div id="jjV123DisabledHints" class="jj-v123-disabled-hints" aria-live="polite"></div>');
        hints=$('#jjV123DisabledHints',bar);
      }
      if(hints)hints.innerHTML=hintItems.map(x=>`<span>${safe(x)}</span>`).join('');
    }else if(hints){hints.remove()}
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
    const deadline=tableState?.hand?.action_deadline,l=tableState?.legal||{},clock=$('#jjActionClock');
    if(!deadline||!l.can_act){
      jjV123ClockWarnedFor='';
      if(clock){clock.style.removeProperty('--jj-v123-clock-pct');clock.removeAttribute('aria-label')}
      return
    }
    const sec=Math.max(0,Math.ceil((new Date(deadline)-new Date())/1000));
    if(clock){
      const pct=Math.max(0,Math.min(100,(sec/45)*100));
      clock.style.setProperty('--jj-v123-clock-pct',`${pct}%`);
      clock.setAttribute('aria-label',`アクション残り${sec}秒`);
    }
    if(sec<=10&&sec>0&&jjV123ClockWarnedFor!==String(deadline)){
      jjV123ClockWarnedFor=String(deadline);jjV123Tone('urgent');jjV123Haptic(35);
    }
  }

  function jjV123DecorateCards(){
    document.querySelectorAll('#pokerRoom .card-face.jj-four-suit').forEach(card=>card.setAttribute('data-four-suit','1'));
  }

  function jjV123ConnectionState(){
    if(typeof document==='undefined')return;
    const room=$('#pokerRoom');if(!room)return;
    let badge=$('#jjV123TableConnection',room);
    const offline=typeof navigator!=='undefined'&&navigator.onLine===false;
    const hasSocket=typeof WebSocket!=='undefined'&&typeof tableWS!=='undefined'&&!!tableWS;
    const open=hasSocket&&tableWS.readyState===WebSocket.OPEN;
    const connecting=hasSocket&&tableWS.readyState===WebSocket.CONNECTING;
    const show=!!currentTableId&&!offline&&hasSocket&&!open;
    if(!show){if(badge)badge.remove();return}
    if(!badge){
      room.insertAdjacentHTML('afterbegin','<div id="jjV123TableConnection" class="jj-v123-table-connection" role="status" aria-live="polite"></div>');
      badge=$('#jjV123TableConnection',room);
    }
    if(badge)badge.textContent=connecting?'接続中…':'再接続中 · 卓の更新を継続中';
  }

  const jjV123BaseRenderActionBar=typeof renderActionBar==='function'?renderActionBar:null;
  if(jjV123BaseRenderActionBar)renderActionBar=function(){
    jjV123BaseRenderActionBar();
    jjV123ActionState();
  };

  const jjV123BaseRenderPokerRoom=typeof renderPokerRoom==='function'?renderPokerRoom:null;
  if(jjV123BaseRenderPokerRoom)renderPokerRoom=function(){
    jjV123BaseRenderPokerRoom();
    jjV123DecorateCards();
    jjV123SoundButton();
    jjV123ActionState();
    jjV123TurnFeedback();
    jjV123ClockFeedback();
    jjV123ConnectionState();
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
      try{if(typeof localStorage!=='undefined')localStorage.setItem(JJ_V123_SOUND_KEY,jjV123SoundEnabled?'1':'0')}catch{}
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
  },true);

  // Unlock WebAudio on the first intentional table interaction. Mobile Safari
  // and Chrome require a user gesture before sound can play.
  document.addEventListener('pointerdown',e=>{
    if(e.target.closest('#pokerRoom,#actionBar,#tableControls'))jjV123AudioContext();
  },{passive:true});

  if(typeof window!=='undefined'&&typeof renderPokerRoom==='function')window.setInterval(()=>{jjV123ClockFeedback();jjV123ActionState();jjV123ConnectionState()},500);


  // v1.24.0 unified online-poker presentation layer.
  // This is the authoritative final renderer for both desktop and mobile.
  // It deliberately stops relying on generic descendants such as
  // `.jj-action-context b`, which caused the v1.23 desktop card/call collision.
  // v1.24.0 isolated-runtime and action refinement.
  const JJ_V124_DESKTOP_MQ=(typeof window!=='undefined'&&typeof window.matchMedia==='function')
    ? window.matchMedia('(min-width:761px)')
    : {matches:false,addEventListener:()=>{}};
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

})();
