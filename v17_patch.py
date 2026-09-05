from __future__ import annotations
import re
from pathlib import Path


def _sub(pattern: str, repl: str, text: str, *, flags=0, label='patch') -> str:
    out, n = re.subn(pattern, repl, text, count=1, flags=flags)
    if n != 1:
        raise RuntimeError(f'v1.7 {label} target mismatch: {n}')
    return out


def apply(root: Path) -> None:
    # Backend: Fall 2026/27 is a separate season. Summer stays archived only.
    p = root / 'server.py'
    s = p.read_text(encoding='utf-8')
    s = s.replace('version="1.6.0"', 'version="1.7.0"').replace('"version":"1.6.0"', '"version":"1.7.0"')
    s = _sub(
        r'@app\.get\("/api/rankings"\)\ndef rankings\(month: str \| None = None, user=Depends\(current_user\)\):.*?\n\n@app\.get\("/api/online/results"\)',
        '''FALL_SEASON_START = "2026-09-01"\nFALL_SEASON_END = "2027-04-01"\nFALL_SEASON_MONTHS = {"2026-09","2026-10","2026-11","2026-12","2027-01","2027-02","2027-03"}\n\n\n@app.get("/api/rankings")\ndef rankings(month: str | None = None, season: str = "fall", user=Depends(current_user)):\n    season = (season or "fall").strip().lower()\n    if season not in {"fall", "summer"}:\n        raise HTTPException(400, "season must be fall or summer")\n    if season == "fall" and month and month not in FALL_SEASON_MONTHS:\n        return []\n    club_where = "WHERE name != '運営調整'"\n    club_params: list[Any] = []\n    online_where = "WHERE COALESCE(h.voided,0)=0"\n    online_params: list[Any] = []\n    if season == "fall":\n        club_where += " AND date>=? AND date<?"\n        club_params.extend([FALL_SEASON_START, FALL_SEASON_END])\n        online_where += " AND h.played_at>=? AND h.played_at<?"\n        online_params.extend([FALL_SEASON_START, FALL_SEASON_END])\n    else:\n        club_where += " AND date<?"\n        club_params.append(FALL_SEASON_START)\n        online_where += " AND h.played_at<?"\n        online_params.append(FALL_SEASON_START)\n    if month:\n        club_where += " AND substr(date,1,7)=?"\n        club_params.append(month)\n        online_where += " AND r.month=?"\n        online_params.append(month)\n    with db.connect() as con:\n        club = con.execute(f"""\n            SELECT name, SUM(points) AS points, COUNT(*) AS games, MAX(points) AS best,\n                   SUM(CASE WHEN points>0 THEN 1 ELSE 0 END) AS wins\n            FROM entries {club_where} GROUP BY name\n        """, club_params).fetchall()\n        online = con.execute(f"""\n            SELECT r.ranking_name AS name, SUM(r.points) AS points, COUNT(*) AS games, MAX(r.points) AS best,\n                   SUM(CASE WHEN r.points>0 THEN 1 ELSE 0 END) AS wins\n            FROM online_hand_results r JOIN online_hands h ON h.hand_id=r.hand_id {online_where} GROUP BY r.ranking_name\n        """, online_params).fetchall()\n    merged: dict[str, dict[str, Any]] = {}\n    for r in club:\n        name=r["name"]; merged[name]={"name":name,"club_points":float(r["points"] or 0),"online_points":0.0,"games":int(r["games"] or 0),"online_hands":0,"best":float(r["best"] or 0),"wins":int(r["wins"] or 0)}\n    for r in online:\n        name=r["name"]; d=merged.setdefault(name,{"name":name,"club_points":0.0,"online_points":0.0,"games":0,"online_hands":0,"best":float(r["best"] or 0),"wins":0})\n        d["online_points"]=round(float(r["points"] or 0),2); d["games"]+=int(r["games"] or 0); d["online_hands"]=int(r["games"] or 0); d["best"]=max(float(d["best"] or 0),float(r["best"] or 0)); d["wins"]+=int(r["wins"] or 0)\n    rows=[]\n    for d in merged.values():\n        d["club_points"]=round(d["club_points"],2); d["points"]=round(d["club_points"]+d["online_points"],2); rows.append(d)\n    rows.sort(key=lambda x:(-x["points"],-x["best"],x["name"]))\n    return [r|{"rank":i+1,"season":season} for i,r in enumerate(rows)]\n\n\n@app.get("/api/ranking-names")\ndef ranking_names(user=Depends(current_user)):\n    with db.connect() as con:\n        entry_rows=con.execute("SELECT DISTINCT name FROM entries WHERE name!='運営調整' AND name IS NOT NULL AND name<>''").fetchall()\n        user_rows=con.execute("SELECT DISTINCT ranking_name FROM users WHERE ranking_name IS NOT NULL AND ranking_name<>''").fetchall()\n    names={str(r["name"]).strip() for r in entry_rows if r["name"]}\n    names.update(str(r["ranking_name"]).strip() for r in user_rows if r["ranking_name"])\n    return sorted(names)\n\n\n@app.get("/api/online/results")''',
        s,
        flags=re.S,
        label='season rankings',
    )
    s = _sub(
        r'@app\.get\("/api/entries"\)\ndef entries\(limit: int = 40, user=Depends\(current_user\)\):.*?return \[dict\(r\) for r in rows\]\n',
        '''@app.get("/api/entries")\ndef entries(limit: int = 40, archive: bool = False, user=Depends(current_user)):\n    limit = max(1, min(limit, 200))\n    with db.connect() as con:\n        if archive:\n            rows = con.execute("SELECT * FROM entries ORDER BY date DESC LIMIT ?", (limit,)).fetchall()\n        else:\n            rows = con.execute("SELECT * FROM entries WHERE date>=? AND date<? ORDER BY date DESC LIMIT ?", (FALL_SEASON_START, FALL_SEASON_END, limit)).fetchall()\n    return [dict(r) for r in rows]\n''',
        s,
        flags=re.S,
        label='season entries',
    )
    marker = '''    if game_type not in {"ring", "tournament"}:\n        raise HTTPException(400, "ゲーム種別が不正です")\n'''
    if marker not in s:
        raise RuntimeError('v1.7 entry date validation target mismatch')
    s = s.replace(marker, marker + '''    entry_day = (payload.date or "")[:10]\n    if not (FALL_SEASON_START <= entry_day < FALL_SEASON_END):\n        raise HTTPException(400, "後期期間（2026/9/1〜2027/3/31）の日付を入力してください")\n''', 1)
    p.write_text(s, encoding='utf-8')

    # UI: default/current ranking is Fall only; Summer is a separate reference tab.
    p = root / 'static' / 'index.html'
    s = p.read_text(encoding='utf-8')
    s = s.replace('Summer実績・活動予定・学習・戦略議論・リアルタイムNLHを一つのArenaに統合。', '後期ランキング・活動予定・学習・戦略議論・リアルタイムNLHを一つのArenaに統合。')
    s = s.replace('<div class="leader-box"><span>OVERALL #1</span>', '<div class="leader-box"><span>FALL #1</span>')
    s = s.replace('<div class="toolbar card"><div class="segmented"><button class="active" data-rank-mode="overall">総合</button><button data-rank-mode="month">月間</button></div>', '<div class="toolbar card"><div class="segmented"><button class="active" data-rank-mode="overall">後期総合</button><button data-rank-mode="month">月間</button><button data-rank-mode="archive">前期参考</button></div>')
    s = s.replace('結果は1bb=3ptとしてランキングへ自動反映されます。', '結果は1bb=3ptとして後期ランキングへ自動反映されます。')
    p.write_text(s, encoding='utf-8')

    p = root / 'static' / 'app.js'
    s = p.read_text(encoding='utf-8')
    s = s.replace("  async function loadRankings(month=null){rankings=await api('/rankings'+(month?`?month=${encodeURIComponent(month)}`:''));return rankings}", "  async function loadRankings(month=null,season='fall'){const q=new URLSearchParams({season});if(month)q.set('month',month);rankings=await api('/rankings?'+q.toString());return rankings}")
    s = s.replace("  function monthOptions(){const now=new Date(),arr=[];for(let i=0;i<12;i++){const d=new Date(now.getFullYear(),now.getMonth()-i,1);arr.push(`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`)}return arr}", "  function monthOptions(){return ['2026-09','2026-10','2026-11','2026-12','2027-01','2027-02','2027-03']}")
    s = _sub(
        r'^  async function renderRanking\(\).*$',
        '''  async function renderRanking(){const month=rankMode==='month'?$('#rankMonth').value||monthOptions()[0]:null,season=rankMode==='archive'?'summer':'fall';await loadRankings(month,season);if(!$('#rankMonth').options.length)$('#rankMonth').innerHTML=monthOptions().map(m=>`<option>${m}</option>`).join('');$$('[data-rank-mode]').forEach(b=>b.classList.toggle('active',b.dataset.rankMode===rankMode));$('#rankMonth').disabled=rankMode!=='month';const q=$('#rankSearch').value.trim().toLowerCase();const rows=rankings.filter(x=>x.name.toLowerCase().includes(q));const label=rankMode==='archive'?'前期参考':'後期';$('#podium').innerHTML=rows.slice(0,3).map((p,i)=>`<article class="podium-card card"><div class="eyebrow">${label} #${i+1}</div><strong>${safe(p.name)}</strong><b>${fmt(p.points)} pt</b><div class="hint">Club ${fmt(p.club_points)} · Online ${p.online_points>=0?'+':''}${fmt(p.online_points)}</div></article>`).join('')||`<div class="card empty">${rankMode==='archive'?'前期データは参考表示です':'後期ランキングはまだ0件です'}</div>`;$('#rankBody').innerHTML=rows.map(p=>`<tr><td class="rank-num">#${p.rank}</td><td><strong>${safe(p.name)}</strong></td><td><b>${fmt(p.points)}</b></td><td>${fmt(p.club_points)}</td><td class="${p.online_points>=0?'positive':'negative'}">${p.online_points>=0?'+':''}${fmt(p.online_points)}</td><td>${p.online_hands||0}</td></tr>`).join('')}''',
        s,
        flags=re.M,
        label='ranking UI',
    )
    s = _sub(
        r'^  async function renderPoints\(\).*$',
        '''  async function renderPoints(){if(me.role!=='admin')return;const [ents,names]=await Promise.all([api('/entries?limit=40'),api('/ranking-names')]);$('#playerNames').innerHTML=names.map(name=>`<option value="${safe(name)}"></option>`).join('');if(!$('#pointName').value)$('#pointName').value=me.name;$('#pointDate').min='2026-09-01T00:00';$('#pointDate').max='2027-03-31T23:59';$('#pointDate').value=$('#pointDate').value||isoLocal();if(!$('#pointInitial').options.length)setPointInitialOptions();pointCalc();$('#recentEntries').innerHTML=ents.map(e=>{const chips=pointDenoms.map(d=>[d,Number(e[`chip_${d}`]||0)]).filter(([,c])=>c>0).map(([d,c])=>`${d}×${c}`).join(' / ');return `<div class="list-item"><strong>${safe(e.name)} <span style="color:${e.points>=0?'var(--accent2)':'var(--danger)'}">${e.points>=0?'+':''}${fmt(e.points)}</span></strong><div class="hint">${dateFmt(e.date,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})} · ${safe(e.game||e.game_type)} · 残り ${fmt(e.remaining)}${chips?` · ${safe(chips)}`:''}</div></div>`}).join('')||'<div class="empty">後期の入力はまだありません</div>'}''',
        s,
        flags=re.M,
        label='point UI season data',
    )
    s = _sub(
        r'^  async function renderMembers\(\).*$',
        '''  async function renderMembers(){if(me.role!=='admin')return;const [members,names]=await Promise.all([api('/admin/members'),api('/ranking-names')]);const opts=names.map(name=>`<option value="${safe(name)}">${safe(name)}</option>`).join('');$('#memberList').innerHTML=members.map(m=>`<article class="card member-card"><div class="member-head"><div><strong>${safe(m.name)}</strong><div class="hint">${m.role==='admin'?'ADMIN':'MEMBER'} · Ranking: ${safe(m.ranking_name||m.name)}</div></div><span class="status-badge ${m.disabled?'danger-badge':'ok-badge'}">${m.disabled?'DISABLED':'ACTIVE'}</span></div><label>ランキング名<select data-ranking-name="${m.id}"><option value="${safe(m.ranking_name||m.name)}">${safe(m.ranking_name||m.name)}</option>${opts}</select></label><div class="button-row"><button class="soft" data-reset-pin="${m.id}">PINリセット</button>${m.role!=='admin'?`<button class="ghost" data-member-action="${m.disabled?'enable':'disable'}" data-member-id="${m.id}">${m.disabled?'利用再開':'利用停止'}</button>`:''}</div></article>`).join('')}''',
        s,
        flags=re.M,
        label='member ranking names',
    )
    p.write_text(s, encoding='utf-8')

    p = root / 'static' / 'sw.js'
    s = p.read_text(encoding='utf-8').replace('jj-arena-live-v6', 'jj-arena-live-v7')
    p.write_text(s, encoding='utf-8')
