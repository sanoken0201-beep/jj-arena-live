from __future__ import annotations
from pathlib import Path
import re


def apply(root: Path) -> None:
    _server(root/'server.py')
    _app(root/'static'/'app.js')
    _styles(root/'static'/'styles.css')
    _index(root/'static'/'index.html')
    _sw(root/'static'/'sw.js')


def _server(p: Path) -> None:
    s=p.read_text(encoding='utf-8')
    s=s.replace('version="1.14.0"','version="1.14.1"').replace('"version":"1.14.0"','"version":"1.14.1"')
    s=s.replace('request.url.query == "v=24"','request.url.query == "v=25"')
    s=s.replace('mode: str = Field(pattern="^(sitout|cancel_sitout|return)$")','mode: str = Field(pattern="^(sitout|cancel_sitout|return|rebuy)$")')
    target='''        elif mode == "return":\n            if int(player.get("stack", 0)) <= 0:\n                raise HTTPException(400, "0bbのため復帰するにはRebuyが必要です")\n            player["sitting_out"] = False\n            player["sit_out_next"] = False\n            if not bool(state.get("session_active")):\n                player["ready"] = False\n'''
    repl=target+'''        elif mode == "rebuy":\n            if state.get("status") == "playing":\n                raise HTTPException(400, "ハンド終了後にRebuyしてください")\n            if int(player.get("stack", 0)) != 0:\n                raise HTTPException(400, "Rebuyは0bbのときだけ利用できます")\n            player["stack"] = int(db.TABLE_STARTING_STACK)\n            player["sitting_out"] = False\n            player["sit_out_next"] = False\n            player["ready"] = False\n'''
    if target not in s:
        raise RuntimeError('v1.14.1 presence return marker missing')
    s=s.replace(target,repl,1)
    p.write_text(s,encoding='utf-8')


def _app(p: Path) -> None:
    s=p.read_text(encoding='utf-8')
    old="if(seated.stack<=0){$('#tableControls').innerHTML='<span class=\"jj-control-note\">BUSTED · Rebuyして復帰してください</span>';return}"
    new="if(seated.stack<=0){$('#tableControls').innerHTML='<div class=\"jj-table-control-left\"><span class=\"jj-control-note\">BUSTED · 0bb</span></div><div class=\"jj-table-control-right\"><button class=\"primary\" data-table-presence=\"rebuy\" '+(tableState.status==='playing'?'disabled':'')+'>Rebuy 150bb</button><button class=\"ghost\" id=\"leaveSeatBtn\">席を離れる</button></div>';return}"
    if old not in s: raise RuntimeError('v1.14.1 busted UI marker missing')
    s=s.replace(old,new,1)
    old="const presets=isPre?[['2.5x',2.5],['3x',3],['4x',4]]:[[ '33%',33],[ '50%',50],[ '75%',75],[ 'POT',100]];\n    const quick=presets.map(([label,val])=>isPre?`<button class=\"jj-size-btn\" data-raise-bb=\"${val}\">${label}</button>`:`<button class=\"jj-size-btn\" data-pot-pct=\"${val}\">${label}</button>`).join('');"
    new="const unopenedPre=isPre&&Number(tableState.hand?.current_bet||0)<=Number(tableState.big_blind||100);\n    const presets=unopenedPre?[['2.5x',2.5],['3x',3],['4x',4]]:[[ '33%',33],[ '50%',50],[ '75%',75],[ 'POT',100]];\n    const quick=presets.map(([label,val])=>unopenedPre?`<button class=\"jj-size-btn\" data-raise-bb=\"${val}\">${label}</button>`:`<button class=\"jj-size-btn\" data-pot-pct=\"${val}\">${label}</button>`).join('');"
    if old not in s: raise RuntimeError('v1.14.1 preset marker missing')
    s=s.replace(old,new,1)
    old="toast(presence.dataset.tablePresence==='sitout'?'次ハンドから離席します':presence.dataset.tablePresence==='return'?'復帰します':'離席予約を取り消しました')"
    new="toast(presence.dataset.tablePresence==='sitout'?'次ハンドから離席します':presence.dataset.tablePresence==='return'?'復帰します':presence.dataset.tablePresence==='rebuy'?'150bbでRebuyしました':'離席予約を取り消しました')"
    if old not in s: raise RuntimeError('v1.14.1 presence toast marker missing')
    s=s.replace(old,new,1)
    p.write_text(s,encoding='utf-8')


def _styles(p: Path) -> None:
    s=p.read_text(encoding='utf-8')
    s += '\n/* v1.14.1 table positioning safeguard */\n#pokerRoom .poker-zone{position:relative}\n'
    p.write_text(s,encoding='utf-8')


def _index(p: Path) -> None:
    s=p.read_text(encoding='utf-8').replace('?v=24','?v=25')
    p.write_text(s,encoding='utf-8')


def _sw(p: Path) -> None:
    s=p.read_text(encoding='utf-8')
    s=re.sub(r'jj-arena-live-v\d+','jj-arena-live-v25',s)
    p.write_text(s,encoding='utf-8')
