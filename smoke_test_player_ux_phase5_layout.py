from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from player_ux_phase2 import transform_styles as phase2_css
from player_ux_phase3 import transform_styles as phase3_css
from player_ux_phase4 import transform_styles as phase4_css
from player_ux_phase5 import transform_styles as phase5_css
from player_ux_phase5_mobile import transform_styles as phase5_mobile_css


ROOT = Path(__file__).resolve().parent

FIXTURE = r'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><link rel="stylesheet" href="styles.css"></head><body class="jj-mobile-table-open"><section id="tablesView"><div id="pokerRoom"><div class="poker-layout"><div class="poker-zone card"><div id="actionBar" class="action-bar"><div class="jj-v124-waiting"><span>他のプレイヤーのアクション待ち</span><strong>73.5bb</strong></div><div class="jj-v5-preactions" aria-label="安全な先行アクション"><span>先行操作</span><button type="button" class="ghost is-selected">チェックのみ</button><button type="button" class="ghost">チェック / フォールド</button><small>コール・ベット・レイズは自動実行しません</small></div></div><div id="resultBanner" class="result-banner"><div class="jj-settlement-head"><b>ハンド精算</b><span>勝者 Player A</span><button type="button" class="ghost jj-v5-result-toggle">縮小</button></div><div class="jj-settlement-grid"><span id="gross">総ポット（卓全体） <b>42bb</b></span><span id="rake">レーキ（卓全体） <b>4.2bb</b></span><span id="mine">あなたの純損益 <strong>+18bb</strong></span><span id="rank">ランキング反映 <strong>+54pt</strong></span></div><div class="jj-settlement-actions"><button>直前のハンドを見る</button></div><small class="jj-settlement-note">投入内訳とアクションはハンド分析で確認できます。</small></div></div></div></div></section><script>addEventListener('load',()=>{const p=new URLSearchParams(location.search);if(p.get('compact')==='1')document.getElementById('resultBanner').classList.add('jj-v5-result-compact');setTimeout(()=>{const pre=document.querySelector('.jj-v5-preactions'),buttons=[...pre.querySelectorAll('button')],bar=document.getElementById('actionBar'),banner=document.getElementById('resultBanner'),toggle=document.querySelector('.jj-v5-result-toggle'),compact=p.get('compact')==='1',br=banner.getBoundingClientRect(),bs=getComputedStyle(banner);const fullContentReachable=compact||banner.scrollHeight<=banner.clientHeight+1||['auto','scroll','visible'].includes(bs.overflowY);const checks={preVisible:getComputedStyle(pre).display!=='none'&&pre.getBoundingClientRect().height>0&&getComputedStyle(bar).display!=='none',preButtonsUsable:buttons.every(b=>b.getBoundingClientRect().height>=30),mineVisible:getComputedStyle(document.getElementById('mine')).display!=='none',grossState:compact?getComputedStyle(document.getElementById('gross')).display==='none':getComputedStyle(document.getElementById('gross')).display!=='none',detailState:compact?getComputedStyle(document.querySelector('.jj-settlement-actions')).display==='none':getComputedStyle(document.querySelector('.jj-settlement-actions')).display!=='none',settlementInteractive:bs.pointerEvents!=='none'&&getComputedStyle(toggle).pointerEvents!=='none'&&toggle.getBoundingClientRect().height>=26,fullContentReachable,bannerInViewport:br.left>=-1&&br.right<=innerWidth+1,noHorizontalOverflow:document.documentElement.scrollWidth<=innerWidth+2};const ok=Object.values(checks).every(Boolean);document.body.insertAdjacentHTML('beforeend',`<pre id="result" data-ok="${ok?'1':'0'}">${JSON.stringify(checks)}</pre>`);},120)});</script></body></html>'''


def _chrome() -> str:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    raise AssertionError("Chrome/Chromium is required")


def _run(chrome: str, fixture: Path, width: int, height: int, compact: bool) -> str:
    proc = subprocess.run(
        [
            chrome,
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--allow-file-access-from-files",
            "--virtual-time-budget=1500",
            f"--window-size={width},{height}",
            "--dump-dom",
            fixture.resolve().as_uri() + f"?compact={1 if compact else 0}",
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )
    return proc.stdout


def main() -> None:
    chrome = _chrome()
    css = (ROOT / "materialized_v1244" / "static" / "styles.css").read_text(encoding="utf-8")
    css = phase5_mobile_css(phase5_css(phase4_css(phase3_css(phase2_css(css)))))
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "styles.css").write_text(css, encoding="utf-8")
        fixture = root / "fixture.html"
        fixture.write_text(FIXTURE, encoding="utf-8")
        for width, height in ((390, 844), (360, 800), (1366, 768)):
            for compact in (False, True):
                dom = _run(chrome, fixture, width, height, compact)
                assert 'data-ok="1"' in dom, f"phase5 layout failed {width}x{height} compact={compact}: {dom[-1800:]}"
    print("JJ_PLAYER_UX_PHASE5_LAYOUT_OK")


if __name__ == "__main__":
    main()
