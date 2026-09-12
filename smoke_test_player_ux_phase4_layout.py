from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from player_ux_phase2 import transform_styles as phase2_styles
from player_ux_phase3 import transform_styles as phase3_styles
from player_ux_phase4 import transform_styles as phase4_styles


ROOT = Path(__file__).resolve().parent

FIXTURE = r'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><link rel="stylesheet" href="styles.css"></head><body class="jj-mobile-table-open jj-mobile-poker-can-act"><section id="tablesView"><div id="pokerRoom"><div class="room-head"><button class="soft">← ロビー</button><h3>Table A</h3><div class="jj-v4-mobile-tools"><button>履歴</button><button>チャット</button></div></div><div class="poker-layout"><div class="poker-zone card"><div id="pokerTable"></div><div id="actionBar" class="action-bar"><div class="jj-v124-decision-meta"><div><span>STACK</span><strong>73.5bb</strong></div><div><span>TO CALL</span><strong>4.5bb</strong></div><div><span>TIME</span><strong>18秒</strong></div></div><div class="jj-sizing jj-v124-sizing"><div class="jj-size-row"><button class="jj-size-btn"><span>33%</span><small id="actualTotal">11bb</small></button><button class="jj-size-btn"><span>50%</span><small>15bb</small></button></div></div></div></div><aside id="side" class="card table-side"><div class="jj-v4-side-head"><strong>テーブル情報</strong><button>閉じる</button></div><div class="side-tabs"><button>チャット</button><button>ハンド履歴</button></div><div>直前のアクション</div></aside></div></div></section><script>addEventListener('load',()=>{const p=new URLSearchParams(location.search);if(p.get('open')==='1')document.body.classList.add('jj-v4-side-open');setTimeout(()=>{const small=document.getElementById('actualTotal'),side=document.getElementById('side'),sr=side.getBoundingClientRect(),ss=getComputedStyle(small),ds=getComputedStyle(side);const open=p.get('open')==='1';const checks={actualTotalVisible:ss.display!=='none'&&small.getBoundingClientRect().height>0,drawerState:open?ds.display!=='none':ds.display==='none',drawerInViewport:!open||(sr.left>=0&&sr.right<=innerWidth+1&&sr.bottom<=innerHeight+1),noHorizontalOverflow:document.documentElement.scrollWidth<=innerWidth+2};const ok=Object.values(checks).every(Boolean);document.body.insertAdjacentHTML('beforeend',`<pre id="result" data-ok="${ok?'1':'0'}">${JSON.stringify(checks)}</pre>`);},100)});</script></body></html>'''


def _chrome() -> str:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    raise AssertionError("Chrome/Chromium is required")


def _run(chrome: str, fixture: Path, width: int, height: int, *, open_drawer: bool) -> str:
    proc = subprocess.run(
        [chrome, "--headless", "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files", "--virtual-time-budget=1800", f"--window-size={width},{height}", "--dump-dom", fixture.resolve().as_uri() + f"?open={1 if open_drawer else 0}"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30,
    )
    return proc.stdout


def main() -> None:
    chrome = _chrome()
    css = (ROOT / "materialized_v1244" / "static" / "styles.css").read_text(encoding="utf-8")
    css = phase4_styles(phase3_styles(phase2_styles(css)))
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "styles.css").write_text(css, encoding="utf-8")
        fixture = root / "fixture.html"
        fixture.write_text(FIXTURE, encoding="utf-8")
        for width, height in ((390, 844), (360, 800)):
            for open_drawer in (False, True):
                dom = _run(chrome, fixture, width, height, open_drawer=open_drawer)
                assert 'data-ok="1"' in dom, f"phase4 layout failed {width}x{height} open={open_drawer}: {dom[-1400:]}"
    print("JJ_PLAYER_UX_PHASE4_LAYOUT_OK")


if __name__ == "__main__":
    main()
