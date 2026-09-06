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
    s=p.read_text(encoding='utf-8')
    s=s.replace('version="1.15.0"','version="1.15.1"').replace('"version":"1.15.0"','"version":"1.15.1"')
    s=s.replace('request.url.query == "v=27"','request.url.query == "v=28"')
    p.write_text(s,encoding='utf-8')


def _app(p: Path) -> None:
    s=p.read_text(encoding='utf-8')
    if 'v1.15.1 exact hero hand label' in s:
        return
    marker='})();'
    pos=s.rfind(marker)
    if pos<0: raise RuntimeError('v1.15.1 app marker missing')
    addon=r'''

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
'''
    s=s[:pos]+addon+s[pos:]
    p.write_text(s,encoding='utf-8')


def _styles(p: Path) -> None:
    s=p.read_text(encoding='utf-8')
    if 'v1.15.1 mobile action clearance' in s:
        return
    s += r'''

/* v1.15.1 mobile action clearance: the fixed betting console must never cover
   the last table controls or create an unreachable region behind bottom nav. */
@media(max-width:760px){
  #pokerRoom .poker-zone{padding:6px 6px calc(212px + env(safe-area-inset-bottom))!important}
  #pokerRoom .table-controls{position:relative;z-index:2;padding-left:8px!important;padding-right:8px!important}
  #pokerRoom .action-bar{bottom:calc(70px + env(safe-area-inset-bottom))!important;max-height:205px;overflow-y:auto;overscroll-behavior:contain}
}
'''
    p.write_text(s,encoding='utf-8')


def _index(p: Path) -> None:
    s=p.read_text(encoding='utf-8').replace('?v=27','?v=28')
    p.write_text(s,encoding='utf-8')


def _sw(p: Path) -> None:
    s=p.read_text(encoding='utf-8')
    s=re.sub(r'jj-arena-live-v\d+','jj-arena-live-v28',s)
    p.write_text(s,encoding='utf-8')
