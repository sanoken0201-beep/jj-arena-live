from __future__ import annotations
import re
from pathlib import Path


def _sub(pattern: str, repl: str, text: str, *, flags=0, label='patch') -> str:
    out, n = re.subn(pattern, repl, text, count=1, flags=flags)
    if n != 1:
        raise RuntimeError(f'v1.6 {label} target mismatch: {n}')
    return out


def apply(root: Path) -> None:
    # Backend: denomination counts are the source of truth; remaining is derived server-side.
    p=root/'server.py'; s=p.read_text(encoding='utf-8')
    s=s.replace('version="1.5.0"','version="1.6.0"').replace('"version":"1.5.0"','"version":"1.6.0"')
    s=_sub(r'class PointEntry\(BaseModel\):.*?\n\n\nclass ScheduleIn', '''class PointEntry(BaseModel):
    name: str
    date: str
    reentries: int = Field(default=0, ge=0, le=50)
    initial: int = Field(gt=0)
    game_type: str = "ring"
    chip_1: int = Field(default=0, ge=0, le=100000)
    chip_5: int = Field(default=0, ge=0, le=100000)
    chip_10: int = Field(default=0, ge=0, le=100000)
    chip_25: int = Field(default=0, ge=0, le=100000)
    chip_100: int = Field(default=0, ge=0, le=100000)
    chip_500: int = Field(default=0, ge=0, le=100000)


class ScheduleIn''', s, flags=re.S, label='PointEntry')
    s=_sub(r'@app\.post\("/api/entries"\)\ndef add_entry\(payload: PointEntry, user=Depends\(admin_user\)\):.*?\n\n\n@app\.get\("/api/schedules"\)', '''@app.post("/api/entries")
def add_entry(payload: PointEntry, user=Depends(admin_user)):
    game_type = payload.game_type.strip().lower()
    if game_type not in {"ring", "tournament"}:
        raise HTTPException(400, "ゲーム種別が不正です")
    ring_initials = {450: "450 / blind 1-3-3", 900: "900 / blind 2-5-5", 2000: "2000 / blind 5-10-10"}
    tournament_initials = {400: "400 / tournament", 1000: "1000 / tournament"}
    initial_map = ring_initials if game_type == "ring" else tournament_initials
    if payload.initial not in initial_map:
        raise HTTPException(400, "初期点はフォームの選択肢から選んでください")
    counts = {1: payload.chip_1, 5: payload.chip_5, 10: payload.chip_10, 25: payload.chip_25, 100: payload.chip_100, 500: payload.chip_500}
    remaining = sum(value * count for value, count in counts.items())
    points = remaining - (payload.reentries + 1) * payload.initial
    eid = "live-" + uuid.uuid4().hex
    game = initial_map[payload.initial]
    with db.connect() as con:
        con.execute(
            "INSERT INTO entries(id,date,name,remaining,reentries,initial,points,game,game_type,source,created_by,created_at,chip_1,chip_5,chip_10,chip_25,chip_100,chip_500) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (eid, payload.date, payload.name.strip(), remaining, payload.reentries, payload.initial, points, game, game_type, "JJ Arena Live", user["id"], db.utcnow(), payload.chip_1, payload.chip_5, payload.chip_10, payload.chip_25, payload.chip_100, payload.chip_500),
        )
    return {"id": eid, "remaining": remaining, "points": points, "chips": {str(k): v for k, v in counts.items()}}


@app.get("/api/schedules")''', s, flags=re.S, label='entries endpoint')
    p.write_text(s,encoding='utf-8')

    # Database: preserve the individual chip counts for audit/history while keeping old entries valid.
    p=root/'db.py'; s=p.read_text(encoding='utf-8')
    if 'def _ensure_entry_chip_columns' not in s:
        s=s.replace('def init_db():', '''def _ensure_entry_chip_columns(con):
    cols = _columns(con, "entries")
    if not cols:
        return
    for name in ("chip_1", "chip_5", "chip_10", "chip_25", "chip_100", "chip_500"):
        if name not in cols:
            con.execute(f"ALTER TABLE entries ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0")


def init_db():''',1)
    s=_sub(r'    CREATE TABLE IF NOT EXISTS entries \([^\n]+\);', '    CREATE TABLE IF NOT EXISTS entries (id TEXT PRIMARY KEY, date TEXT NOT NULL, name TEXT NOT NULL, remaining INTEGER NOT NULL, reentries INTEGER NOT NULL, initial INTEGER NOT NULL, points INTEGER NOT NULL, game TEXT, game_type TEXT, source TEXT, created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL, chip_1 INTEGER NOT NULL DEFAULT 0, chip_5 INTEGER NOT NULL DEFAULT 0, chip_10 INTEGER NOT NULL DEFAULT 0, chip_25 INTEGER NOT NULL DEFAULT 0, chip_100 INTEGER NOT NULL DEFAULT 0, chip_500 INTEGER NOT NULL DEFAULT 0);', s, label='entries schema')
    s=s.replace('_migrate_legacy_beta(con); con.executescript(schema); _ensure_access_columns(con); _ensure_online_hand_columns(con)', '_migrate_legacy_beta(con); con.executescript(schema); _ensure_access_columns(con); _ensure_online_hand_columns(con); _ensure_entry_chip_columns(con)')
    p.write_text(s,encoding='utf-8')

    # UI: same entry flow as the Google Form, with a 500-point denomination added.
    p=root/'static'/'index.html'; s=p.read_text(encoding='utf-8')
    point_card='''<article class="card panel"><div class="eyebrow">ADMIN</div><h3>公式ポイント入力</h3><p>Googleフォームと同じく、残ったチップを額面ごとの枚数で入力します。空欄は0枚として計算されます。</p><form id="pointForm" class="form-grid"><label>プレイヤー<input id="pointName" required list="playerNames"></label><datalist id="playerNames"></datalist><label>日付<input id="pointDate" type="datetime-local" required></label><label>ゲーム<select id="pointGame"><option value="ring">リング</option><option value="tournament">トーナメント</option></select></label><label>初期チップ<select id="pointInitial" required></select></label><label>リエントリー回数<input id="pointReentries" type="number" value="0" min="0" step="1" inputmode="numeric" required></label><div class="chip-entry full"><div class="chip-entry-head"><strong>残りチップ枚数</strong><span>未入力 = 0枚</span></div><div class="chip-count-grid"><label>1点<input id="pointChip1" class="point-chip-count" type="number" min="0" step="1" inputmode="numeric" placeholder="0"></label><label>5点<input id="pointChip5" class="point-chip-count" type="number" min="0" step="1" inputmode="numeric" placeholder="0"></label><label>10点<input id="pointChip10" class="point-chip-count" type="number" min="0" step="1" inputmode="numeric" placeholder="0"></label><label>25点<input id="pointChip25" class="point-chip-count" type="number" min="0" step="1" inputmode="numeric" placeholder="0"></label><label>100点<input id="pointChip100" class="point-chip-count" type="number" min="0" step="1" inputmode="numeric" placeholder="0"></label><label>500点<input id="pointChip500" class="point-chip-count" type="number" min="0" step="1" inputmode="numeric" placeholder="0"></label></div></div><div class="calc calc-stack"><span>残りチップ合計</span><strong id="pointRemainingPreview">0</strong><span>ランキング加算点</span><strong id="pointPreview">0 pt</strong></div><button class="primary full">記録</button></form></article>'''
    s=_sub(r'<article class="card panel"><div class="eyebrow">ADMIN</div><h3>公式ポイント入力</h3>.*?</article>', point_card, s, flags=re.S, label='point card')
    p.write_text(s,encoding='utf-8')

    p=root/'static'/'app.js'; s=p.read_text(encoding='utf-8')
    helper='''  const pointDenoms=[1,5,10,25,100,500];
  const pointInitialOptions={ring:[{value:450,label:'450 / blind 1-3-3'},{value:900,label:'900 / blind 2-5-5'},{value:2000,label:'2000 / blind 5-10-10'}],tournament:[{value:400,label:'400 / tournament'},{value:1000,label:'1000 / tournament'}]};
  function setPointInitialOptions(){const game=$('#pointGame')?.value||'ring',sel=$('#pointInitial');if(!sel)return;const previous=Number(sel.value||0),opts=pointInitialOptions[game]||pointInitialOptions.ring;sel.innerHTML=opts.map(o=>`<option value="${o.value}">${o.label}</option>`).join('');if(opts.some(o=>o.value===previous))sel.value=String(previous);else sel.value=String(game==='ring'?450:400);pointCalc()}
  function chipCount(value){const n=Number(value||0);return Number.isFinite(n)&&n>=0?Math.floor(n):0}
  function pointCalc(){const initial=Number($('#pointInitial')?.value||0),re=chipCount($('#pointReentries')?.value),rem=pointDenoms.reduce((sum,d)=>sum+d*chipCount($(`#pointChip${d}`)?.value),0),p=rem-(re+1)*initial;if($('#pointRemainingPreview'))$('#pointRemainingPreview').textContent=fmt(rem);if($('#pointPreview'))$('#pointPreview').textContent=(p>=0?'+':'')+fmt(p)+' pt';return {remaining:rem,points:p}}'''
    s=_sub(r'^  function pointCalc\(\).*$', helper, s, flags=re.M, label='point calculator')
    render="""  async function renderPoints(){if(me.role!=='admin')return;const [ents,r]=await Promise.all([api('/entries?limit=40'),api('/rankings')]);$('#playerNames').innerHTML=r.map(x=>`<option value=\"${safe(x.name)}\"></option>`).join('');if(!$('#pointName').value)$('#pointName').value=me.name;$('#pointDate').value=$('#pointDate').value||isoLocal();if(!$('#pointInitial').options.length)setPointInitialOptions();pointCalc();$('#recentEntries').innerHTML=ents.map(e=>{const chips=pointDenoms.map(d=>[d,Number(e[`chip_${d}`]||0)]).filter(([,c])=>c>0).map(([d,c])=>`${d}×${c}`).join(' / ');return `<div class=\"list-item\"><strong>${safe(e.name)} <span style=\"color:${e.points>=0?'var(--accent2)':'var(--danger)'}\">${e.points>=0?'+':''}${fmt(e.points)}</span></strong><div class=\"hint\">${dateFmt(e.date,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})} · ${safe(e.game||e.game_type)} · 残り ${fmt(e.remaining)}${chips?` · ${safe(chips)}`:''}</div></div>`}).join('')}"""
    s=_sub(r'^  async function renderPoints\(\).*$', render, s, flags=re.M, label='renderPoints')
    listeners="""    $('#rankMonth').addEventListener('change',()=>rankMode==='month'&&renderRanking());$('#rankSearch').addEventListener('input',()=>renderRanking());$('#memberList').addEventListener('change',async e=>{const sel=e.target.closest('[data-ranking-name]');if(!sel)return;try{await patch(`/admin/members/${sel.dataset.rankingName}`,{ranking_name:sel.value});toast('ランキング名を更新しました')}catch(err){toast(err.message)}});$('#pointGame').addEventListener('change',setPointInitialOptions);['pointInitial','pointReentries'].forEach(id=>$('#'+id).addEventListener('input',pointCalc));$$('.point-chip-count').forEach(inp=>inp.addEventListener('input',pointCalc));setPointInitialOptions();"""
    s=_sub(r"^    \$\('#rankMonth'\).*pointCalc\)\);$", listeners, s, flags=re.M, label='point listeners')
    submit="""    $('#pointForm').addEventListener('submit',async e=>{e.preventDefault();try{const payload={name:$('#pointName').value.trim(),date:$('#pointDate').value,reentries:chipCount($('#pointReentries').value),initial:Number($('#pointInitial').value),game_type:$('#pointGame').value};pointDenoms.forEach(d=>payload[`chip_${d}`]=chipCount($(`#pointChip${d}`).value));const result=await post('/entries',payload);toast(`公式ポイントを記録しました（残り ${fmt(result.remaining)} / ${result.points>=0?'+':''}${fmt(result.points)}pt）`);$$('.point-chip-count').forEach(inp=>inp.value='');$('#pointReentries').value='0';$('#pointDate').value=isoLocal();pointCalc();await renderPoints()}catch(err){toast(err.message)}});"""
    s=_sub(r"^    \$\('#pointForm'\).*;$", submit, s, flags=re.M, label='point submit')
    p.write_text(s,encoding='utf-8')

    p=root/'static'/'styles.css'; s=p.read_text(encoding='utf-8')
    if 'v1.6 Google-Form-style chip counting' not in s:
        s += '''\n/* v1.6 Google-Form-style chip counting */\n.chip-entry{border:1px solid var(--line);background:#fbfdfc;border-radius:16px;padding:14px}.chip-entry-head{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:12px}.chip-entry-head span{font-size:.72rem;color:var(--muted)}.chip-count-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.chip-count-grid label{background:#fff;border:1px solid #dbe7df;border-radius:12px;padding:10px}.chip-count-grid input{text-align:center;font-size:1rem;font-weight:800}.calc-stack{display:grid;grid-template-columns:1fr auto;gap:7px 16px;align-items:center}.calc-stack strong{text-align:right}.calc-stack strong:first-of-type{color:var(--text)}\n@media(max-width:760px){.chip-count-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.chip-entry{padding:12px}.chip-entry-head{align-items:flex-start;flex-direction:column;gap:3px}}\n'''
    p.write_text(s,encoding='utf-8')

    p=root/'static'/'sw.js'; s=p.read_text(encoding='utf-8').replace('jj-arena-live-v5','jj-arena-live-v6'); p.write_text(s,encoding='utf-8')
