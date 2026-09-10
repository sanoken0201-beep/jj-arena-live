from __future__ import annotations
from pathlib import Path
import json
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
    if 'const jjJapaneseArticleFallback=' in s:
        return
    marker='})();'
    pos=s.rfind(marker)
    if pos < 0:
        raise RuntimeError('v1.9 app.js closing marker not found')
    addon=r'''

  // Japanese article fallbacks are embedded from the server's verified list.
  // Both study surfaces stay Japanese even when the API is unavailable.
  const jjJapaneseArticleFallback=__JJ_JAPANESE_ARTICLE_FALLBACK__;
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
'''
    from learning_content import _fallback_payload

    fallback_json = json.dumps(_fallback_payload()['articles'], ensure_ascii=False).replace('<', '\\u003c')
    addon = addon.replace('__JJ_JAPANESE_ARTICLE_FALLBACK__', fallback_json)
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
