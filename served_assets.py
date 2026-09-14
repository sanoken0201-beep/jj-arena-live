"""Deterministic build-time compiler for JJ Arena's served browser assets.

`materialized_v1244/static` is the immutable canonical input.  Production must
serve the compiled output under `.jj_build/` instead of executing the historical
UX transform chain on visitor requests or process startup.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from hand_history_visibility import (
    HAND_HISTORY_VISIBILITY_MARKER,
    transform_app_js as transform_hand_history_app_js,
    transform_styles as transform_hand_history_styles,
)
from player_ux_asset_transform import PLAYER_UX_MARKER, transform_app_js
from player_ux_clear_copy import (
    CLEAR_COPY_MARKER,
    transform_app_js as transform_clear_copy_app_js,
    transform_styles as transform_clear_copy_styles,
)
from player_ux_phase2 import (
    PHASE2_MARKER,
    transform_app_js as transform_phase2_app_js,
    transform_styles as transform_phase2_styles,
)
from player_ux_phase3 import (
    PHASE3_MARKER,
    transform_app_js as transform_phase3_app_js,
    transform_styles as transform_phase3_styles,
)
from player_ux_phase4 import (
    PHASE4_MARKER,
    transform_app_js as transform_phase4_app_js,
    transform_styles as transform_phase4_styles,
)
from player_ux_phase5 import (
    PHASE5_MARKER,
    transform_app_js as transform_phase5_app_js,
    transform_styles as transform_phase5_styles,
)
from player_ux_phase5_mobile import (
    PHASE5_MOBILE_MARKER,
    transform_styles as transform_phase5_mobile_styles,
)
from player_ux_phase6 import PHASE6_MARKER, transform_app_js as transform_phase6_app_js

from poker_simple import transform_app_js as simple_app_js, transform_styles as simple_styles

ROOT = Path(__file__).resolve().parent
MATERIALIZED_STATIC = ROOT / "materialized_v1244" / "static"
BUILD_ROOT = ROOT / ".jj_build"
ASSET_VERSION = 70
BUILD_FORMAT = 1

_TODAYS_JJ_MARKER = "v2 today's-jj contrast hardening 2026-09-12"
_TODAYS_JJ_CSS = r'''

/* v2 today's-jj contrast hardening 2026-09-12
   These rules intentionally target the cards themselves, not only their parent
   learning shell. The home layout has changed several times and the text must
   remain readable even if a card is moved to another container. */
.jj-study-card,
.jj-video-card{
  color:#f4f8f6!important;
  -webkit-text-fill-color:currentColor;
}
.jj-study-card:link,
.jj-study-card:visited,
.jj-video-card:link,
.jj-video-card:visited{
  color:#f4f8f6!important;
  -webkit-text-fill-color:#f4f8f6!important;
}
.jj-study-card h3,
.jj-video-card h3{
  color:#ffffff!important;
  -webkit-text-fill-color:#ffffff!important;
  opacity:1!important;
  text-shadow:0 1px 2px rgba(0,0,0,.32)!important;
}
.jj-study-card p,
.jj-video-card p{
  color:#d7e2dc!important;
  -webkit-text-fill-color:#d7e2dc!important;
  opacity:1!important;
}
.jj-study-meta,
.jj-study-meta>span:not(.jj-study-source){
  color:#c4d0ca!important;
  -webkit-text-fill-color:#c4d0ca!important;
  opacity:1!important;
}
.jj-study-source,
.jj-video-kind{
  color:#a8ebcb!important;
  -webkit-text-fill-color:#a8ebcb!important;
  opacity:1!important;
}
.jj-video-kind.is-motivation{
  color:#f6dc8d!important;
  -webkit-text-fill-color:#f6dc8d!important;
  opacity:1!important;
}
.jj-study-card footer,
.jj-video-card footer,
.jj-study-card footer>span,
.jj-video-card footer>span{
  color:#c4d0ca!important;
  -webkit-text-fill-color:#c4d0ca!important;
  opacity:1!important;
}
.jj-study-card footer b,
.jj-video-card footer b{
  color:#ffe08a!important;
  -webkit-text-fill-color:#ffe08a!important;
  opacity:1!important;
}
@media(max-width:760px){
  .jj-study-card h3,.jj-video-card h3{
    font-size:.92rem!important;
    line-height:1.52!important;
    font-weight:800!important;
  }
  .jj-study-meta{font-size:.68rem!important}
  .jj-study-card footer,.jj-video-card footer{font-size:.7rem!important}
}
'''

_PWA_UPDATE_MARKER = "v69 pwa update prompt 2026-09-13"
_PWA_UPDATE_CSS = r'''

/* v69 pwa update prompt 2026-09-13 */
.jj-update-banner{
  position:fixed;
  z-index:10000;
  left:50%;
  bottom:max(16px,env(safe-area-inset-bottom));
  transform:translateX(-50%);
  width:min(560px,calc(100vw - 24px));
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:14px;
  padding:12px 14px;
  border:1px solid rgba(255,255,255,.15);
  border-radius:14px;
  background:rgba(18,34,27,.97);
  color:#f4f8f6;
  box-shadow:0 12px 36px rgba(0,0,0,.3);
}
.jj-update-banner span{display:grid;gap:2px;min-width:0}
.jj-update-banner strong{font-size:.9rem;line-height:1.35}
.jj-update-banner small{color:#c4d0ca;font-size:.74rem;line-height:1.4}
.jj-update-banner button{
  flex:0 0 auto;
  min-height:38px;
  padding:0 14px;
  border:0;
  border-radius:10px;
  font-weight:800;
  cursor:pointer;
}
.jj-update-banner button:disabled{opacity:.65;cursor:wait}
@media(max-width:560px){
  .jj-update-banner{align-items:stretch;flex-direction:column;gap:9px}
  .jj-update-banner button{width:100%}
}
'''

_PWA_REGISTRATION = "if('serviceWorker' in navigator && location.protocol.startsWith('http')) navigator.serviceWorker.register('/static/sw.js').catch(()=>{});"
_PWA_REGISTRATION_REPLACEMENT = r'''/* v69 pwa update prompt 2026-09-13 */
  let jjUpdateRequested=false,jjUpdateReloading=false;
  function jjShowAppUpdate(reg){
    if(!reg?.waiting||document.getElementById('jjUpdateBanner'))return;
    const banner=document.createElement('div');
    banner.id='jjUpdateBanner';banner.className='jj-update-banner';
    banner.setAttribute('role','status');banner.setAttribute('aria-live','polite');
    banner.innerHTML='<span><strong>新しいバージョンがあります</strong><small>ハンド中でない時に更新してください。</small></span><button type="button">更新する</button>';
    const button=banner.querySelector('button');
    button.addEventListener('click',()=>{
      if(!reg.waiting)return;
      jjUpdateRequested=true;button.disabled=true;button.textContent='更新中…';
      reg.waiting.postMessage({type:'SKIP_WAITING'});
    });
    document.body.appendChild(banner);
  }
  if('serviceWorker' in navigator && location.protocol.startsWith('http')){
    navigator.serviceWorker.addEventListener('controllerchange',()=>{
      if(!jjUpdateRequested||jjUpdateReloading)return;
      jjUpdateReloading=true;location.reload();
    });
    navigator.serviceWorker.register('/static/sw.js').then(reg=>{
      if(reg.waiting&&navigator.serviceWorker.controller)jjShowAppUpdate(reg);
      reg.addEventListener('updatefound',()=>{
        const worker=reg.installing;if(!worker)return;
        worker.addEventListener('statechange',()=>{
          if(worker.state==='installed'&&navigator.serviceWorker.controller)jjShowAppUpdate(reg);
        });
      });
      reg.update().catch(()=>{});
    }).catch(()=>{});
  }'''


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest_text(value: str) -> str:
    return _digest_bytes(value.encode("utf-8"))


def _read(name: str) -> str:
    return (MATERIALIZED_STATIC / name).read_text(encoding="utf-8")


def build_index() -> str:
    html = _read("index.html")
    html = html.replace('/static/styles.css?v=56', f'/static/styles.css?v={ASSET_VERSION}')
    html = html.replace('/static/app.js?v=56', f'/static/app.js?v={ASSET_VERSION}')
    html = html.replace('← Lobby', '← ロビー')
    html = html.replace('>Table Chat<', '>チャット<').replace('>Hand Log<', '>ハンド履歴<')
    html = html.replace('Waiting for players', '着席者を待っています')
    html = html.replace(
        'JJ内の練習用プレイマネーテーブルです。A/Bの2卓のみ、6-max、0.5/1bb、着席時150bb固定。各ハンドは10% rake・5bb capで、結果は1bb=3ptとして後期ランキングへ自動反映されます。テーブル画面との接続・操作が15分ない場合、ハンド終了後に自動離席します。',
        'プレイマネー｜6-max｜0.5/1bb｜150bb固定｜rake 10%・5bb cap｜ランキング 1bb=3pt｜15分無操作でハンド終了後に自動離席',
    )
    return html


def build_app_js() -> str:
    js = _read("app.js")
    js = transform_hand_history_app_js(js)
    js = transform_phase5_app_js(
        transform_phase4_app_js(
            transform_phase3_app_js(
                transform_phase2_app_js(transform_app_js(js))
            )
        )
    )
    js = transform_clear_copy_app_js(js)

    ws_handler = "tableWS.onmessage=e=>{try{const m=JSON.parse(e.data);if(m.type==='state'){const previous=tableState;tableState=m.state;tableMessages=m.messages||[];renderPokerRoom();jjV2AcceptState('ws',previous);refreshMe().catch(()=>{})}}catch{}};"
    ws_handler_optimized = "tableWS.onmessage=e=>{try{const m=JSON.parse(e.data);if(m.type==='state'){const previous=tableState;tableState=m.state;if(Array.isArray(m.messages))tableMessages=m.messages;renderPokerRoom();jjV2AcceptState('ws',previous)}else if(m.type==='chat'){tableMessages=m.messages||[];renderTableChat()}}catch{}};"
    if js.count(ws_handler) != 1:
        raise RuntimeError("production websocket handler drift: expected one Phase 2 state handler")
    js = js.replace(ws_handler, ws_handler_optimized, 1)

    # Compatibility guard for any remaining pre-Phase-2 renderer copy.
    js = js.replace("renderPokerRoom();refreshMe().catch(()=>{})", "renderPokerRoom()")
    # showApp() already refreshes the visible view through switchView().
    js = js.replace("showApp();await refreshAll()", "showApp()")
    js = simple_app_js(transform_phase6_app_js(js))
    if js.count(_PWA_REGISTRATION) != 1:
        raise RuntimeError("service worker registration drift: expected one canonical registration")
    return js.replace(_PWA_REGISTRATION, _PWA_REGISTRATION_REPLACEMENT, 1)


def build_styles() -> str:
    css = _read("styles.css")
    if _TODAYS_JJ_MARKER not in css:
        css = css.rstrip() + _TODAYS_JJ_CSS + "\n"
    css = transform_hand_history_styles(css)
    css = transform_phase5_mobile_styles(
        transform_phase5_styles(
            transform_phase4_styles(
                transform_phase3_styles(transform_phase2_styles(css))
            )
        )
    )
    css = transform_clear_copy_styles(css)
    if _PWA_UPDATE_MARKER not in css:
        css = css.rstrip() + _PWA_UPDATE_CSS + "\n"
    return simple_styles(css)


def build_service_worker() -> str:
    worker = _read("sw.js")
    worker = worker.replace("const CACHE='jj-arena-live-v56';", f"const CACHE='jj-arena-live-v{ASSET_VERSION}';")
    worker = worker.replace("'/static/styles.css?v=19'", f"'/static/styles.css?v={ASSET_VERSION}'")
    worker = worker.replace("'/static/app.js?v=19'", f"'/static/app.js?v={ASSET_VERSION}'")
    old_install = "self.addEventListener('install',e=>{self.skipWaiting();e.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL)))});"
    new_install = "self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL)))});"
    if worker.count(old_install) != 1:
        raise RuntimeError("service worker install handler drift")
    worker = worker.replace(old_install, new_install, 1)
    worker = worker.replace(
        new_install,
        new_install + "\nself.addEventListener('message',e=>{if(e.data&&e.data.type==='SKIP_WAITING')self.skipWaiting()});",
        1,
    )
    return worker


def _atomic_write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    temporary.replace(path)


def build_all(output_root: Path | str = BUILD_ROOT) -> dict:
    output_root = Path(output_root)
    outputs = {
        "index.html": build_index(),
        "static/app.js": build_app_js(),
        "static/styles.css": build_styles(),
        "static/sw.js": build_service_worker(),
    }
    for relative, value in outputs.items():
        _atomic_write(output_root / relative, value)

    sources = {
        name: _digest_bytes((MATERIALIZED_STATIC / name).read_bytes())
        for name in ("index.html", "app.js", "styles.css", "sw.js")
    }
    manifest = {
        "format": BUILD_FORMAT,
        "asset_version": ASSET_VERSION,
        "canonical_core": "materialized_v1244",
        "sources": sources,
        "outputs": {name: _digest_text(value) for name, value in outputs.items()},
    }
    _atomic_write(
        output_root / "manifest.json",
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    )
    return manifest


def validate_built_assets(output_root: Path | str = BUILD_ROOT) -> dict:
    output_root = Path(output_root)
    manifest_path = output_root / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"served asset manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if int(manifest.get("format", -1)) != BUILD_FORMAT:
        raise RuntimeError("served asset build format mismatch")
    if int(manifest.get("asset_version", -1)) != ASSET_VERSION:
        raise RuntimeError("served asset version mismatch")
    if manifest.get("canonical_core") != "materialized_v1244":
        raise RuntimeError("served asset canonical core mismatch")

    expected_sources = manifest.get("sources") or {}
    for name in ("index.html", "app.js", "styles.css", "sw.js"):
        path = MATERIALIZED_STATIC / name
        if expected_sources.get(name) != _digest_bytes(path.read_bytes()):
            raise RuntimeError(f"served asset source drift: {name}")

    expected_outputs = manifest.get("outputs") or {}
    for relative in ("index.html", "static/app.js", "static/styles.css", "static/sw.js"):
        path = output_root / relative
        if not path.is_file():
            raise RuntimeError(f"served asset output is missing: {relative}")
        if expected_outputs.get(relative) != _digest_bytes(path.read_bytes()):
            raise RuntimeError(f"served asset output drift: {relative}")
    return manifest


def ensure_runtime_assets() -> Path:
    """Return validated assets; production never compiles them at runtime."""
    try:
        validate_built_assets(BUILD_ROOT)
    except Exception as exc:
        if os.getenv("RENDER"):
            raise RuntimeError(
                "prebuilt served assets are unavailable in production; "
                "run `python build_served_assets.py` during the Render build"
            ) from exc
        # Local/test compatibility only. Production builds must precompile.
        build_all(BUILD_ROOT)
        validate_built_assets(BUILD_ROOT)
    return BUILD_ROOT


__all__ = [
    "ASSET_VERSION",
    "BUILD_ROOT",
    "CLEAR_COPY_MARKER",
    "HAND_HISTORY_VISIBILITY_MARKER",
    "PHASE2_MARKER",
    "PHASE3_MARKER",
    "PHASE4_MARKER",
    "PHASE5_MARKER",
    "PHASE5_MOBILE_MARKER",
    "PHASE6_MARKER",
    "PLAYER_UX_MARKER",
    "build_all",
    "build_app_js",
    "build_index",
    "build_service_worker",
    "build_styles",
    "ensure_runtime_assets",
    "validate_built_assets",
]
