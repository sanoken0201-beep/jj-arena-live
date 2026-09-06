from __future__ import annotations
from pathlib import Path
import re


def apply(root: Path) -> None:
    _patch_db(root / 'db.py')
    _patch_server(root / 'server.py')
    _patch_index(root / 'static' / 'index.html')
    _patch_appjs(root / 'static' / 'app.js')
    _patch_styles(root / 'static' / 'styles.css')
    _patch_sw(root / 'static' / 'sw.js')


def _patch_db(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    if '\nimport re\n' not in s and not s.startswith('import re\n'):
        anchor='import os\n'
        if anchor in s:
            s=s.replace(anchor,anchor+'import re\n',1)
        else:
            s='import re\n'+s
    if 'def cleanup_duplicate_kenichiro_users' in s:
        return
    marker = 'def init_db():'
    if marker not in s:
        raise RuntimeError('v1.10 db init marker not found')
    helper = r'''def cleanup_duplicate_kenichiro_users() -> int:
    """Keep the admin ケンイチロウ account and remove older duplicate member accounts.

    Foreign-key ownership is reassigned to the retained admin account before deletion.
    Sessions belonging to duplicates are deleted rather than transferred.
    The operation is idempotent and returns the number of removed users.
    """
    target = "ケンイチロウ"
    with connect() as con:
        admin = con.execute(
            "SELECT id FROM users WHERE name=? AND role='admin' ORDER BY id LIMIT 1",
            (target,),
        ).fetchone()
        if not admin:
            return 0
        keep_id = int(admin["id"])
        dup_rows = con.execute(
            "SELECT id FROM users WHERE name=? AND id<>? ORDER BY id",
            (target, keep_id),
        ).fetchall()
        dup_ids = [int(r["id"]) for r in dup_rows]
        if not dup_ids:
            return 0

        refs: list[tuple[str, str]] = []
        if IS_POSTGRES:
            rows = con.execute("""
                SELECT DISTINCT tc.table_name, kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name=kcu.constraint_name AND tc.table_schema=kcu.table_schema
                JOIN information_schema.constraint_column_usage ccu
                  ON tc.constraint_name=ccu.constraint_name AND tc.table_schema=ccu.table_schema
                WHERE tc.constraint_type='FOREIGN KEY'
                  AND ccu.table_schema='public' AND ccu.table_name='users' AND ccu.column_name='id'
            """).fetchall()
            refs = [(str(r["table_name"]), str(r["column_name"])) for r in rows]
        else:
            tables = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            for row in tables:
                table = str(row["name"])
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table):
                    continue
                for fk in con.execute(f'PRAGMA foreign_key_list("{table}")').fetchall():
                    fd = dict(fk)
                    if str(fd.get("table")) == "users" and str(fd.get("to")) == "id":
                        refs.append((table, str(fd.get("from"))))

        refs = [
            (table, col) for table, col in refs
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table)
            and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", col)
        ]
        for dup_id in dup_ids:
            for table, col in refs:
                if table == "sessions":
                    con.execute(f'DELETE FROM "{table}" WHERE "{col}"=?', (dup_id,))
                else:
                    con.execute(f'UPDATE "{table}" SET "{col}"=? WHERE "{col}"=?', (keep_id, dup_id))
            con.execute("DELETE FROM users WHERE id=?", (dup_id,))
        return len(dup_ids)


'''
    s = s.replace(marker, helper + marker, 1)
    p.write_text(s, encoding='utf-8')


def _patch_server(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    s = s.replace('version="1.9.0"', 'version="1.10.0"').replace('"version":"1.9.0"', '"version":"1.10.0"')
    s = s.replace('request.url.query == "v=19"', 'request.url.query == "v=20"')
    if 'cleanup_duplicate_kenichiro_users()' not in s:
        pattern = re.compile(r'(?m)^(\s*)db\.init_db\(\)\s*$')
        match = pattern.search(s)
        if not match:
            raise RuntimeError('v1.10 db.init_db call not found')
        indent = match.group(1)
        replacement = (
            f'{indent}db.init_db()\n'
            f'{indent}_removed_duplicate_accounts = db.cleanup_duplicate_kenichiro_users()\n'
            f'{indent}if _removed_duplicate_accounts:\n'
            f'{indent}    print(f"JJ_ACCOUNT_CLEANUP removed_duplicates={{_removed_duplicate_accounts}}")'
        )
        s = pattern.sub(replacement, s, count=1)
    p.write_text(s, encoding='utf-8')


def _patch_index(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    s = s.replace('?v=19', '?v=20')
    p.write_text(s, encoding='utf-8')


def _patch_appjs(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    if 'v1.10 mobile-first operations' in s:
        return
    marker = '})();'
    pos = s.rfind(marker)
    if pos < 0:
        raise RuntimeError('v1.10 app.js closing marker not found')
    addon = r'''

  // v1.10 mobile-first operations. Desktop layout remains unchanged.
  const mobileBreakpoint=760;
  const quickPointDenoms=[1,5,10,25,100,500];
  const quickPointInitials={
    ring:[{value:450,label:'450 · 1-3-3'},{value:900,label:'900 · 2-5-5'},{value:2000,label:'2000 · 5-10-10'}],
    tournament:[{value:400,label:'400 · Tournament'},{value:1000,label:'1000 · Tournament'}]
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
    const card=document.createElement('section');card.id='mobileQuickPointCard';card.className='mobile-only mobile-quick-point card';
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
    dock.addEventListener('click',e=>{const v=e.target.closest('[data-mobile-view]')?.dataset.mobileView;if(v){switchView(v);closeMobileMore();mobileScrollTop();return}if(e.target.closest('[data-mobile-more]'))openMobileMore()});
  }
  function ensureMobileMore(){
    if($('#mobileMore'))return;
    const overlay=document.createElement('div');overlay.id='mobileMore';overlay.className='mobile-only mobile-more hidden';overlay.innerHTML='<div class="mobile-more-backdrop" data-close-mobile-more></div><section class="mobile-more-sheet" role="dialog" aria-modal="true" aria-label="その他のメニュー"><div class="sheet-grab"></div><div class="mobile-more-head"><div><div class="eyebrow">MENU</div><h3>その他</h3></div><button class="sheet-close" data-close-mobile-more aria-label="閉じる">×</button></div><div id="mobileMoreLinks" class="mobile-more-links"></div></section>';
    document.body.appendChild(overlay);overlay.addEventListener('click',e=>{if(e.target.closest('[data-close-mobile-more]'))closeMobileMore();const b=e.target.closest('[data-more-view]');if(b){switchView(b.dataset.moreView);closeMobileMore();mobileScrollTop()}});
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
    $$('#mobileDock [data-mobile-view]').forEach(b=>b.classList.toggle('active',b.dataset.mobileView===currentView));
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
'''
    s = s[:pos] + addon + s[pos:]
    p.write_text(s, encoding='utf-8')


def _patch_styles(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    if 'v1.10 smartphone redesign' in s:
        return
    s += r'''

/* v1.10 smartphone redesign — desktop intentionally unchanged */
.mobile-only{display:none!important}
.admin-home-point{display:inline-flex}
@media (max-width:760px){
  :root{--mobile-dock-h:68px;--mobile-top-h:64px}
  html{scroll-behavior:auto;scroll-padding-top:calc(var(--mobile-top-h) + 10px);background:#f3f7f4}
  body{overflow-x:hidden;overscroll-behavior-y:none;background:linear-gradient(180deg,#f7faf8 0,#f2f6f3 48%,#edf3ef 100%);padding:0!important}
  body.mobile-sheet-open{overflow:hidden}
  .mobile-only{display:block!important}
  .sidebar{display:none!important}
  .app-shell{display:block!important;min-height:100dvh;width:100%!important}
  .main{display:block!important;width:100%!important;min-width:0!important;max-width:none!important;margin:0!important;padding:0 12px calc(var(--mobile-dock-h) + env(safe-area-inset-bottom) + 22px)!important}
  .topbar{position:sticky!important;top:0;z-index:50;margin:0 -12px 12px!important;padding:calc(9px + env(safe-area-inset-top)) 14px 9px!important;min-height:var(--mobile-top-h);background:rgba(247,250,248,.92)!important;border-bottom:1px solid rgba(32,67,51,.08);backdrop-filter:blur(18px) saturate(1.35);-webkit-backdrop-filter:blur(18px) saturate(1.35)}
  .topbar>div:first-child{min-width:0}.topbar #viewEyebrow{display:none}.topbar h2{font-size:1.22rem!important;line-height:1.15;margin:0!important;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .top-actions{gap:7px!important}.user-chip{min-width:0!important;padding:6px 9px!important;border-radius:12px!important;background:#fff!important;box-shadow:none!important;border:1px solid rgba(27,72,50,.09)!important}.user-chip span,.user-chip b,#wallet,.logout-top{display:none!important}.user-chip strong{max-width:105px;font-size:.75rem!important;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .view{min-width:0!important;animation:none!important}.view:not(.active-view){display:none!important}
  .section-head{align-items:flex-end!important;gap:10px;margin:18px 1px 10px!important}.section-head h3{font-size:1.2rem!important;margin:.1rem 0!important}.section-head .eyebrow{font-size:.62rem!important}
  .card{border-radius:18px!important;box-shadow:0 8px 28px rgba(26,55,42,.055)!important;border-color:rgba(34,75,55,.09)!important}
  #homeView>.hero-grid{display:grid!important;grid-template-columns:1fr!important;gap:10px!important;margin-top:0!important}
  #homeView .hero{padding:18px!important;min-height:0!important;display:grid!important;grid-template-columns:1fr!important;gap:16px!important;background:linear-gradient(145deg,#163d31,#235944)!important;color:#fff!important}
  #homeView .hero h3{font-size:1.72rem!important;line-height:1.12!important;margin:.35rem 0 .65rem!important}#homeView .hero p{font-size:.82rem!important;line-height:1.65!important;opacity:.88}
  #homeView .hero .button-row{display:none!important}.leader-box{width:100%!important;min-height:auto!important;padding:13px 15px!important;border-radius:14px!important;display:grid!important;grid-template-columns:1fr auto!important;align-items:center!important}.leader-box span{grid-column:1/3}.leader-box strong{font-size:1.12rem!important}.leader-box b{font-size:1rem!important}
  #homeView .kpi{display:none!important}
  .top-grid{display:flex!important;gap:9px!important;overflow-x:auto!important;margin:0 -12px!important;padding:2px 12px 12px!important;scroll-snap-type:x mandatory;scrollbar-width:none}.top-grid::-webkit-scrollbar{display:none}.top-player{flex:0 0 min(72vw,280px)!important;scroll-snap-align:start;padding:15px!important;min-height:128px!important}
  .home-columns{display:grid!important;grid-template-columns:1fr!important;gap:10px!important}.home-columns .panel{padding:16px!important}
  .weekly-study-home{margin-top:18px!important}.weekly-study-home .study-grid{display:flex!important;overflow-x:auto!important;margin:0 -12px!important;padding:2px 12px 10px!important;scroll-snap-type:x mandatory;scrollbar-width:none}.weekly-study-home .study-card{flex:0 0 84vw!important;scroll-snap-align:start!important}
  .mobile-quick-point{margin:0 0 12px!important;padding:16px!important;background:linear-gradient(160deg,#fff 0,#f8fbf9 100%)!important;border:1px solid rgba(17,115,78,.16)!important;box-shadow:0 12px 34px rgba(20,86,59,.08)!important}
  .mobile-section-title{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:13px}.mobile-section-title h3{font-size:1.3rem;margin:.12rem 0 0}.mobile-section-title>span{padding:5px 8px;border-radius:999px;background:#e7f6ef;color:#087a55;font-size:.6rem;font-weight:900;letter-spacing:.1em}
  .quick-point-form{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:9px!important}.quick-point-form label{min-width:0!important;font-size:.68rem!important;color:var(--muted,#65736c)!important;font-weight:800!important}.quick-point-form input,.quick-point-form select{width:100%!important;min-width:0!important;margin-top:5px!important;padding:10px 9px!important;min-height:44px!important;border-radius:11px!important;background:#fff!important;font-size:16px!important}
  .quick-player,.quick-date,.quick-chip-block,.quick-point-total,.quick-submit{grid-column:1/-1!important}.quick-chip-block{padding:11px!important;border:1px solid rgba(34,75,55,.10);border-radius:14px;background:#f6faf7}.quick-chip-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:9px;font-size:.75rem}.quick-chip-head span{font-size:.62rem;color:var(--muted,#65736c)}
  .quick-chip-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}.quick-chip-grid label{padding:8px 7px 7px;border-radius:10px;background:#fff;border:1px solid rgba(33,72,54,.08);text-align:center}.quick-chip-grid label span{display:block;color:#263d32;font-size:.67rem}.quick-chip-grid input{text-align:center!important;margin-top:3px!important;padding:7px 3px!important;min-height:40px!important;font-weight:850!important}
  .quick-point-total{display:flex!important;align-items:center;justify-content:space-between;padding:11px 12px;border-radius:12px;background:#143c30;color:#fff}.quick-point-total span{font-size:.72rem;opacity:.82}.quick-point-total span b{font-size:.9rem}.quick-point-total>strong{font-size:1.18rem;font-variant-numeric:tabular-nums}.quick-submit{min-height:50px!important;border-radius:13px!important;font-size:.9rem!important;font-weight:900!important}
  .admin-home-point{display:none!important}
  #rankingView .toolbar{position:sticky!important;top:calc(var(--mobile-top-h) + env(safe-area-inset-top) - 1px);z-index:38;display:grid!important;grid-template-columns:1fr!important;gap:8px!important;margin:0 -4px 11px!important;padding:10px!important;border-radius:15px!important;background:rgba(250,252,251,.94)!important;backdrop-filter:blur(14px)}
  #rankingView .segmented{display:flex!important;overflow-x:auto;scrollbar-width:none}#rankingView .segmented button{flex:1 0 auto;min-height:40px!important;white-space:nowrap}
  #rankMonth,#rankSearch{width:100%!important;min-height:44px!important;font-size:16px!important}
  #podium{display:grid!important;grid-template-columns:1fr!important;gap:8px!important}.podium-card{display:grid!important;grid-template-columns:62px 1fr auto!important;align-items:center!important;gap:8px!important;padding:13px 14px!important}.podium-card .eyebrow{grid-column:1}.podium-card strong{grid-column:2;font-size:1rem!important}.podium-card>b{grid-column:3;font-size:1rem!important}.podium-card .hint{grid-column:2/4!important}
  #rankingView .table-card{padding:0!important;background:transparent!important;border:0!important;box-shadow:none!important;overflow:visible!important}#rankingView table,#rankingView tbody{display:block!important;width:100%!important}#rankingView thead{display:none!important}#rankingView tr{display:grid!important;grid-template-columns:50px minmax(0,1fr) auto!important;align-items:center!important;gap:7px!important;margin-bottom:7px!important;padding:12px 13px!important;background:#fff;border:1px solid rgba(34,75,55,.09);border-radius:14px;box-shadow:0 5px 18px rgba(26,55,42,.04)}#rankingView td{display:block!important;padding:0!important;border:0!important;min-width:0}#rankingView td:nth-child(n+4){display:none!important}#rankingView td:nth-child(1){font-size:.72rem!important;color:#6a776f}#rankingView td:nth-child(2){overflow:hidden;text-overflow:ellipsis;white-space:nowrap}#rankingView td:nth-child(3){font-weight:900;font-variant-numeric:tabular-nums;text-align:right}
  #tablesView .section-head{margin-top:4px!important}.table-rule{font-size:.62rem!important}.table-lobby{display:grid!important;grid-template-columns:1fr!important;gap:10px!important}.lobby-card{padding:17px!important}.room-head{display:grid!important;grid-template-columns:auto 1fr!important;gap:10px!important;align-items:center!important}.room-meta{grid-column:1/3!important;font-size:.68rem!important}.poker-layout{display:grid!important;grid-template-columns:1fr!important;gap:10px!important}.poker-zone{padding:8px!important;margin:0 -6px!important;border-radius:18px!important}.poker-table{min-height:440px!important;height:min(62dvh,540px)!important;border-radius:32%/18%!important}.table-side{padding:12px!important}.action-bar{position:sticky!important;bottom:calc(var(--mobile-dock-h) + env(safe-area-inset-bottom) + 5px);z-index:36;margin:8px -2px 0!important;padding:9px!important;border-radius:15px!important;background:rgba(250,252,251,.96)!important;box-shadow:0 -8px 28px rgba(15,40,29,.12)!important;backdrop-filter:blur(12px)}.action-bar button{min-height:48px!important;font-weight:900!important}.table-controls{gap:7px!important}.table-controls button{min-height:44px!important}
  .cards .card-face{transform:scale(.94)}.seat{max-width:118px!important}.seat-name{max-width:94px!important;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .two-col,.schedule-grid,.news-grid,.lab-grid{display:grid!important;grid-template-columns:1fr!important;gap:10px!important}.panel{padding:16px!important}.form-grid{grid-template-columns:1fr!important}.chip-count-grid{grid-template-columns:repeat(3,minmax(0,1fr))!important}.threads{gap:10px!important}.thread{padding:16px!important}
  dialog{width:100%!important;max-width:none!important;max-height:86dvh!important;margin:auto 0 0!important;border-radius:24px 24px 0 0!important;padding:20px 16px calc(18px + env(safe-area-inset-bottom))!important;animation:mobileSheetIn .18s ease-out!important}dialog::backdrop{background:rgba(8,24,17,.42)!important;backdrop-filter:blur(2px)}@keyframes mobileSheetIn{from{transform:translateY(18px);opacity:.7}to{transform:none;opacity:1}}
  .mobile-dock{position:fixed!important;left:8px;right:8px;bottom:calc(7px + env(safe-area-inset-bottom));height:var(--mobile-dock-h);z-index:80;display:flex!important;align-items:stretch;padding:5px;border-radius:21px;background:rgba(20,51,40,.96);box-shadow:0 16px 42px rgba(7,27,18,.28);backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px)}
  .mobile-dock button{appearance:none;border:0;background:transparent;color:rgba(255,255,255,.62);flex:1;min-width:0;min-height:56px!important;border-radius:16px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:1px;padding:4px 2px;font:inherit}.mobile-dock button b{font-size:1.18rem;line-height:1;font-weight:700}.mobile-dock button span{font-size:.57rem;font-weight:800;letter-spacing:.02em}.mobile-dock button.active{color:#fff;background:rgba(255,255,255,.10)}.mobile-dock .mobile-point-nav{position:relative;color:#11392c!important;background:#bff0d8!important;margin:-10px 3px 3px;min-height:62px!important;border-radius:19px;box-shadow:0 8px 22px rgba(44,186,126,.28)}.mobile-dock .mobile-point-nav b{font-size:1.5rem}.mobile-dock .mobile-point-nav.hidden{display:none!important}
  .mobile-more{position:fixed!important;inset:0;z-index:100;display:block!important}.mobile-more.hidden{display:none!important}.mobile-more-backdrop{position:absolute;inset:0;background:rgba(5,20,13,.43);backdrop-filter:blur(2px)}.mobile-more-sheet{position:absolute;left:0;right:0;bottom:0;max-height:80dvh;overflow:auto;padding:8px 14px calc(20px + env(safe-area-inset-bottom));border-radius:26px 26px 0 0;background:#f9fbfa;box-shadow:0 -18px 50px rgba(8,28,18,.22);animation:mobileSheetIn .18s ease-out}.sheet-grab{width:38px;height:4px;border-radius:99px;background:#cbd6d0;margin:2px auto 12px}.mobile-more-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}.mobile-more-head h3{margin:.1rem 0;font-size:1.35rem}.sheet-close{width:44px;height:44px;border:0;border-radius:50%;background:#eaf0ec;font-size:1.5rem}.mobile-more-links{display:grid;gap:7px}.mobile-more-links button{display:flex;align-items:center;justify-content:space-between;width:100%;min-height:54px;padding:0 15px;border:1px solid rgba(34,75,55,.08);border-radius:14px;background:#fff;color:#1d3027;font:inherit;font-size:.88rem;font-weight:800}.mobile-more-links button b{font-size:1.25rem;color:#839088}.mobile-more-links .danger-link{color:#a53b3b}
  input,select,textarea{font-size:16px!important;max-width:100%!important}img,svg,canvas{max-width:100%}*{min-width:0}
}
@media (max-width:390px){
  .main{padding-left:9px!important;padding-right:9px!important}.topbar{margin-left:-9px!important;margin-right:-9px!important}.quick-chip-grid{grid-template-columns:repeat(2,minmax(0,1fr))!important}.poker-table{min-height:405px!important}.mobile-dock{left:5px;right:5px}.mobile-dock button span{font-size:.54rem}
}
'''
    p.write_text(s, encoding='utf-8')


def _patch_sw(p: Path) -> None:
    s = p.read_text(encoding='utf-8')
    for old in ('jj-arena-live-v7', 'jj-arena-live-v8', 'jj-arena-live-v9'):
        s = s.replace(old, 'jj-arena-live-v10')
    p.write_text(s, encoding='utf-8')
