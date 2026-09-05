from __future__ import annotations
from pathlib import Path
import base64, hashlib, io, tarfile

ASSET_SHA256 = "b8a9cbd3e33724ec9fa5b807721d1c3b37a8bbb4f7bc7e44e82497836d7071ab"


def apply(root: Path, assets_dir: Path) -> None:
    _patch_server(root / 'server.py')
    _patch_appjs(root / 'static' / 'app.js')
    parts=sorted(assets_dir.glob('part*.b64'))
    if len(parts)!=5:
        raise RuntimeError(f'v1.8 assets incomplete: {len(parts)}')
    raw=base64.b64decode(''.join(p.read_text(encoding='utf-8').strip() for p in parts),validate=True)
    if hashlib.sha256(raw).hexdigest()!=ASSET_SHA256:
        raise RuntimeError('v1.8 asset checksum mismatch')
    static=(root/'static').resolve()
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
        for member in archive.getmembers():
            target=(static/member.name).resolve()
            if static not in target.parents:
                raise RuntimeError('v1.8 unsafe asset path')
        archive.extractall(static)


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count=text.count(old)
    if count != 1:
        raise RuntimeError(f'v1.8 {label} target mismatch: {count}')
    return text.replace(old,new,1)


def _patch_server(p: Path) -> None:
    s=p.read_text(encoding='utf-8')
    if 'from fastapi.middleware.gzip import GZipMiddleware' not in s:
        s=_replace_once(s,'from fastapi.staticfiles import StaticFiles','from fastapi.staticfiles import StaticFiles\nfrom fastapi.middleware.gzip import GZipMiddleware','gzip import')
    s=s.replace('version="1.7.0"','version="1.8.0"').replace('"version":"1.7.0"','"version":"1.8.0"')
    app_line='app = FastAPI(title="JJ Arena Live", version="1.8.0", lifespan=lifespan, docs_url=None if os.getenv("RENDER") else "/docs", redoc_url=None if os.getenv("RENDER") else "/redoc", openapi_url=None if os.getenv("RENDER") else "/openapi.json")\n'
    if 'app.add_middleware(GZipMiddleware' not in s:
        s=_replace_once(s,app_line,app_line+'app.add_middleware(GZipMiddleware, minimum_size=800, compresslevel=5)\n','gzip middleware')
    old='''    if request.url.path.startswith('/api/'):\n        response.headers["Cache-Control"]="no-store"\n        response.headers["Pragma"]="no-cache"\n'''
    new='''    if request.url.path.startswith('/api/'):\n        response.headers["Cache-Control"]="no-store"\n        response.headers["Pragma"]="no-cache"\n    elif request.url.path == "/":\n        response.headers["Cache-Control"]="no-cache"\n    elif request.url.path.startswith('/static/'):\n        if request.url.path.endswith(("styles.css","app.js")) and request.url.query == "v=18":\n            response.headers["Cache-Control"]="public, max-age=31536000, immutable"\n        else:\n            response.headers["Cache-Control"]="public, max-age=86400"\n'''
    if 'request.url.query == "v=18"' not in s:
        s=_replace_once(s,old,new,'cache policy')
    p.write_text(s,encoding='utf-8')


def _patch_appjs(p: Path) -> None:
    s=p.read_text(encoding='utf-8')
    if 'let tableChatSig=' not in s:
        s=_replace_once(s,'  let actionBusy=false;\n  let quiz=','  let actionBusy=false;\n  let tableChatSig="";\n  let handLogSig="";\n  let quiz=','render signatures')
    old="function switchView(v){if((v==='points'||v==='members')&&me?.role!=='admin')v='home';currentView=v;$$('.view').forEach(x=>x.classList.toggle('active-view',x.id===v+'View'));$$('.nav').forEach(x=>x.classList.toggle('active',x.dataset.view===v));$('#viewEyebrow').textContent=titles[v]?.[0]||'';$('#viewTitle').textContent=titles[v]?.[1]||'';if(v!=='tables'&&currentTableId)disconnectTable();refreshView(v).catch(e=>toast(e.message))}"
    new="function switchView(v){if((v==='points'||v==='members')&&me?.role!=='admin')v='home';currentView=v;$$('.view').forEach(x=>x.classList.toggle('active-view',x.id===v+'View'));let activeNav=null;$$('.nav').forEach(x=>{const on=x.dataset.view===v;x.classList.toggle('active',on);x.toggleAttribute('aria-current',on);if(on)activeNav=x});if(activeNav&&innerWidth<=760)activeNav.scrollIntoView({block:'nearest',inline:'center',behavior:'smooth'});$('#viewEyebrow').textContent=titles[v]?.[0]||'';$('#viewTitle').textContent=titles[v]?.[1]||'';if(v!=='tables'&&currentTableId)disconnectTable();refreshView(v).catch(e=>toast(e.message))}"
    if 'activeNav&&innerWidth<=760' not in s:
        s=_replace_once(s,old,new,'navigation')
    oldclock="tableClock=setInterval(()=>{if(currentTableId&&tableState?.status==='playing')renderPokerRoom()},1000)"
    if oldclock in s:
        s=s.replace(oldclock,"tableClock=setInterval(()=>{if(currentTableId&&tableState?.status==='playing')renderHandStatusOnly()},1000)",1)
    olddisc="releaseWakeLock();currentTableId=null;tableState=null;tableMessages=[];wasMyTurn=false}"
    if olddisc in s:
        s=s.replace(olddisc,"releaseWakeLock();currentTableId=null;tableState=null;tableMessages=[];tableChatSig='';handLogSig='';wasMyTurn=false}",1)
    status="const phase=tableState.hand?.phase||'waiting';const actionSeat=tableState.hand?.action_seat;const acting=tableState.seats.find(p=>p.seat===actionSeat);const deadline=tableState.hand?.action_deadline;let sec='';if(deadline){sec=Math.max(0,Math.ceil((new Date(deadline)-new Date())/1000));sec=` · ${sec}s`}$('#handStatus').textContent=tableState.status==='playing'?`${phase.toUpperCase()}${acting?' · '+acting.name+' to act':''}${sec}`:'Waiting / Ready';"
    if 'function renderHandStatusOnly()' not in s:
        helper="function renderHandStatusOnly(){if(!tableState)return;const phase=tableState.hand?.phase||'waiting',actionSeat=tableState.hand?.action_seat,acting=tableState.seats.find(p=>p.seat===actionSeat),deadline=tableState.hand?.action_deadline;let sec='';if(deadline){const left=Math.max(0,Math.ceil((new Date(deadline)-new Date())/1000));sec=` · ${left}s`}const el=$('#handStatus');if(el)el.textContent=tableState.status==='playing'?`${phase.toUpperCase()}${acting?' · '+acting.name+' to act':''}${sec}`:'Waiting / Ready'}\n  "
        marker='  function renderPokerRoom(){'
        s=_replace_once(s,marker,'  '+helper+marker.strip(),'status helper marker')
        s=_replace_once(s,status,'renderHandStatusOnly();','status render')
    oldchat='''  function renderTableChat(){$('#tableMessages').innerHTML=tableMessages.map(m=>`<div class="chat-message"><b>${safe(m.author_name)}</b> ${safe(m.body)}<time>${dateFmt(m.created_at,{hour:'2-digit',minute:'2-digit'})}</time></div>`).join('');$('#tableMessages').scrollTop=$('#tableMessages').scrollHeight}\n  function renderHandLog(){const logs=tableState.hand?.log||[];$('#handLog').innerHTML=[...logs].reverse().map(x=>`<div>${safe(x)}</div>`).join('')||'<div>まだハンド履歴はありません</div>'}'''
    newchat='''  function renderTableChat(){const sig=tableMessages.map(m=>`${m.id||''}:${m.created_at||''}:${m.body||''}`).join('|');if(sig===tableChatSig)return;tableChatSig=sig;const el=$('#tableMessages');el.innerHTML=tableMessages.map(m=>`<div class="chat-message"><b>${safe(m.author_name)}</b> ${safe(m.body)}<time>${dateFmt(m.created_at,{hour:'2-digit',minute:'2-digit'})}</time></div>`).join('');el.scrollTop=el.scrollHeight}\n  function renderHandLog(){const logs=tableState.hand?.log||[],sig=logs.join('|');if(sig===handLogSig)return;handLogSig=sig;$('#handLog').innerHTML=[...logs].reverse().map(x=>`<div>${safe(x)}</div>`).join('')||'<div>まだハンド履歴はありません</div>'}'''
    if 'sig===tableChatSig' not in s:
        s=_replace_once(s,oldchat,newchat,'chat/log diffing')
    p.write_text(s,encoding='utf-8')
