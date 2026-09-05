from __future__ import annotations
import os, json, secrets, hashlib, random, itertools, sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from contextlib import contextmanager
from fastapi import FastAPI, HTTPException, Header, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

DB_URL=os.getenv('DATABASE_URL','').strip(); DB_PATH=Path(os.getenv('JJ_DB_PATH','/tmp/jj-arena.db'))
IS_PG=bool(DB_URL)

def now(): return datetime.now(timezone.utc).isoformat()
class PG:
    def __init__(self,c): self.c=c
    def execute(self,q,p=()):
        q=q.replace('?', '%s').replace('INSERT OR IGNORE INTO','INSERT INTO')
        if 'INSERT INTO historical' in q and 'OR IGNORE' not in q and 'ON CONFLICT' not in q and q.startswith('INSERT INTO historical'): q += ' ON CONFLICT DO NOTHING'
        cur=self.c.cursor(); cur.execute(q,p); return cur
@contextmanager
def con():
    if IS_PG:
        import psycopg
        from psycopg.rows import dict_row
        raw=psycopg.connect(DB_URL,row_factory=dict_row); c=PG(raw)
        try: yield c; raw.commit()
        except: raw.rollback(); raise
        finally: raw.close()
    else:
        raw=sqlite3.connect(DB_PATH,check_same_thread=False); raw.row_factory=sqlite3.Row
        try: yield raw; raw.commit()
        finally: raw.close()

def hpass(p,s=None):
    s=s or secrets.token_bytes(16); d=hashlib.pbkdf2_hmac('sha256',p.encode(),s,150000); return f'{s.hex()}${d.hex()}'
def vpass(p,e):
    s,d=e.split('$'); return secrets.compare_digest(hashlib.pbkdf2_hmac('sha256',p.encode(),bytes.fromhex(s),150000).hex(),d)

HIST={
'Luke':{'2026-06':378,'2026-07':2242},'Mahen':{'2026-06':1702,'2026-07':-465},'MeiLi':{'2026-06':-952,'2026-07':2618},'Pekka':{'2026-06':-858,'2026-07':855},'Tuomas':{'2026-06':-450,'2026-07':-900},'アツシ':{'2026-06':-451},'アユム':{'2026-06':1317,'2026-07':39,'2026-08':2},'イズミ':{'2026-06':-671,'2026-07':-164,'2026-08':1115},'エイデン':{'2026-06':-4424,'2026-07':-324},'カイジ':{'2026-06':-596},'カズキ':{'2026-06':-300},'ガク':{'2026-06':55,'2026-07':59,'2026-08':2096},'キミ':{'2026-06':-639,'2026-07':364},'ケイセイ':{'2026-06':-467},'ケイタロウ':{'2026-07':1015},'ケンイチロウ':{'2026-04':0,'2026-06':689,'2026-07':-84,'2026-08':-2323},'ゲンヤ':{'2026-06':-168},'コウタロウ':{'2026-06':-2698},'コウヨウ':{'2026-06':361},'シオン':{'2026-07':-809,'2026-08':186},'ショウタ':{'2026-06':-387},'ジンギョム':{'2026-06':717,'2026-07':-937},'ソラミ':{'2026-06':-866,'2026-07':-803,'2026-08':-449},'タイセイ':{'2026-06':746,'2026-07':-1324},'タクマ':{'2026-06':1529},'テルアキ':{'2026-06':-718},'トミー':{'2026-06':-898,'2026-07':-2018},'トモマサ':{'2026-06':3800,'2026-07':-519},'トモリ':{'2026-06':2427,'2026-07':216,'2026-08':-2674},'ハルキ':{'2026-06':277,'2026-07':906,'2026-08':2169},'バサ':{'2026-06':-955},'ムツミ':{'2026-06':645,'2026-07':26},'ユウイチロウ':{'2026-06':428,'2026-07':289},'ユウマ':{'2026-06':1178},'ヨシハル':{'2026-06':1025,'2026-07':4532,'2026-08':1126},'リュウセイ':{'2026-06':3190,'2026-07':1305,'2026-08':147},'レオン':{'2026-06':-1268},'ワディ':{'2026-06':741,'2026-07':1076,'2026-08':-239}}

def init():
    idcol='BIGSERIAL PRIMARY KEY' if IS_PG else 'INTEGER PRIMARY KEY AUTOINCREMENT'
    sql=f'''CREATE TABLE IF NOT EXISTS users(id {idcol},name TEXT,email TEXT UNIQUE,ph TEXT,role TEXT,chips INTEGER,xp INTEGER);CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER,expires TEXT);CREATE TABLE IF NOT EXISTS historical(name TEXT,month TEXT,points INTEGER,PRIMARY KEY(name,month));CREATE TABLE IF NOT EXISTS point_entries(id {idcol},name TEXT,month TEXT,points INTEGER,created TEXT);CREATE TABLE IF NOT EXISTS schedules(id {idcol},date TEXT,time TEXT,room TEXT,title TEXT,note TEXT,creator TEXT);CREATE TABLE IF NOT EXISTS announcements(id {idcol},kind TEXT,title TEXT,body TEXT,url TEXT,date TEXT);CREATE TABLE IF NOT EXISTS threads(id {idcol},title TEXT,body TEXT,author TEXT,created TEXT);CREATE TABLE IF NOT EXISTS replies(id {idcol},thread_id INTEGER,body TEXT,author TEXT,created TEXT);'''
    with con() as c:
        for s in sql.split(';'):
            if s.strip(): c.execute(s)
        for n,ms in HIST.items():
            for m,p in ms.items():
                try: c.execute('INSERT OR IGNORE INTO historical(name,month,points) VALUES (?,?,?)',(n,m,p))
                except Exception: pass
        if c.execute('SELECT COUNT(*) c FROM users').fetchone()['c']==0:
            ap=os.getenv('JJ_ADMIN_PASSWORD','admin2026'); ae=os.getenv('JJ_ADMIN_EMAIL','admin@jj.local'); an=os.getenv('JJ_ADMIN_NAME','ケンイチロウ')
            c.execute('INSERT INTO users(name,email,ph,role,chips,xp) VALUES (?,?,?,?,?,?)',(an,ae,hpass(ap),'admin',20000,0))
init()

def auth(a):
    if not a or not a.lower().startswith('bearer '): raise HTTPException(401,'login required')
    t=a[7:].strip()
    with con() as c: r=c.execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>?',(t,now())).fetchone()
    if not r: raise HTTPException(401,'session expired')
    return dict(r)
def session(uid):
    t=secrets.token_urlsafe(24); ex=(datetime.now(timezone.utc)+timedelta(days=30)).isoformat()
    with con() as c: c.execute('INSERT INTO sessions(token,user_id,expires) VALUES (?,?,?)',(t,uid,ex))
    return t

R='23456789TJQKA'; S='cdhs'; RV={r:i+2 for i,r in enumerate(R)}
def deck(): d=[r+s for r in R for s in S]; random.SystemRandom().shuffle(d); return d
def five(cs):
    vs=sorted([RV[c[0]] for c in cs],reverse=True); suits=[c[1] for c in cs]; cnt={v:vs.count(v) for v in set(vs)}; u=sorted(cnt,reverse=True); sh=5 if u==[14,5,4,3,2] else (u[0] if len(u)==5 and u[0]-u[-1]==4 else 0); fl=len(set(suits))==1
    groups=sorted(((n,v) for v,n in cnt.items()),reverse=True)
    if fl and sh:return(8,sh)
    if groups[0][0]==4:return(7,groups[0][1],max(v for v in vs if v!=groups[0][1]))
    if sorted(cnt.values())==[2,3]:return(6,max(v for v,n in cnt.items() if n==3),max(v for v,n in cnt.items() if n==2))
    if fl:return(5,*vs)
    if sh:return(4,sh)
    if groups[0][0]==3:return(3,groups[0][1],*sorted([v for v in vs if v!=groups[0][1]],reverse=True))
    ps=sorted([v for v,n in cnt.items() if n==2],reverse=True)
    if len(ps)>=2:return(2,ps[0],ps[1],max(v for v in vs if v not in ps[:2]))
    if ps:return(1,ps[0],*sorted([v for v in vs if v!=ps[0]],reverse=True))
    return(0,*vs)
def seven(cs):return max(five(list(x)) for x in itertools.combinations(cs,5))
TABLE={'id':'main','name':'JJ Main Table','sb':5,'bb':10,'max':6,'button':-1,'seats':[],'hand':None,'hand_no':0,'last':''}

def seated(uid): return next((p for p in TABLE['seats'] if p['uid']==uid),None)
def nextseat(after, pred=lambda p:True):
    occ={p['seat']:p for p in TABLE['seats']}
    for i in range(1,TABLE['max']+1):
        x=(after+i)%TABLE['max']; p=occ.get(x)
        if p and pred(p): return x
    return None
def pdata(viewer):
    h=TABLE['hand']; out={k:v for k,v in TABLE.items() if k not in ('seats','hand')}; out['seats']=[]
    for p in TABLE['seats']:
        q={k:v for k,v in p.items() if k!='cards'}; q['cards']=p['cards'] if viewer==p['uid'] or (h and h.get('done')) else (['??','??'] if p.get('in') else []) ; out['seats'].append(q)
    if h: out['hand']={k:v for k,v in h.items() if k!='deck'}
    else: out['hand']=None
    return out
def start_hand():
    ps=[p for p in TABLE['seats'] if p['stack']>0]
    if len(ps)<2: raise ValueError('2 players required')
    if TABLE['hand'] and not TABLE['hand'].get('done'): raise ValueError('hand active')
    for p in TABLE['seats']: p.update({'in':p['stack']>0,'fold':False,'allin':False,'bet':0,'put':0,'cards':[]})
    TABLE['button']=nextseat(TABLE['button'],lambda p:p['stack']>0); b=TABLE['button']; sb=b if len(ps)==2 else nextseat(b,lambda p:p['stack']>0); bb=nextseat(sb,lambda p:p['stack']>0); d=deck()
    for _ in range(2):
        for p in sorted(ps,key=lambda p:(p['seat']-b)%TABLE['max']): p['cards'].append(d.pop())
    def take(p,a): a=min(a,p['stack']);p['stack']-=a;p['bet']+=a;p['put']+=a;p['allin']=p['stack']==0
    sp=next(p for p in ps if p['seat']==sb); bp=next(p for p in ps if p['seat']==bb); take(sp,TABLE['sb']);take(bp,TABLE['bb'])
    TABLE['hand_no']+=1; TABLE['hand']={'phase':'preflop','board':[],'deck':d,'current':max(sp['bet'],bp['bet']),'minraise':TABLE['bb'],'acted':[],'turn':nextseat(bb,lambda p:p['in'] and not p['allin']),'done':False,'log':[f"Hand #{TABLE['hand_no']}"]}

def act(uid,a,amount=None):
    h=TABLE['hand']; p=seated(uid)
    if not h or h['done'] or not p or p['seat']!=h['turn']: raise ValueError('not your turn')
    call=max(0,h['current']-p['bet'])
    def take(x): x=min(x,p['stack']);p['stack']-=x;p['bet']+=x;p['put']+=x;p['allin']=p['stack']==0
    a=a.lower()
    if a=='fold':p['fold']=True;h['acted'].append(uid)
    elif a=='check':
        if call:raise ValueError('cannot check')
        h['acted'].append(uid)
    elif a=='call':
        if not call:raise ValueError('nothing to call')
        take(call);h['acted'].append(uid)
    elif a in ('raise','allin'):
        target=p['bet']+p['stack'] if a=='allin' else int(amount or 0)
        if target<=h['current'] or target>p['bet']+p['stack']:raise ValueError('invalid raise')
        inc=target-h['current']
        if inc<h['minraise'] and target!=p['bet']+p['stack']:raise ValueError('raise too small')
        take(target-p['bet']);h['current']=target
        if inc>=h['minraise']:h['minraise']=inc;h['acted']=[uid]
        elif uid not in h['acted']:h['acted'].append(uid)
    else:raise ValueError('unknown action')
    progress(p['seat'])
def progress(after):
    h=TABLE['hand']; live=[p for p in TABLE['seats'] if p.get('in') and not p.get('fold')]
    if len(live)==1:
        live[0]['stack']+=sum(p.get('put',0) for p in TABLE['seats']);h['done']=True;TABLE['last']=f"{live[0]['name']} wins";return
    can=[p for p in live if not p.get('allin') and p['stack']>0]
    complete=all(p['uid'] in h['acted'] and p['bet']==h['current'] for p in can)
    if not complete:
        h['turn']=nextseat(after,lambda p:p.get('in') and not p.get('fold') and not p.get('allin') and (p['uid'] not in h['acted'] or p['bet']!=h['current']));return
    phase=h['phase']; d=h['deck']
    for p in TABLE['seats']:p['bet']=0
    h['current']=0;h['acted']=[]
    if phase=='preflop': d.pop();h['board'] += [d.pop(),d.pop(),d.pop()];h['phase']='flop'
    elif phase=='flop': d.pop();h['board'].append(d.pop());h['phase']='turn'
    elif phase=='turn': d.pop();h['board'].append(d.pop());h['phase']='river'
    else:return showdown()
    can=[p for p in live if not p.get('allin') and p['stack']>0]
    if len(can)<=1:return progress(TABLE['button'])
    h['turn']=nextseat(TABLE['button'],lambda p:p.get('in') and not p.get('fold') and not p.get('allin'))
def showdown():
    h=TABLE['hand']; live=[p for p in TABLE['seats'] if p.get('in') and not p.get('fold')]
    while len(h['board'])<5:
        h['deck'].pop();h['board'].append(h['deck'].pop())
    scores={p['uid']:seven(p['cards']+h['board']) for p in live}; best=max(scores.values()); ws=[p for p in live if scores[p['uid']]==best]; pot=sum(p.get('put',0) for p in TABLE['seats']); share,rem=divmod(pot,len(ws))
    for i,p in enumerate(ws):p['stack']+=share+(1 if i<rem else 0)
    TABLE['last']=', '.join(p['name'] for p in ws)+' wins';h['done']=True;h['turn']=None

app=FastAPI(title='JJ Arena Live')
class Cred(BaseModel): name:str='';email:str;password:str
class Point(BaseModel):name:str;month:str;points:int
class Schedule(BaseModel):date:str;time:str;room:str;title:str='JJ活動';note:str=''
class Ann(BaseModel):kind:str='club';title:str;body:str;url:str='';date:str
class Thread(BaseModel):title:str;body:str
class Reply(BaseModel):body:str
class Seat(BaseModel):seat:int;buyin:int
class Action(BaseModel):action:str;amount:int|None=None

@app.get('/api/health')
def health():return {'ok':True,'service':'JJ Arena Live'}
@app.post('/api/signup')
def signup(x:Cred):
    if len(x.password)<6:raise HTTPException(400,'password too short')
    try:
        with con() as c:
            cur=c.execute('INSERT INTO users(name,email,ph,role,chips,xp) VALUES (?,?,?,?,?,?)',(x.name or x.email.split('@')[0],x.email.lower(),hpass(x.password),'member',10000,0)); uid=cur.lastrowid if not IS_PG else c.execute('SELECT id FROM users WHERE email=?',(x.email.lower(),)).fetchone()['id']
    except Exception:raise HTTPException(409,'email already registered')
    return {'token':session(uid)}
@app.post('/api/login')
def login(x:Cred):
    with con() as c:r=c.execute('SELECT * FROM users WHERE email=?',(x.email.lower(),)).fetchone()
    if not r or not vpass(x.password,r['ph']):raise HTTPException(401,'invalid login')
    return {'token':session(r['id']),'user':dict(r)}
@app.get('/api/me')
def me(authorization:str|None=Header(None)):return auth(authorization)
@app.get('/api/rankings')
def rankings(month:str|None=None,authorization:str|None=Header(None)):
    auth(authorization); q='''SELECT name,SUM(points) points FROM (SELECT name,month,points FROM historical UNION ALL SELECT name,month,points FROM point_entries) x''';p=[]
    if month:q+=' WHERE month=?';p=[month]
    q+=' GROUP BY name ORDER BY points DESC,name';
    with con() as c:rs=c.execute(q,p).fetchall()
    return [dict(r)|{'rank':i+1} for i,r in enumerate(rs)]
@app.post('/api/points')
def points(x:Point,authorization:str|None=Header(None)):
    u=auth(authorization)
    if u['role']!='admin':raise HTTPException(403,'admin only')
    with con() as c:c.execute('INSERT INTO point_entries(name,month,points,created) VALUES (?,?,?,?)',(x.name,x.month,x.points,now()))
    return {'ok':True}
@app.get('/api/schedules')
def schedules(authorization:str|None=Header(None)):
    auth(authorization)
    with con() as c:return [dict(r) for r in c.execute('SELECT * FROM schedules ORDER BY date,time').fetchall()]
@app.post('/api/schedules')
def adds(x:Schedule,authorization:str|None=Header(None)):
    u=auth(authorization)
    with con() as c:c.execute('INSERT INTO schedules(date,time,room,title,note,creator) VALUES (?,?,?,?,?,?)',(x.date,x.time,x.room,x.title,x.note,u['name']))
    return {'ok':True}
@app.get('/api/announcements')
def anns(authorization:str|None=Header(None)):
    auth(authorization)
    with con() as c:return [dict(r) for r in c.execute('SELECT * FROM announcements ORDER BY date DESC').fetchall()]
@app.post('/api/announcements')
def adda(x:Ann,authorization:str|None=Header(None)):
    u=auth(authorization)
    if u['role']!='admin':raise HTTPException(403,'admin only')
    with con() as c:c.execute('INSERT INTO announcements(kind,title,body,url,date) VALUES (?,?,?,?,?)',(x.kind,x.title,x.body,x.url,x.date))
    return {'ok':True}
@app.get('/api/threads')
def threads(authorization:str|None=Header(None)):
    auth(authorization)
    with con() as c:
        ts=[dict(r) for r in c.execute('SELECT * FROM threads ORDER BY id DESC').fetchall()]
        for t in ts:t['replies']=[dict(r) for r in c.execute('SELECT * FROM replies WHERE thread_id=? ORDER BY id',(t['id'],)).fetchall()]
        return ts
@app.post('/api/threads')
def addt(x:Thread,authorization:str|None=Header(None)):
    u=auth(authorization)
    with con() as c:c.execute('INSERT INTO threads(title,body,author,created) VALUES (?,?,?,?)',(x.title,x.body,u['name'],now()))
    return {'ok':True}
@app.post('/api/threads/{tid}/reply')
def addr(tid:int,x:Reply,authorization:str|None=Header(None)):
    u=auth(authorization)
    with con() as c:c.execute('INSERT INTO replies(thread_id,body,author,created) VALUES (?,?,?,?)',(tid,x.body,u['name'],now()))
    return {'ok':True}
@app.get('/api/table')
def table(authorization:str|None=Header(None)):
    u=auth(authorization);return pdata(u['id'])
@app.post('/api/table/seat')
def seat(x:Seat,authorization:str|None=Header(None)):
    u=auth(authorization)
    if seated(u['id']):raise HTTPException(400,'already seated')
    if any(p['seat']==x.seat for p in TABLE['seats']):raise HTTPException(400,'occupied')
    if not 500<=x.buyin<=5000 or x.buyin>u['chips']:raise HTTPException(400,'invalid buyin')
    TABLE['seats'].append({'uid':u['id'],'name':u['name'],'seat':x.seat,'stack':x.buyin,'cards':[],'in':False,'fold':False,'allin':False,'bet':0,'put':0})
    with con() as c:c.execute('UPDATE users SET chips=chips-? WHERE id=?',(x.buyin,u['id']))
    return pdata(u['id'])
@app.post('/api/table/start')
def st(authorization:str|None=Header(None)):
    u=auth(authorization)
    if not seated(u['id']) and u['role']!='admin':raise HTTPException(403,'sit first')
    try:start_hand()
    except ValueError as e:raise HTTPException(400,str(e))
    return pdata(u['id'])
@app.post('/api/table/action')
def ac(x:Action,authorization:str|None=Header(None)):
    u=auth(authorization)
    try:act(u['id'],x.action,x.amount)
    except ValueError as e:raise HTTPException(400,str(e))
    return pdata(u['id'])

CLIENTS=set()
@app.websocket('/ws')
async def ws(w:WebSocket):
    await w.accept();CLIENTS.add(w)
    try:
        while True: await w.receive_text(); await w.send_text('pong')
    except WebSocketDisconnect:CLIENTS.discard(w)

HTML=r'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>JJ Arena Live</title><style>
:root{--bg:#07110d;--card:#0e1d16;--line:#23372d;--lime:#d5ff72;--txt:#eef8f1;--muted:#8fa69a}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 20% 0,#153224,#07110d 38%);color:var(--txt);font:15px system-ui}button,input,select,textarea{font:inherit}button{background:var(--lime);border:0;border-radius:10px;padding:10px 14px;font-weight:800;cursor:pointer}.ghost{background:#17291f;color:#dce8df}.wrap{max-width:1180px;margin:auto;padding:18px}.top{display:flex;justify-content:space-between;align-items:center;gap:12px}.brand{font-size:26px;font-weight:900}.brand b{color:var(--lime)}.nav{display:flex;gap:8px;flex-wrap:wrap}.nav button.active{outline:2px solid var(--lime)}.card{background:rgba(14,29,22,.93);border:1px solid var(--line);border-radius:18px;padding:16px;margin:12px 0}.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:12px}.c6{grid-column:span 6}.c4{grid-column:span 4}.c8{grid-column:span 8}h2,h3{margin:0 0 12px}.muted{color:var(--muted)}table{width:100%;border-collapse:collapse}td,th{padding:10px;border-bottom:1px solid var(--line);text-align:left}.podium{font-size:18px;font-weight:800}.tablefelt{min-height:420px;border-radius:50%;border:10px solid #173c2b;background:#0b5b39;position:relative;margin:20px auto;max-width:760px;box-shadow:inset 0 0 50px #041f14}.seat{position:absolute;background:#0a1510;border:2px solid #365d49;border-radius:14px;padding:9px;min-width:120px;text-align:center}.s0{left:42%;bottom:-10px}.s1{left:4%;bottom:70px}.s2{left:2%;top:60px}.s3{left:42%;top:-15px}.s4{right:2%;top:60px}.s5{right:4%;bottom:70px}.board{position:absolute;left:50%;top:48%;transform:translate(-50%,-50%);text-align:center}.cards{font-size:23px;letter-spacing:5px}.actions{display:flex;gap:8px;justify-content:center;flex-wrap:wrap}.login{max-width:420px;margin:70px auto}.login input,.field{width:100%;padding:11px;border-radius:10px;border:1px solid #294637;background:#09150f;color:white;margin:5px 0}.hidden{display:none}.pill{display:inline-block;padding:4px 8px;border-radius:99px;background:#1d3528;color:var(--lime)}@media(max-width:760px){.c6,.c4,.c8{grid-column:span 12}.tablefelt{min-height:360px}.seat{min-width:86px;font-size:12px}.top{align-items:flex-start;flex-direction:column}}
</style></head><body><div id="login" class="wrap login"><div class="card"><div class="brand">JJ <b>ARENA</b> LIVE</div><p class="muted">Ranking · Club · Poker Lab · Realtime NLH</p><input id="email" class="field" placeholder="email"><input id="pw" class="field" type="password" placeholder="password"><input id="name" class="field" placeholder="表示名（新規登録時）"><div style="display:flex;gap:8px"><button onclick="login()">ログイン</button><button class="ghost" onclick="signup()">新規登録</button></div><p id="err" class="muted"></p></div></div><div id="app" class="hidden"><div class="wrap"><div class="top"><div class="brand">JJ <b>ARENA</b> LIVE</div><div id="me"></div></div><div class="nav" id="nav"></div><div id="view"></div></div></div><script>
let token=localStorage.jjtoken||'',user=null,tab='home';const A=(u,o={})=>fetch(u,{...o,headers:{'Content-Type':'application/json','Authorization':'Bearer '+token,...(o.headers||{})}}).then(async r=>{if(!r.ok)throw new Error((await r.json()).detail||r.status);return r.json()});
async function login(){try{let r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:email.value,password:pw.value,name:''})}).then(r=>r.json());if(!r.token)throw Error(r.detail);token=r.token;localStorage.jjtoken=token;boot()}catch(e){err.textContent=e.message}}async function signup(){try{let r=await fetch('/api/signup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:email.value,password:pw.value,name:name.value})}).then(r=>r.json());if(!r.token)throw Error(r.detail);token=r.token;localStorage.jjtoken=token;boot()}catch(e){err.textContent=e.message}}
async function boot(){try{user=await A('/api/me');document.getElementById('login').classList.add('hidden');app.classList.remove('hidden');me.innerHTML=`<span class=pill>${user.name}</span> ${user.chips} chips`;nav.innerHTML=['home','ranking','schedule','news','poker','study','talk'].map(x=>`<button class="ghost ${x==tab?'active':''}" onclick="tab='${x}';render()">${{home:'Home',ranking:'Ranking',schedule:'Schedule',news:'News',poker:'Play',study:'Poker Lab',talk:'Open Table'}[x]}</button>`).join('');render()}catch(e){localStorage.removeItem('jjtoken')}}
async function render(){[...nav.children].forEach((b,i)=>b.classList.toggle('active',['home','ranking','schedule','news','poker','study','talk'][i]==tab));if(tab=='home')return home();if(tab=='ranking')return rank();if(tab=='schedule')return sched();if(tab=='news')return news();if(tab=='poker')return poker();if(tab=='study')return study();if(tab=='talk')return talk()}
async function home(){let r=await A('/api/rankings');view.innerHTML=`<div class=grid><div class="card c8"><h2>Season Race</h2>${r.slice(0,5).map((x,i)=>`<p class=podium>#${i+1} ${x.name} <b>${x.points}</b> pt</p>`).join('')}</div><div class="card c4"><h2>Next Action</h2><p>活動予定・オンライン卓・学習を1つに統合。</p><button onclick="tab='poker';render()">テーブルへ</button></div></div>`}
async function rank(){let r=await A('/api/rankings');view.innerHTML=`<div class=card><h2>総合ランキング</h2><table><tr><th>#</th><th>Player</th><th>Points</th></tr>${r.map(x=>`<tr><td>${x.rank}</td><td>${x.name}</td><td><b>${x.points}</b></td></tr>`).join('')}</table></div>`}
async function sched(){let r=await A('/api/schedules');view.innerHTML=`<div class=grid><div class="card c8"><h2>活動予定</h2>${r.length?r.map(x=>`<p><b>${x.date} ${x.time}</b> · ${x.room} · ${x.title}</p>`).join(''):'まだ予定はありません'}</div><div class="card c4"><h3>予定追加</h3><input id=sd class=field type=date><input id=st class=field type=time><input id=sr class=field placeholder=教室><input id=sti class=field placeholder=タイトル value="JJ活動"><button onclick="adds()">追加</button></div></div>`}async function adds(){await A('/api/schedules',{method:'POST',body:JSON.stringify({date:sd.value,time:st.value,room:sr.value,title:sti.value,note:''})});sched()}
async function news(){let r=await A('/api/announcements');view.innerHTML=`<div class=card><h2>お知らせ / External Events</h2>${r.map(x=>`<article><span class=pill>${x.kind}</span><h3>${x.title}</h3><p>${x.body}</p></article>`).join('')||'告知はまだありません'}</div>`}
function card(c){if(!c)return'';if(c=='??')return'🂠';let m={c:'♣',d:'♦',h:'♥',s:'♠'};return c[0]+m[c[1]]}
async function poker(){let t=await A('/api/table');let seats=t.seats.map(p=>`<div class="seat s${p.seat}"><b>${p.name}</b><br>${p.stack} chips<br><span class=cards>${(p.cards||[]).map(card).join(' ')}</span></div>`).join('');let h=t.hand,board=h?(h.board||[]).map(card).join(' '):'';view.innerHTML=`<div class=card><h2>JJ Main Table <span class=pill>${t.last||'play-money'}</span></h2><div class=tablefelt>${seats}<div class=board><div class=cards>${board}</div><p>${h&&!h.done?h.phase:'Waiting'}</p></div></div><div class=actions>${[0,1,2,3,4,5].map(i=>`<button class=ghost onclick="sit(${i})">Seat ${i+1}</button>`).join('')}<button onclick="start()">Deal</button><button class=ghost onclick="act('fold')">Fold</button><button class=ghost onclick="act('check')">Check</button><button class=ghost onclick="act('call')">Call</button><button class=ghost onclick="raisebet()">Raise</button><button onclick="act('allin')">All-in</button></div></div>`;setTimeout(()=>{if(tab=='poker')poker()},3500)}async function sit(s){let b=prompt('Buy-in 500–5000','1000');if(b)try{await A('/api/table/seat',{method:'POST',body:JSON.stringify({seat:s,buyin:+b})});poker()}catch(e){alert(e.message)}}async function start(){try{await A('/api/table/start',{method:'POST'});poker()}catch(e){alert(e.message)}}async function act(a,amount=null){try{await A('/api/table/action',{method:'POST',body:JSON.stringify({action:a,amount})});poker()}catch(e){alert(e.message)}}function raisebet(){let n=prompt('Raise-to amount','50');if(n)act('raise',+n)}
function study(){view.innerHTML=`<div class=grid><div class="card c6"><h2>Pot Odds Sprint</h2><p>Pot 100。相手が50 bet。あなたは50 call。必要勝率は？</p><button onclick="alert('正解: 25%（50 / 200）')">答えを見る</button></div><div class="card c6"><h2>Daily Spot</h2><p>BB vs BTN SRP。フロップ A♠7♦2♣。どのレンジが小さいC-betを使いやすいか考えてみよう。</p></div></div>`}
async function talk(){let r=await A('/api/threads');view.innerHTML=`<div class=grid><div class="card c8"><h2>Open Table</h2>${r.map(t=>`<article><h3>${t.title}</h3><p>${t.body}</p><small>${t.author}</small>${(t.replies||[]).map(x=>`<p>↳ ${x.body} <small>${x.author}</small></p>`).join('')}<button class=ghost onclick="reply(${t.id})">返信</button></article>`).join('')}</div><div class="card c4"><input id=tt class=field placeholder=タイトル><textarea id=tb class=field placeholder=内容></textarea><button onclick="postThread()">投稿</button></div></div>`}async function postThread(){await A('/api/threads',{method:'POST',body:JSON.stringify({title:tt.value,body:tb.value})});talk()}async function reply(id){let b=prompt('返信');if(b){await A(`/api/threads/${id}/reply`,{method:'POST',body:JSON.stringify({body:b})});talk()}}
if(token)boot();</script></body></html>'''
@app.get('/')
def index():return HTMLResponse(HTML)
