from __future__ import annotations

import re
from pathlib import Path


def apply(root: Path) -> None:
    _server(root / "server.py")
    _app(root / "static" / "app.js")
    _styles(root / "static" / "styles.css")
    _index(root / "static" / "index.html")
    _sw(root / "static" / "sw.js")


def _server(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace('version="1.19.1"', 'version="1.19.2"')
    text = text.replace('"version":"1.19.1"', '"version":"1.19.2"')
    text = text.replace('request.url.query == "v=40"', 'request.url.query == "v=41"')
    path.write_text(text, encoding="utf-8")


def _app(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "v1.19.2 Japanese-first learning share" in text:
        return
    marker = "})();"
    pos = text.rfind(marker)
    if pos < 0:
        raise RuntimeError("v1.19.2 app closing marker missing")
    addon = r'''

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
'''
    text = text[:pos] + addon + text[pos:]
    path.write_text(text, encoding="utf-8")


def _styles(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "v1.19.2 Japanese-first learning share" in text:
        return
    text += r'''

/* v1.19.2 Japanese-first learning share */
.jj-learning-share{grid-column:1/-1;width:100%;margin-top:22px;padding:22px;border:1px solid var(--line,#263b34);border-radius:18px;background:linear-gradient(160deg,rgba(17,31,26,.96),rgba(9,18,15,.98));box-shadow:0 15px 40px rgba(0,0,0,.18)}
.jj-learning-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:18px}.jj-learning-head h2{margin:3px 0 5px;font-size:1.35rem}.jj-learning-head p{margin:0;color:var(--muted,#9cadA5);font-size:.82rem;line-height:1.55}.jj-learning-policy{flex:0 0 auto;padding:7px 10px;border:1px solid rgba(242,205,99,.38);border-radius:999px;color:#f2d77d;background:rgba(242,205,99,.08);font-size:.68rem;font-weight:800;letter-spacing:.04em}
.jj-learning-columns{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px}.jj-learning-column{min-width:0}.jj-learning-title{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:9px;padding:0 2px}.jj-learning-title b{font-size:.69rem;letter-spacing:.12em;color:#f2d77d}.jj-learning-title span{font-size:.68rem;color:var(--muted,#9cada5)}
.jj-learning-list,.jj-video-list{display:grid;gap:8px}.jj-study-card,.jj-video-card{display:block;text-decoration:none;color:inherit;border:1px solid rgba(255,255,255,.08);border-radius:13px;background:rgba(255,255,255,.025);transition:border-color .15s ease,background .15s ease,transform .15s ease}.jj-study-card{padding:13px 14px}.jj-study-card:hover,.jj-video-card:hover{border-color:rgba(242,205,99,.38);background:rgba(255,255,255,.045);transform:translateY(-1px)}
.jj-study-meta{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-bottom:6px;color:var(--muted,#9cada5);font-size:.62rem}.jj-study-source,.jj-video-kind{padding:3px 6px;border-radius:999px;background:rgba(78,183,137,.12);color:#8fd8b6;font-weight:800}.jj-video-kind.is-motivation{background:rgba(242,205,99,.12);color:#f1d47c}.jj-study-card h3,.jj-video-card h3{margin:0;font-size:.88rem;line-height:1.45}.jj-study-card p,.jj-video-card p{margin:6px 0 0;color:var(--muted,#a5b4ad);font-size:.72rem;line-height:1.5}.jj-study-card footer,.jj-video-card footer{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:9px;color:var(--muted,#93a39b);font-size:.64rem}.jj-study-card footer b,.jj-video-card footer b{color:#e9d181;font-size:.66rem}
.jj-video-card{display:grid;grid-template-columns:122px minmax(0,1fr);overflow:hidden}.jj-video-thumb{position:relative;min-height:92px;background:#050807;overflow:hidden}.jj-video-thumb img{width:100%;height:100%;object-fit:cover;display:block}.jj-video-thumb:after{content:"";position:absolute;inset:0;background:linear-gradient(90deg,transparent,rgba(0,0,0,.2))}.jj-video-thumb>span{position:absolute;z-index:2;left:50%;top:50%;transform:translate(-50%,-50%);display:grid;place-items:center;width:34px;height:34px;border-radius:50%;background:rgba(0,0,0,.72);color:#fff;font-size:.8rem}.jj-video-copy{padding:10px 12px;min-width:0}
@media(max-width:760px){.jj-learning-share{margin-top:14px;padding:15px 12px;border-radius:14px}.jj-learning-head{gap:10px;margin-bottom:14px}.jj-learning-head h2{font-size:1.08rem}.jj-learning-head p{font-size:.72rem}.jj-learning-policy{padding:6px 8px;font-size:.59rem}.jj-learning-columns{grid-template-columns:1fr;gap:18px}.jj-study-card{padding:12px}.jj-study-card h3,.jj-video-card h3{font-size:.82rem}.jj-video-card{grid-template-columns:110px minmax(0,1fr)}.jj-video-thumb{min-height:88px}.jj-video-copy{padding:9px 10px}.jj-study-card p,.jj-video-card p{font-size:.68rem}}
@media(max-width:380px){.jj-video-card{grid-template-columns:96px minmax(0,1fr)}.jj-video-card p{display:none}}
'''
    path.write_text(text, encoding="utf-8")


def _index(path: Path) -> None:
    text = path.read_text(encoding="utf-8").replace("?v=40", "?v=41")
    path.write_text(text, encoding="utf-8")


def _sw(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"jj-arena-live-v\d+", "jj-arena-live-v41", text)
    path.write_text(text, encoding="utf-8")
