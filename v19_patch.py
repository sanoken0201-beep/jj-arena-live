from __future__ import annotations
from pathlib import Path
import re


def apply(root: Path) -> None:
    _patch_server(root / 'server.py')
    _patch_index(root / 'static' / 'index.html')
    _patch_appjs(root / 'static' / 'app.js')
    _patch_styles(root / 'static' / 'styles.css')
    _patch_sw(root / 'static' / 'sw.js')


def _patch_server(p: Path) -> None:
    s=p.read_text(encoding='utf-8')
    s=s.replace('version="1.8.0"','version="1.9.0"').replace('"version":"1.8.0"','"version":"1.9.0"')
    s=s.replace('request.url.query == "v=18"','request.url.query == "v=19"')
    p.write_text(s,encoding='utf-8')


def _patch_index(p: Path) -> None:
    s=p.read_text(encoding='utf-8')
    s=s.replace('?v=18','?v=19')
    p.write_text(s,encoding='utf-8')


def _patch_appjs(p: Path) -> None:
    s=p.read_text(encoding='utf-8')
    if 'const wizardStudyLibrary=' in s:
        return
    marker='})();'
    pos=s.rfind(marker)
    if pos < 0:
        raise RuntimeError('v1.9 app.js closing marker not found')
    addon=r'''

  // v1.9 — curated external study spotlight. The selection is deterministic per ISO-like
  // week so every member sees the same Cash/MTT pair and it rotates automatically.
  const wizardStudyLibrary={
    cash:[
      {title:'OOP 4-Betting in Deep-Stacked Cash Games',date:'2025-01-27',minutes:'8 min',url:'https://blog.gtowizard.com/oop-4-betting-in-deep-stacked-cash-games/',summary:'ディープスタックの4bet potで、OOP側がどのボードで強くベットできるかを整理する週。'},
      {title:'Check-Raising a Single Pair',date:'2024-02-26',minutes:'7 min',url:'https://blog.gtowizard.com/check-raising-a-single-pair/',summary:'100bb前後でワンペアをチェックレイズへ回す条件を、レンジとインセンティブから考える。'},
      {title:'The 5 Levels of Trainer Mastery for Cash Games',date:'2024-06-17',minutes:'9 min',url:'https://blog.gtowizard.com/the-5-levels-of-trainer-mastery/',summary:'Trainer学習を難易度順に組み立て、ただ解くだけではなく反復設計まで見直す。'},
      {title:'Live Cash Solutions and 4,000 New Scenarios',date:'2024-06-18',minutes:'4 min',url:'https://blog.gtowizard.com/live-cash-solutions-and-4000-new-scenarios-for-cash-mtt-formats/',summary:'ライブキャッシュ特有の深いスタック・大きなオープンサイズをどう学習対象にするか確認する。'},
      {title:'Introducing Nodelocking',date:'2023-10-11',minutes:'11 min',url:'https://blog.gtowizard.com/introducing-nodelocking/',summary:'均衡戦略から相手のリークを固定して、エクスプロイトへ橋渡しする考え方を確認する。'}
    ],
    mtt:[
      {title:'Playing Under 10bb – Part 2: ICM',date:'2026-07-13',minutes:'12 min',url:'https://blog.gtowizard.com/playing-under-10bb-part-2-icm/',summary:'10bb未満の終盤戦。バブルとFTで同じショート戦略にならない理由をICMから確認する。'},
      {title:'Playing Under 10bb – Part 1: cEV',date:'2026-06-29',minutes:'14 min',url:'https://blog.gtowizard.com/playing-under-10bb-part-1-cev/',summary:'ICMが薄い局面の超ショート戦略を先に整理し、Part 2との違いを見る。'},
      {title:'How ICM Quietly Shapes Postflop Strategy From the Start',date:'2025-12-23',minutes:'13 min',url:'https://blog.gtowizard.com/how-icm-quietly-shapes-postflop-strategy-from-the-start/',summary:'トーナメント序盤にも小さなリスクプレミアムが存在するという視点からcEVとの差を考える。'},
      {title:'How ICM Reshapes 3-Bet Pots',date:'2025-12-08',minutes:'11 min',url:'https://blog.gtowizard.com/how-icm-reshapes-3-bet-pots-and-why-you-cant-trust-chipev/',summary:'3bet potでICMがプリフロップレンジとポストフロップ双方に与える影響を切り分ける。'},
      {title:'Register Late, Win More',date:'2025-07-28',minutes:'10 min',url:'https://blog.gtowizard.com/register-late-win-more-the-math-behind-smarter-tournament-entry/',summary:'レイトレジがスタックのICM価値と収益性にどう作用するか、参加タイミングの数学を見る。'},
      {title:'Mastering Postflop ICM: Avoid These Common Mistakes',date:'2025-02-11',minutes:'13 min',url:'https://blog.gtowizard.com/mastering-postflop-icm-avoid-these-common-mistakes/',summary:'ポストフロップICMをcEVと比較せず読む危険など、学習時の代表的な落とし穴を整理する。'},
      {title:'When to Just Shove Postflop in ICM Spots',date:'2025-04-15',minutes:'9 min',url:'https://blog.gtowizard.com/when-to-just-shove-post-flop-in-icm-spots/',summary:'ICMでは小さく打つ傾向だけでなく、極端なオールインが選ばれる条件もあることを学ぶ。'},
      {title:'The 5 Levels of Trainer Mastery for MTTs',date:'2024-08-12',minutes:'9 min',url:'https://blog.gtowizard.com/5-levels-of-trainer-mastery-for-mtts/',summary:'スタック深度・ICM・PKOまで含むMTT学習を段階化して、毎週の学習ルーティンを作る。'}
    ]
  };
  function studyWeekSeed(){
    const now=new Date(),d=new Date(now.getFullYear(),now.getMonth(),now.getDate());
    const day=(d.getDay()+6)%7; d.setDate(d.getDate()-day);
    return Number(`${d.getFullYear()}${String(d.getMonth()+1).padStart(2,'0')}${String(d.getDate()).padStart(2,'0')}`);
  }
  function studyIndex(kind,length){let x=(studyWeekSeed()^(kind==='cash'?0x43a5f17:0x19b7c31))>>>0;x^=x<<13;x^=x>>>17;x^=x<<5;return Math.abs(x>>>0)%length}
  function studyArticle(kind){const list=wizardStudyLibrary[kind],a=list[studyIndex(kind,list.length)];return a}
  function studyCard(kind,a,compact=false){const label=kind==='cash'?'CASH':'MTT',jp=kind==='cash'?'キャッシュ':'トーナメント';return `<article class="study-card ${kind} ${compact?'compact':''}"><div class="study-card-top"><span class="study-kind">${label}</span><span class="study-time">${safe(a.minutes)}</span></div><h4>${safe(a.title)}</h4><p>${safe(a.summary)}</p><div class="study-meta"><span>${jp} · ${safe(a.date)}</span><a href="${safe(a.url)}" target="_blank" rel="noopener noreferrer">GTO Wizardで読む <b>↗</b></a></div></article>`}
  function renderWeeklyStudy(){
    const cash=studyArticle('cash'),mtt=studyArticle('mtt');
    const home=$('#homeView');
    if(home&&!$('#weeklyStudyHome')){
      const block=document.createElement('section');block.id='weeklyStudyHome';block.className='weekly-study weekly-study-home';
      block.innerHTML=`<div class="study-head"><div><div class="eyebrow">WEEKLY STUDY</div><h3>今週の2本</h3><p>CashとMTTを1本ずつ。毎週月曜に自動で切り替わります。</p></div><button class="soft" data-jump="lab">Poker Labで見る</button></div><div class="study-grid">${studyCard('cash',cash,true)}${studyCard('mtt',mtt,true)}</div>`;
      const anchor=home.querySelector('.home-columns');if(anchor)anchor.insertAdjacentElement('beforebegin',block);else home.appendChild(block);
    }
    const lab=$('#labView');
    if(lab&&!$('#weeklyStudyLab')){
      const block=document.createElement('section');block.id='weeklyStudyLab';block.className='weekly-study weekly-study-lab card';
      block.innerHTML=`<div class="study-head"><div><div class="eyebrow">CURATED BY JJ · EXTERNAL</div><h3>今週のGTO Wizard</h3><p>原文への入口だけをJJ Arenaに置きます。本文転載はせず、学習テーマをCash / MTTで分離しています。</p></div><a class="study-all" href="https://blog.gtowizard.com/articles/" target="_blank" rel="noopener noreferrer">記事一覧 ↗</a></div><div class="study-grid">${studyCard('cash',cash)}${studyCard('mtt',mtt)}</div><div class="study-foot">GTO Wizardの外部記事を紹介する非提携の学習リンクです。JJ Arenaのポイントやオンライン対戦結果には影響しません。</div>`;
      const first=lab.firstElementChild;if(first)first.insertAdjacentElement('beforebegin',block);else lab.appendChild(block);
    }
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',renderWeeklyStudy,{once:true});else renderWeeklyStudy();
'''
    s=s[:pos]+addon+s[pos:]
    p.write_text(s,encoding='utf-8')


def _patch_styles(p: Path) -> None:
    s=p.read_text(encoding='utf-8')
    if 'v1.9 weekly study + launch refinement' in s:
        return
    s += r'''

/* v1.9 weekly study + launch refinement */
:where(button,a,input,select,textarea):focus-visible{outline:3px solid color-mix(in srgb,var(--accent,#1f8a62) 42%,transparent);outline-offset:2px}
:where(.rank-num,#heroLeaderPoints,.pot-display,.date-big,.calc strong){font-variant-numeric:tabular-nums}
:where(h1,h2,h3,h4){text-wrap:balance}
.weekly-study{margin-top:clamp(18px,2.4vw,32px)}
.weekly-study.card{padding:clamp(18px,2.6vw,30px);overflow:hidden;position:relative}
.weekly-study.card:before{content:"";position:absolute;inset:0 auto auto 0;width:100%;height:3px;background:linear-gradient(90deg,#14a573,#d6a83b,#233b6e)}
.study-head{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;margin-bottom:16px}
.study-head h3{margin:.18rem 0 .3rem;font-size:clamp(1.25rem,2vw,1.7rem)}
.study-head p{margin:0;color:var(--muted,#68756f);max-width:700px;font-size:.88rem}
.study-all{white-space:nowrap;text-decoration:none;font-weight:800;color:var(--accent,#177553);font-size:.86rem}
.study-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.study-card{position:relative;isolation:isolate;display:flex;flex-direction:column;min-width:0;padding:18px;border:1px solid var(--line,#dfe8e2);border-radius:18px;background:linear-gradient(145deg,rgba(255,255,255,.98),rgba(248,251,249,.94));box-shadow:0 10px 30px rgba(24,52,40,.055);overflow:hidden;transition:transform .18s ease,box-shadow .18s ease,border-color .18s ease}
.study-card:after{content:"";position:absolute;z-index:-1;width:150px;height:150px;border-radius:50%;right:-60px;top:-70px;opacity:.11;filter:blur(2px)}
.study-card.cash:after{background:#13a06f}.study-card.mtt:after{background:#d0a33a}
.study-card:hover{transform:translateY(-2px);box-shadow:0 14px 34px rgba(24,52,40,.09);border-color:color-mix(in srgb,var(--line,#dfe8e2) 55%,#4a8b6e)}
.study-card-top{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:12px}
.study-kind{display:inline-flex;align-items:center;min-height:25px;padding:0 9px;border-radius:999px;font-size:.68rem;font-weight:900;letter-spacing:.12em}
.study-card.cash .study-kind{background:#e4f7ef;color:#087652}.study-card.mtt .study-kind{background:#fff2cf;color:#8a6506}
.study-time{font-size:.72rem;font-weight:800;color:var(--muted,#68756f)}
.study-card h4{font-size:clamp(1rem,1.45vw,1.18rem);line-height:1.35;margin:0 0 9px}
.study-card p{font-size:.84rem;line-height:1.72;color:var(--muted,#68756f);margin:0 0 16px;flex:1}
.study-meta{display:flex;align-items:center;justify-content:space-between;gap:12px;padding-top:12px;border-top:1px solid var(--line,#e2e9e5);font-size:.72rem;color:var(--muted,#68756f)}
.study-meta a{text-decoration:none;font-weight:900;color:var(--text,#17231e);white-space:nowrap}
.study-meta a:hover{text-decoration:underline}.study-meta b{font-size:.9rem}
.study-foot{margin-top:13px;padding-top:12px;border-top:1px dashed var(--line,#dfe8e2);font-size:.7rem;line-height:1.6;color:var(--muted,#68756f)}
.weekly-study-home{padding:0}.weekly-study-home .study-head{padding:0 2px}.weekly-study-home .study-card.compact{padding:16px}.weekly-study-home .study-card.compact p{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
@media (max-width:760px){
  :where(button,.primary,.soft,.ghost,input,select){min-height:44px}
  .study-head{align-items:flex-start;flex-direction:column;gap:9px}.study-grid{grid-template-columns:1fr}.study-card{padding:16px;border-radius:16px}.study-meta{align-items:flex-start;flex-direction:column;gap:7px}.weekly-study{margin-top:18px}
}
@media (prefers-reduced-motion:reduce){*,*:before,*:after{scroll-behavior:auto!important;animation-duration:.001ms!important;animation-iteration-count:1!important;transition-duration:.001ms!important}.study-card:hover{transform:none}}
@supports (content-visibility:auto){.news-card,.schedule-card,.thread{content-visibility:auto;contain-intrinsic-size:1px 260px}}
'''
    p.write_text(s,encoding='utf-8')


def _patch_sw(p: Path) -> None:
    if not p.exists():
        return
    s=p.read_text(encoding='utf-8')
    s=re.sub(r'jj-arena-live-v\d+','jj-arena-live-v9',s)
    s=s.replace('?v=18','?v=19')
    p.write_text(s,encoding='utf-8')
