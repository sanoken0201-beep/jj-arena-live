from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from runtime_builder import build_runtime


FIXTURE = r'''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="styles.css">
<style>html,body{margin:0;background:#07100d;color:#eef6f2}.fixture{width:100%;max-width:1180px;margin:auto;padding:16px;box-sizing:border-box}.view{display:block!important}.card{background:#13211c;border:1px solid rgba(255,255,255,.11);border-radius:16px}button{font:inherit}.section{margin-bottom:28px}.jj-home-hub-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}</style></head><body>
<div class="fixture">
<section class="section"><div id="jjHomeHubGrid" class="jj-home-hub-grid">
<article class="card jj-v1243-focus"><div class="jj-v1243-focus-copy"><span>TODAY · PRIORITY</span><h3>今日のクイズをあと7問</h3><p>3/10問完了 · 本日 +30pt。残り最大 +70pt。</p></div><div class="jj-v1243-focus-side"><button class="primary">続きを解く →</button><small>最初にやることを1つだけ表示しています</small></div></article>
<article class="card jj-v1243-metric"><span>今日のクイズ</span><div><strong>3<small>/10</small></strong><em>+30pt</em></div><div class="jj-v1243-meter"><i style="width:30%"></i></div><small>残り7問 · 報酬 30%</small><button class="soft">クイズへ</button></article>
<article class="card jj-v1243-metric"><span>後期ポイント</span><div><strong>4250<small>pt</small></strong><em>#2</em></div><small>現在のシーズン順位</small><button class="soft">ランキングを見る</button></article>
<article class="card jj-v1243-metric"><span>直近30日</span><div><strong>+18.4bb</strong><em>142 hands</em></div><small>+12.9bb/100</small><button class="soft">分析を見る</button></article>
<article class="card jj-v1243-learning"><div><span>RECOMMENDED REVIEW</span><h4>BB vs Stealでfoldが多い</h4><p>Stealに直面した42回のうち72%でfoldしています。</p></div><button class="soft">根拠を見る →</button></article>
<article class="card jj-v1243-hands"><div class="jj-v1243-card-head"><div><span>RECENT HANDS</span><h4>最近のハンド</h4></div><button class="text-btn">すべて見る →</button></div><div class="jj-v1243-hand-list"><button><b>BTN</b><em>+12.5bb</em><small>今日 12:30</small></button><button><b>BB</b><em>-4bb</em><small>昨日 23:10</small></button></div></article>
</div></section>
<section class="section"><div id="quizStage"><div class="jj-v1243-quiz-head"><div><span>DAILY QUIZ</span><strong>3<small> / 10</small></strong></div><div class="jj-v1243-quiz-progress"><div><b>進捗</b><span>30%</span></div><div class="jj-v1243-meter"><i style="width:30%"></i></div><div class="jj-v1243-quiz-reward-row"><span>今日 +30pt</span><small>最大 100pt · 30%</small></div></div></div><div class="jj-v1243-question-meta"><span>ICM / トーナメント</span><b>問題 4 / 10</b></div><p class="jj-quiz-prompt">バブル付近でスタック差が大きい場面です。最も適切な考え方を選んでください。</p></div><div id="quizChoices"><button data-daily-answer="a"><span>A</span><b>チップEVだけを基準に判断する</b></button><button data-daily-answer="b"><span>B</span><b>ICMによるリスクプレミアムも考慮する</b></button></div></section>
<section class="section"><div class="jj-v1243-ranking-summary"><div class="jj-v1243-ranking-head"><div><span>YOUR SEASON</span><h3>ランキングの現在地</h3><p>合計だけでなく、順位差とポイントの内訳を確認できます。</p></div><button class="soft">更新</button></div><div class="jj-v1243-ranking-grid"><article class="card jj-v1243-rank-me"><span>後期シーズン</span><div><strong>#2</strong><b>4250 pt</b></div><p>#1 リョウまであと 230pt</p><div class="jj-v1243-rank-sub"><span>今月 <b>#1 · 830pt</b></span><span>記録 <b>26</b></span></div></article><article class="card jj-v1243-rank-breakdown"><span>ポイント内訳</span><div><div class="jj-v1243-break-row"><p><span>サークル</span><b>+3100pt</b></p><div class="jj-v1243-meter"><i style="width:73%"></i></div></div><div class="jj-v1243-break-row"><p><span>台帳・クイズ等</span><b>+1150pt</b></p><div class="jj-v1243-meter"><i style="width:27%"></i></div></div></div></article><article class="card jj-v1243-rank-top"><div class="jj-v1243-card-head"><div><span>TOP 5</span><h4>上位の現在地</h4></div><small>1位 リョウ</small></div><div><div class="jj-v1243-rank-row"><b>#1</b><span>リョウ</span><div><i style="width:100%"></i></div><strong>4480pt</strong></div><div class="jj-v1243-rank-row is-me"><b>#2</b><span>ケンイチロウ</span><div><i style="width:95%"></i></div><strong>4250pt</strong></div></div></article></div></div></section>
</div><script>addEventListener('load',()=>{const root=document.querySelector('.fixture'),quizButtons=[...document.querySelectorAll('#quizChoices button')],checks={noPageOverflow:document.documentElement.scrollWidth<=innerWidth+2,fixtureContained:root.getBoundingClientRect().right<=innerWidth+1,quizButtonsTouch:quizButtons.every(b=>b.getBoundingClientRect().height>=44),homeFocusVisible:document.querySelector('.jj-v1243-focus').getBoundingClientRect().height>80,rankingVisible:document.querySelector('.jj-v1243-ranking-grid').getBoundingClientRect().height>100};document.body.insertAdjacentHTML('beforeend',`<pre data-layout-ok="${Object.values(checks).every(Boolean)?'1':'0'}">${JSON.stringify(checks)}</pre>`)});</script></body></html>'''


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
            [chrome, "--headless", "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files", "--run-all-compositor-stages-before-draw", "--virtual-time-budget=3000", f"--window-size={width},{height}", "--dump-dom", fixture.resolve().as_uri()],
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
        fixture = root / "static" / "v1243-non-poker-layout.html"
        fixture.write_text(FIXTURE, encoding="utf-8")
        desktop = _run(chrome, fixture, 1440, 1000)
        mobile = _run(chrome, fixture, 390, 844)
        assert 'data-layout-ok="1"' in desktop, desktop[-1800:]
        assert 'data-layout-ok="1"' in mobile, mobile[-1800:]
    print("JJ_V1243_NON_POKER_LAYOUT_OK")


if __name__ == "__main__":
    main()
