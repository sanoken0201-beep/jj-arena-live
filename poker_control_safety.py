from __future__ import annotations

"""Final browser-asset safety layer for non-betting table controls.

The poker action pipeline already has receipt/idempotency protection. READY,
presence and immediate-leave controls historically predate that pipeline and
could either stay disabled after a failed request or submit twice on a rapid
double tap. This transform intercepts those controls in capture phase and gives
them one in-flight request at a time.

It also clears the two-tap all-in confirmation whenever the action bar is fully
rerendered. A confirmation is visual state; if the confirming DOM is replaced,
its authorization must be replaced with it rather than survive invisibly.
"""

import hashlib
import json
from pathlib import Path

MARKER = "v72 poker control safety 2026-09-16"
CACHE_QUERY = "cs=control-safety-20260916-1"

_ACTION_RENDER_ANCHOR = """  renderActionBar=function(){
    const bar=$('#actionBar');if(!bar)return;
"""
_ACTION_RENDER_REPLACEMENT = """  renderActionBar=function(){
    const bar=$('#actionBar');if(!bar)return;
    // All-in confirmation is valid only while its visibly-confirming control
    // remains on screen. Any complete action-bar rerender invalidates it.
    if(typeof jjV123AllinConfirmUntil!=='undefined')jjV123AllinConfirmUntil=0;
    if(typeof jjV123AllinConfirmKey!=='undefined')jjV123AllinConfirmKey='';
"""

_LISTENER_ANCHOR = "  // Desktop bet markers use explicit poker-table lanes rather than the old\n"
_LISTENERS = r'''  // v72 poker control safety 2026-09-16
  function jjV72ControlBusy(button){
    if(!button||button.dataset.jjControlBusy==='1')return true;
    button.dataset.jjControlBusy='1';button.disabled=true;return false;
  }
  function jjV72ControlRelease(button){
    if(!button||!button.isConnected)return;
    delete button.dataset.jjControlBusy;button.disabled=false;
  }
  function jjV72PresenceToast(mode){
    return mode==='sitout'?'一時離席を設定しました':mode==='return'?'次ハンドから参加します':mode==='rebuy'?'150bbでリバイしました':mode==='unready'?'開始準備を取り消しました':'一時離席予約を取り消しました';
  }
  document.addEventListener('click',async e=>{
    const ready=e.target.closest?.('#jjReadyBtn');
    if(ready){
      e.preventDefault();e.stopImmediatePropagation();
      if(jjV72ControlBusy(ready))return;
      try{await post(`/tables/${currentTableId}/start`);toast('開始準備を完了しました')}
      catch(err){jjV72ControlRelease(ready);toast(err.message)}
      return;
    }
    const presence=e.target.closest?.('[data-table-presence]');
    if(presence){
      e.preventDefault();e.stopImmediatePropagation();
      if(jjV72ControlBusy(presence))return;
      const mode=presence.dataset.tablePresence;
      try{await post(`/tables/${currentTableId}/presence`,{mode});toast(jjV72PresenceToast(mode))}
      catch(err){jjV72ControlRelease(presence);toast(err.message)}
      return;
    }
    const leave=e.target.closest?.('#leaveSeatBtn');
    if(leave){
      e.preventDefault();e.stopImmediatePropagation();
      if(jjV72ControlBusy(leave))return;
      try{
        await post(`/tables/${currentTableId}/leave`);
        const d=await api('/tables/'+currentTableId);
        tableState=d.state;tableMessages=d.messages||[];renderPokerRoom();await refreshMe();toast('テーブルから退席しました');
      }catch(err){jjV72ControlRelease(leave);toast(err.message)}
      return;
    }
  },true);

'''


def transform_app_js(source: str) -> str:
    if MARKER in source:
        return source
    if source.count(_ACTION_RENDER_ANCHOR) != 1:
        raise RuntimeError("poker control safety drift: action renderer anchor not found exactly once")
    if source.count(_LISTENER_ANCHOR) != 1:
        raise RuntimeError("poker control safety drift: listener anchor not found exactly once")
    source = source.replace(_ACTION_RENDER_ANCHOR, _ACTION_RENDER_REPLACEMENT, 1)
    return source.replace(_LISTENER_ANCHOR, _LISTENERS + _LISTENER_ANCHOR, 1)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def apply_to_build(output_root: Path | str, manifest: dict) -> dict:
    root = Path(output_root)
    app_path = root / "static/app.js"
    index_path = root / "index.html"

    app_js = transform_app_js(app_path.read_text(encoding="utf-8"))
    app_path.write_text(app_js, encoding="utf-8", newline="\n")

    index = index_path.read_text(encoding="utf-8")
    asset_version = int(manifest.get("asset_version", 0))
    base = f"/static/app.js?v={asset_version}"
    if CACHE_QUERY not in index:
        # Preserve any earlier cache-buster query and append the control-safety
        # identity to the same app.js URL.
        needle = base
        if index.count(needle) != 1:
            raise RuntimeError("poker control safety drift: app.js asset URL not found exactly once")
        start = index.index(needle)
        end = index.find('"', start)
        if end < 0:
            raise RuntimeError("poker control safety drift: app.js URL terminator missing")
        current = index[start:end]
        separator = '&' if '?' in current else '?'
        index = index[:start] + current + separator + CACHE_QUERY + index[end:]
    index_path.write_text(index, encoding="utf-8", newline="\n")

    outputs = dict(manifest.get("outputs") or {})
    outputs["static/app.js"] = _digest(app_js)
    outputs["index.html"] = _digest(index)
    manifest["outputs"] = outputs
    post = dict(manifest.get("post_transforms") or {})
    post["poker_control_safety"] = MARKER
    manifest["post_transforms"] = post
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


__all__ = ["CACHE_QUERY", "MARKER", "apply_to_build", "transform_app_js"]
