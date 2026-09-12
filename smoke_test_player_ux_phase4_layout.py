from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from player_ux_phase2 import transform_styles as phase2_styles
from player_ux_phase3 import transform_styles as phase3_styles
from player_ux_phase4 import transform_styles as phase4_styles


ROOT = Path(__file__).resolve().parent

FIXTURE = r'''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><link rel="stylesheet" href="styles.css">
<style>.fixture-seat{position:absolute;left:50%;top:79%;transform:translate(-50%,-50%);z-index:6}.fixture-seat .jj-seat-box{width:108px}.fixture-seat .jj-hole{display:flex;justify-content:center}.fixture-seat .card-face{width:38px;height:53px}</style></head>
<body>
<div id="appView" class="app-shell"><aside class="sidebar"><nav><button class="nav active">卓</button></nav></aside><main class="main"><header class="topbar"><h2>JJ Arena</h2></header><section id="tablesView" class="view active-view"><div id="pokerRoom"><div class="room-head"><button id="backLobby" class="soft">← ロビー</button><div><div class="eyebrow">LIVE TABLE</div><h3 id="roomTitle">Table A</h3></div><div id="roomMeta" class="room-meta">6-max · 0.5/1bb · 150bb</div><button id="jjFocusModeToggle" class="ghost jj-focus-toggle">集中表示</button><div id="jjV4TableTools" class="jj-v4-table-tools"><button id="jjSizingSettingsOpen" class="ghost jj-v4-tool"><span class="jj-v4-tool-long">サイズ設定</span><span class="jj-v4-tool-short">⚙</span></button><button id="jjSideDrawerToggle" class="ghost jj-v4-tool" aria-expanded="false"><span class="jj-v4-tool-long">履歴・チャット</span><span class="jj-v4-tool-short">履歴</span></button></div></div><div class="poker-layout"><div class="poker-zone card"><div id="pokerTable"><div class="felt-center"><div class="cards board"><span class="card-face">A♠</span><span class="card-face">K♥</span><span class="card-face">Q♦</span></div><div class="pot-display">Pot 18.5bb</div><div class="hand-status">TURN · あなたの番です</div></div><div class="jj-seat is-hero fixture-seat"><div class="jj-hole"><span class="card-face">J♣</span><span class="card-face">10♣</span></div><div class="jj-seat-box"><div class="name">プレイヤー</div><div class="stack">73.5bb</div></div></div><div class="jj-bet-marker" style="left:50%;top:64%">4.5bb</div></div><div id="tableControls" class="table-controls"><span class="jj-ready-count">自動進行</span></div><div id="actionBar" class="action-bar"><div class="jj-v124-decision-meta"><div><span>STREET</span><strong>TURN</strong></div><div><span>POT</span><strong>18.5bb</strong></div><div><span>TO CALL</span><strong>4.5bb</strong></div><div><span>STACK</span><strong>73.5bb</strong></div><div><span>EFFECTIVE</span><strong>52bb</strong></div><div><span>TIME</span><strong>20秒</strong></div></div><div class="jj-sizing jj-v124-sizing"><div class="jj-size-row"><button class="jj-size-btn"><span>33%</span><small>11bb</small></button><button class="jj-size-btn"><span>50%</span><small>15bb</small></button><button class="jj-size-btn"><span>75%</span><small>22bb</small></button><button class="jj-size-btn"><span>POT</span><small>30bb</small></button><button class="jj-size-btn jj-allin-size"><span>ALL-IN</span><small>73.5bb</small></button></div><div class="jj-raise-editor jj-v124-raise-editor"><input id="raiseSlider" type="range" min="9" max="73.5" value="22"><div class="jj-v124-stepper"><button>−</button><label><input id="raiseTo" type="text" value="22"><span>BB</span></label><button>＋</button></div></div></div><div class="jj-main-actions jj-actions-3"><button class="jj-action-btn jj-fold"><small>FOLD</small><b>フォールド</b></button><button class="jj-action-btn jj-call"><small>CALL</small><b>コール 4.5bb</b></button><button class="jj-action-btn jj-raise"><small>RAISE · +17.5bb</small><b>レイズ 合計 22bb</b></button></div></div></div><aside id="tableSidePanel" class="card table-side"><div class="jj-v4-side-head"><strong>テーブル情報</strong><button id="jjSideDrawerClose" class="ghost">閉じる</button></div><div class="side-tabs"><button class="active">チャット</button><button>ハンド履歴</button></div><div id="tableChatPanel"><div id="tableMessages" class="table-messages"><div class="chat-message"><b>A</b> テストメッセージ</div></div><form id="tableChatForm" class="chat-form"><input id="tableChatInput" value=""><button class="primary">送信</button></form></div><div id="handLogPanel" class="hidden"><div id="handLog" class="hand-log">Player A raised to 4.5bb</div></div></aside><button id="jjSideDrawerBackdrop" aria-label="閉じる"></button></div></div></section></main></div>
<script>
function run(){const p=new URLSearchParams(location.search),mobile=p.get('mobile')==='1',keyboard=p.get('keyboard')==='1',drawer=p.get('drawer')==='1',compact=innerWidth<=1000;if(mobile)document.body.classList.add('jj-mobile-table-open','jj-mobile-poker-can-act');if(keyboard){document.body.classList.add('jj-poker-keyboard-open');document.documentElement.style.setProperty('--jj-vv-bottom','240px')}if(drawer)document.body.classList.add('jj-poker-side-open');document.getElementById('jjSideDrawerToggle').hidden=!compact;
const action=document.getElementById('actionBar'),ar=action.getBoundingClientRect(),side=document.getElementById('tableSidePanel'),sr=side.getBoundingClientRect(),small=document.querySelector('#actionBar .jj-size-btn small'),stack=document.querySelector('.jj-seat-box .stack'),decision=document.querySelector('#actionBar .jj-v124-decision-meta strong');const limit=keyboard?innerHeight-240:innerHeight;const checks={noHorizontalPageOverflow:document.documentElement.scrollWidth<=innerWidth+2,actionNoHorizontalOverflow:action.scrollWidth<=action.clientWidth+2,actualTargetVisible:getComputedStyle(small).display!=='none'&&small.getBoundingClientRect().height>0,noActionSettings:!action.querySelector('[data-jj-sizing-settings],.jj-size-settings'),mobileStackReadable:!mobile||parseFloat(getComputedStyle(stack).fontSize)>=12,mobileDecisionReadable:!mobile||parseFloat(getComputedStyle(decision).fontSize)>=11,drawerOpenVisible:!drawer||(getComputedStyle(side).display!=='none'&&parseFloat(getComputedStyle(side).opacity)>.9&&sr.left>=-2&&sr.right<=innerWidth+2&&sr.top>=0&&sr.bottom<=innerHeight+2),drawerClosedNonBlocking:drawer||!compact||parseFloat(getComputedStyle(side).opacity)<.1,keyboardAboveInset:!keyboard||(ar.bottom<=limit+4&&ar.top>=0),settingsVisible:document.getElementById('jjSizingSettingsOpen').getBoundingClientRect().width>20};const ok=Object.values(checks).every(Boolean);document.body.insertAdjacentHTML('beforeend',`<pre id="result" data-ok="${ok?'1':'0'}">${JSON.stringify(checks)}</pre>`)}addEventListener('load',()=>setTimeout(run,120));
</script></body></html>'''


def _chrome() -> str:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    raise AssertionError("Chrome/Chromium is required")


def _run(chrome: str, fixture: Path, width: int, height: int, *, mobile: bool, keyboard: bool, drawer: bool) -> str:
    q = f"?mobile={1 if mobile else 0}&keyboard={1 if keyboard else 0}&drawer={1 if drawer else 0}"
    proc = subprocess.run(
        [chrome, "--headless", "--no-sandbox", "--disable-gpu", "--allow-file-access-from-files", "--run-all-compositor-stages-before-draw", "--virtual-time-budget=2500", f"--window-size={width},{height}", "--dump-dom", fixture.resolve().as_uri() + q],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30,
    )
    return proc.stdout


def main() -> None:
    chrome = _chrome()
    css = (ROOT / "materialized_v1244" / "static" / "styles.css").read_text(encoding="utf-8")
    css = phase4_styles(phase3_styles(phase2_styles(css)))
    cases = [
        (1440, 900, False, False, False),
        (900, 800, False, False, True),
        (390, 844, True, False, True),
        (360, 800, True, False, False),
        (390, 844, True, True, False),
    ]
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "styles.css").write_text(css, encoding="utf-8")
        fixture = root / "fixture.html"
        fixture.write_text(FIXTURE, encoding="utf-8")
        for width, height, mobile, keyboard, drawer in cases:
            dom = _run(chrome, fixture, width, height, mobile=mobile, keyboard=keyboard, drawer=drawer)
            assert 'data-ok="1"' in dom, f"phase4 layout failed {width}x{height} mobile={mobile} keyboard={keyboard} drawer={drawer}: {dom[-2200:]}"
    print("JJ_PLAYER_UX_PHASE4_LAYOUT_OK")


if __name__ == "__main__":
    main()
