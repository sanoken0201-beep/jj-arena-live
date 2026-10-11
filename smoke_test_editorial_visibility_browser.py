from __future__ import annotations

"""Real Chromium viewport, contrast, and clipping checks for editorial UI.

Fixtures deliberately use the genuine *compiled* stylesheet and realistic
Japanese names. No network/API, game mutation, or third-party visual assets.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

from playwright.sync_api import sync_playwright
from served_assets import build_styles

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "test-artifacts" / "editorial-visibility"

HOME = r'''
<section id="homeView" class="view active-view">
  <div class="hero-grid">
    <article class="hero card">
      <div>
        <div class="eyebrow">JJ ARENA LIVE</div>
        <h3>次の1ハンドを、みんなで。</h3>
        <p>後期ランキング、活動予定、学習、リアルタイムNLH。表示内容がすべて読み取れることを確認します。</p>
        <div class="button-row"><button class="primary" data-jump="tables">オンライン卓へ</button><button class="soft" data-jump="ranking">ランキング</button></div>
      </div>
      <div class="leader-box"><span>SEASON #1</span><strong>タカハシケンイチロウ</strong><b>28,560 pt</b></div>
    </article>
    <article class="card kpi"><div class="eyebrow">ONLINE NLH</div><strong>2</strong><span>TABLES</span><p>公開テーブル</p></article>
  </div>
  <div class="section-head"><div><div class="eyebrow">LEADERBOARD</div><h3>トップ5</h3></div>
  <button class="link-btn" data-jump="ranking">すべて見る →</button></div>
  <div id="homeTop" class="top-grid">
    <article class="top-player card"><span class="rank">#1</span><strong>タカハシケンイチロウ</strong><b>28,560 pt</b><div class="hint">17 entries</div></article>
    <article class="top-player card"><span class="rank">#2</span><strong>プレイヤーニジュウモジノナマエ</strong><b>12,350 pt</b><div class="hint">10 entries</div></article>
    <article class="top-player card"><span class="rank">#3</span><strong>イノウエ</strong><b>8,900 pt</b><div class="hint">10 entries</div></article>
    <article class="top-player card"><span class="rank">#4</span><strong>ナカムラ</strong><b>2,140 pt</b><div class="hint">5 entries</div></article>
    <article class="top-player card"><span class="rank">#5</span><strong>マツダ</strong><b>130 pt</b><div class="hint">4 entries</div></article>
  </div>
  <div class="home-columns">
    <article class="card panel"><div class="eyebrow">NEXT SESSION</div><h3>次の活動</h3><div class="mini-item"><strong>通常活動</strong><span>2026-10-11 · 17405教室</span></div></article>
    <article class="card panel"><div class="eyebrow">LIVE TABLES</div><h3>いま遊べる卓</h3><div class="mini-item"><strong>JJ Ring</strong><span>4 / 6</span></div></article>
    <article class="card panel"><div class="eyebrow">BOARD</div><h3>最新のお知らせ</h3><div class="mini-item"><strong>公式情報</strong><span>2026-10-11</span></div></article>
  </div>
</section>'''

RANKING = r'''
<section id="rankingView" class="view active-view">
  <div class="toolbar card">
    <div class="segmented">
      <button class="active" data-rank-mode="overall">後期総合</button>
      <button data-rank-mode="month">月間</button>
      <button data-rank-mode="archive">前期参考</button>
    </div>
    <select id="rankMonth"><option>2026-10</option></select>
    <input id="rankSearch" placeholder="プレイヤー検索" aria-label="プレイヤー検索">
  </div>
  <div id="podium" class="podium">
    <article class="podium-card card"><div class="eyebrow">後期 #1</div><strong>タカハシケンイチロウ</strong><b>28,560 pt</b><div class="hint">Club 15,220 · Online +13,340</div></article>
    <article class="podium-card card"><div class="eyebrow">後期 #2</div><strong>プレイヤーニジュウモジノナマエ</strong><b>12,350 pt</b><div class="hint">Club 5,000 · Online +7,350</div></article>
    <article class="podium-card card"><div class="eyebrow">後期 #3</div><strong>イノウエ</strong><b>8,900 pt</b><div class="hint">Club 3,000 · Online +5,900</div></article>
  </div>
  <div class="card table-card"><table><thead><tr>
    <th>Rank</th><th>Player</th><th>Total</th><th>Club</th><th>Online</th><th>Online Hands</th>
  </tr></thead><tbody id="rankBody">
    <tr><td class="rank-num">#1</td><td><strong>タカハシケンイチロウ</strong></td><td><b>28,560</b></td><td>15,220</td><td class="positive">+13,340</td><td>124</td></tr>
    <tr><td class="rank-num">#2</td><td><strong>プレイヤーニジュウモジノナマエ</strong></td><td><b>12,350</b></td><td>5,000</td><td class="positive">+7,350</td><td>85</td></tr>
    <tr><td class="rank-num">#3</td><td><strong>イノウエ</strong></td><td><b>8,900</b></td><td>3,000</td><td class="positive">+5,900</td><td>50</td></tr>
  </tbody></table></div>
</section>'''

HTML = r'''<!doctype html><html lang="ja"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<style>/* STYLE */</style></head><body>
<div class="app-shell">
<aside class="sidebar"><div class="side-brand">JJ Arena</div><nav><button class="nav active">ホーム</button></nav></aside>
<main class="main"><header class="topbar"><div><div id="viewEyebrow" class="eyebrow">DASHBOARD</div><h2 id="viewTitle">JJ Arena</h2></div><div class="top-actions"><div class="user-chip"><strong>テストユーザー</strong></div></div></header>
<!-- BODY -->
</main></div>
<div class="mobile-dock"><button class="active"><b>⌂</b><span>ホーム</span></button><button><b>♛</b><span>ランキング</span></button></div>
</body></html>'''

# Evaluate computed styles on actual rendered nodes, not assumed CSS colors.
AUDIT_JS = r'''(mode) => {
  const vw = innerWidth;
  const nodes = mode === 'home'
    ? ['.hero h3','.hero p','.leader-box strong','.leader-box b',
       ...Array.from({length:5},(_,i)=>'#homeTop .top-player:nth-child('+(i+1)+') strong'),
       ...Array.from({length:5},(_,i)=>'#homeTop .top-player:nth-child('+(i+1)+') b')]
    : ['#podium .podium-card:nth-child(1) strong',
       '#podium .podium-card:nth-child(1) b',
       '#podium .podium-card:nth-child(2) strong',
       '#podium .podium-card:nth-child(2) b',
       ...Array.from({length:3},(_,i)=>'#rankBody tr:nth-child('+(i+1)+') td:nth-child(2)'),
       ...Array.from({length:3},(_,i)=>'#rankBody tr:nth-child('+(i+1)+') td:nth-child(3)'),
       '.segmented button.active','#rankSearch'];
  function rgb(str) {
    const m = str.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const a=m[1].split(/[\s,\/]+/).filter(Boolean).map(Number);
    return [a[0],a[1],a[2],a.length<4?1:a[3]];
  }
  function background(el) {
    for(let n=el; n; n=n.parentElement) {
      const a=rgb(getComputedStyle(n).backgroundColor);
      if(a && a[3]>=0.99) return a;
    }
    return [255,255,255,1];
  }
  function luminance(a) {
    return [0,1,2].map(i=>{const v=a[i]/255;return v<=0.04045?v/12.92:Math.pow((v+0.055)/1.055,2.4)})
      .reduce((sum,v,i)=>sum+v*[0.2126,0.7152,0.0722][i],0);
  }
  const errors=[],metrics=[];
  const view=document.querySelector(mode==='home'?'#homeView':'#rankingView');
  if(Number(getComputedStyle(view).opacity)<0.99)errors.push('view is still fading; evaluate fully visible page');
  for (const selector of nodes) {
    const e=document.querySelector(selector);
    if (!e) {errors.push(selector+': missing');continue;}
    const style=getComputedStyle(e), r=e.getBoundingClientRect();
    if (r.width<1 || r.height<1 || style.visibility==='hidden' || style.display==='none')
      errors.push(selector+': hidden');
    if (r.left<-1 || r.right>vw+1)
      errors.push(selector+': outside viewport ('+r.left+','+r.right+')');
    if (e.scrollWidth>e.clientWidth+2)
      errors.push(selector+': horizontal text clip ('+e.scrollWidth+'/'+e.clientWidth+')');
    const fg=rgb(style.color),bg=background(e);
    const a=luminance(fg),b=luminance(bg);
    const ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
    if(ratio<4.5) errors.push(selector+': contrast '+ratio.toFixed(2)+' < 4.5');
    const font=parseFloat(style.fontSize);
    if (selector.includes('strong') || selector.includes(' b') ||
        selector.includes('td:nth-child') || selector==='.hero p' || selector.includes('button.active')) {
      if(font<14)errors.push(selector+': important text only '+font+'px');
    }
    metrics.push({selector,contrast:+ratio.toFixed(2),font,rect:{left:Math.round(r.left),right:Math.round(r.right),height:Math.round(r.height)}});
  }
  const pairs= mode==='home'
    ? Array.from({length:5},(_,i)=>['#homeTop .top-player:nth-child('+(i+1)+') strong',
      '#homeTop .top-player:nth-child('+(i+1)+') b'])
    : Array.from({length:3},(_,i)=>['#rankBody tr:nth-child('+(i+1)+') td:nth-child(2)',
      '#rankBody tr:nth-child('+(i+1)+') td:nth-child(3)']);
  for(const [left,right] of pairs) {
    const a=document.querySelector(left).getBoundingClientRect(), b=document.querySelector(right).getBoundingClientRect();
    if(a.left<b.right && a.right>b.left && a.top<b.bottom && a.bottom>b.top)
      errors.push(left+': overlaps numeric score');
  }
  if(vw<=760){
    const controls=mode==='home' ? ['.section-head .link-btn'] :
      ['.segmented button:nth-child(1)','.segmented button:nth-child(2)',
       '.segmented button:nth-child(3)','#rankMonth','#rankSearch'];
    for(const selector of controls){
      const e=document.querySelector(selector);
      if(!e) {errors.push(selector+': missing control');continue;}
      const box=e.getBoundingClientRect();
      if(box.height<44)errors.push(selector+': tap target only '+box.height.toFixed(1)+'px');
    }
    if(mode==='ranking' && parseFloat(getComputedStyle(document.querySelector('#rankSearch')).fontSize)<16)
      errors.push('ranking search input: font size below 16px causes mobile zoom');
  }
  if (document.documentElement.scrollWidth>vw+2)
    errors.push('horizontal page overflow: '+document.documentElement.scrollWidth+' > '+vw);
  return {viewport:vw,mode,errors,metrics};
}'''


def _browser_executable() -> str | None:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "msedge"):
        p=shutil.which(name)
        if p:
            return p
    return None


def main() -> None:
    # A pass with tofu boxes instead of Japanese glyphs is not a valid test.
    result=subprocess.run(["fc-list", ":lang=ja", "family"],capture_output=True,text=True,check=True)
    if not result.stdout.strip():
        raise AssertionError("Japanese fonts missing in Chromium runner: install Noto CJK for screenshot audit")
    css=build_styles()
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        executable=_browser_executable()
        kwargs={"headless":True,"args":["--no-sandbox","--disable-dev-shm-usage"]}
        if executable:
            kwargs["executable_path"]=executable
        browser=p.chromium.launch(**kwargs)
        issues=[]
        for width,height in ((320,568),(360,740),(390,844),(760,1024),(1024,768),(1440,900)):
            for mode,section in (("home",HOME),("ranking",RANKING)):
                page=browser.new_page(viewport={"width":width,"height":height},device_scale_factor=1)
                page.set_content(HTML.replace("/* STYLE */",css).replace("<!-- BODY -->",section),wait_until="load")
                page.wait_for_timeout(300)
                result=page.evaluate(AUDIT_JS,mode)
                (OUT/f"{mode}-{width}.png").parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(OUT/f"{mode}-{width}.png"),full_page=True)
                print(json.dumps({"width":width,"mode":mode,"errors":result["errors"],
                                  "smallest_contrast":min(x["contrast"] for x in result["metrics"])},
                                 ensure_ascii=False),flush=True)
                issues.extend(f"{width}px {mode}: {e}" for e in result["errors"])
                page.close()
        browser.close()
        if issues:
            raise AssertionError("Visibility audit failed:\n"+"\n".join(issues))
    print("JJ_EDITORIAL_VISIBILITY_OK 320/360/390/760/1024/1440px, contrast >= 4.5, labels >=14px, no clipping")


if __name__ == "__main__":
    main()
