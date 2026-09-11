from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from runtime_builder import build_runtime


FIXTURE = r'''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="styles.css">
<style>
:root{--ink:#eef6f2;--muted:#9fb1a9;--line:rgba(255,255,255,.12);--accent:#20a873;--danger:#e35b67}
html,body{margin:0;background:#07100d;color:#eef6f2}.fixture{width:100%;max-width:1180px;margin:auto;padding:16px;box-sizing:border-box}.card{background:#13211c;border:1px solid var(--line);border-radius:16px}button{font:inherit}.hidden{display:none!important}
</style></head><body><main class="fixture">
<section id="jjV1244AnalysisFocus" class="jj-v1244-analysis-focus">
  <div class="jj-v1244-focus-head"><div><span>START HERE</span><h3>今見るべきポイント</h3><p>検出された傾向を最大3件に絞っています。</p></div><small>solver判定ではありません</small></div>
  <div class="jj-v1244-focus-grid">
    <article class="jj-v1244-focus-card is-watch"><div class="jj-v1244-focus-no">01</div><div><span>Fold to 3bet</span><h4>3betに対するフォールドが多い傾向</h4><p>3betを受けた24回のうち79%でフォールドしています。</p></div><button type="button">関連ハンドを見る →</button></article>
    <article class="jj-v1244-focus-card is-watch"><div class="jj-v1244-focus-no">02</div><div><span>3bet</span><h4>3bet頻度が低い傾向</h4><p>3bet機会51回で3.9%。</p></div><button type="button">関連ハンドを見る →</button></article>
    <article class="jj-v1244-focus-card is-info"><div class="jj-v1244-focus-no">03</div><div><span>Cbet</span><h4>フロップCbet頻度を確認</h4><p>実際の該当ハンドを確認します。</p></div><button type="button">関連ハンドを見る →</button></article>
  </div>
  <div id="jjV1244FocusHands" class="jj-v1244-focus-hands">
    <div class="jj-v1244-focus-hands-head"><div><span>RELATED HANDS</span><h4>3betに対するフォールドが多い傾向</h4></div><button class="text-btn">閉じる</button></div>
    <div class="jj-v1244-focus-hand-grid">
      <button><div><b>BTN</b><span>PREFLOP</span></div><strong>-4.5bb</strong><small>JJ Table · #101</small><em>09/11 15:30</em></button>
      <button><div><b>CO</b><span>PREFLOP</span></div><strong>+1.5bb</strong><small>JJ Table · #97</small><em>09/11 14:20</em></button>
      <button><div><b>HJ</b><span>FLOP</span></div><strong>-7bb</strong><small>JJ Table · #82</small><em>09/10 23:55</em></button>
    </div>
  </div>
</section>
<section class="jj-v1244-decision-panel card">
  <div class="jj-v1244-review-heading"><div><span>YOUR DECISIONS</span><h4>自分の意思決定</h4><p>Pot / Facing / サイズ / 時間を先に確認します。</p></div><small>3 decisions</small></div>
  <div class="jj-v1244-decision-list">
    <article class="jj-v1244-decision"><div class="jj-v1244-decision-index">01</div><div class="jj-v1244-decision-street"><span>PREFLOP</span><small>Pot 1.5bb</small></div><div class="jj-v1244-decision-action"><strong>レイズ</strong><b>to 2.5bb</b></div><div class="jj-v1244-decision-context"><span>Facing 1bb</span><small>4.2s</small></div></article>
    <article class="jj-v1244-decision"><div class="jj-v1244-decision-index">02</div><div class="jj-v1244-decision-street"><span>FLOP</span><small>Pot 5.5bb</small></div><div class="jj-v1244-decision-action"><strong>ベット</strong><b>1.8bb</b></div><div class="jj-v1244-decision-context"><span>Facing —</span><small>7.1s</small></div></article>
    <article class="jj-v1244-decision is-timeout"><div class="jj-v1244-decision-index">03</div><div class="jj-v1244-decision-street"><span>TURN</span><small>Pot 9.1bb</small></div><div class="jj-v1244-decision-action"><strong>フォールド</strong></div><div class="jj-v1244-decision-context"><span>Facing 6bb</span><small>45s</small><em>TIMEOUT</em></div></article>
  </div>
</section>
<details class="jj-v1244-full-flow card"><summary><span><b>全プレイヤーのアクションを見る</b><small>必要な場合だけ開く</small></span></summary><div style="padding:16px">ACTION FLOW</div></details>
</main>
<script>addEventListener('load',()=>requestAnimationFrame(()=>requestAnimationFrame(()=>{const q=s=>document.querySelector(s),all=s=>[...document.querySelectorAll(s)],r=q('.fixture').getBoundingClientRect(),checks={noPageOverflow:document.documentElement.scrollWidth<=innerWidth+2,fixtureContained:r.right<=innerWidth+1,focusButtonsTouch:all('.jj-v1244-focus-card button').every(b=>b.getBoundingClientRect().height>=44),handButtonsTouch:all('.jj-v1244-focus-hand-grid button').every(b=>b.getBoundingClientRect().height>=44),decisionContained:all('.jj-v1244-decision').every(x=>x.getBoundingClientRect().right<=innerWidth+1),detailsTouch:q('.jj-v1244-full-flow summary').getBoundingClientRect().height>=44,focusVisible:q('.jj-v1244-analysis-focus').getBoundingClientRect().height>180,decisionVisible:q('.jj-v1244-decision-panel').getBoundingClientRect().height>140};document.body.insertAdjacentHTML('beforeend',`<pre data-layout-ok="${Object.values(checks).every(Boolean)?'1':'0'}">${JSON.stringify(checks)}</pre>`)})));</script></body></html>'''


def _chrome() -> str:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    raise AssertionError("Chrome/Chromium is required")


def _run(chrome: str, fixture: Path, width: int, height: int) -> str:
    last = ""
    for _ in range(2):
        proc = subprocess.run(
            [chrome, "--headless", "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files",
             "--run-all-compositor-stages-before-draw", "--virtual-time-budget=3000",
             f"--window-size={width},{height}", "--dump-dom", fixture.resolve().as_uri()],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30,
        )
        last = proc.stdout
        if 'data-layout-ok=' in last:
            return last
    return last


def main() -> None:
    chrome = _chrome()
    with tempfile.TemporaryDirectory() as td:
        root = build_runtime(Path(td) / "runtime")
        fixture = root / "static" / "v1244-analysis-layout.html"
        fixture.write_text(FIXTURE, encoding="utf-8")
        desktop = _run(chrome, fixture, 1440, 1000)
        mobile = _run(chrome, fixture, 390, 844)
        assert 'data-layout-ok="1"' in desktop, desktop[-2200:]
        assert 'data-layout-ok="1"' in mobile, mobile[-2200:]
    print("JJ_V1244_ANALYSIS_LAYOUT_OK")


if __name__ == "__main__":
    main()
