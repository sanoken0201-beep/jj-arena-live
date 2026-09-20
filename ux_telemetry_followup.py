from __future__ import annotations

"""Final low-overhead UX telemetry completion layer.

This post-build transform fills the measurement gaps left by the original
privacy-preserving telemetry: successful reconnect-to-fresh-state recovery,
seat-to-READY timing, table-to-review usage, bookmarks, and rejected betting
requests. It adds no polling loop and stores no identity, hand/table ids,
cards, chip amounts, or free text.
"""

import hashlib
import json
from pathlib import Path

MARKER = "v73 ux telemetry followup 2026-09-20"
CACHE_QUERY = "uxf=followup-20260920-1"
_ANCHOR = "  // Desktop bet markers use explicit poker-table lanes rather than the old\n"

_HELPERS = r'''
  // v73 ux telemetry followup 2026-09-20
  let jjV73ReadyStartedAt=0;
  function jjV73ReadyStart(){
    jjV73ReadyStartedAt=performance.now();
  }
  function jjV73ReadySuccess(){
    const elapsed=jjV73ReadyStartedAt?performance.now()-jjV73ReadyStartedAt:null;
    jjV73ReadyStartedAt=0;
    // Timing is useful only for the same-page seat -> READY flow. A READY
    // success without a local start marker is still counted without duration.
    jjV6Emit('ready','submit',elapsed!=null&&elapsed>=0&&elapsed<=600000?elapsed:null);
  }
  function jjV73ActionFailed(){jjV6Emit('action_result','failed')}
  function jjV73Review(kind){jjV6Emit('review',kind)}
  function jjV73FreshState(){
    if(!jjV6Telemetry.awaitingFresh)return;
    jjV6Telemetry.awaitingFresh=false;
    jjV6Emit('reconnect','fresh_state');
  }
  document.addEventListener('click',e=>{
    if(!e.isTrusted)return;
    const join=e.target.closest?.('[data-jj-join],#jjJoinTableBtn,[data-seat]');
    if(join)jjV73ReadyStart();
  },true);

'''


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"UX telemetry followup drift at {label}: expected 1 source block, found {count}")
    return source.replace(old, new, 1)


def transform_app_js(source: str) -> str:
    if MARKER in source:
        return source
    if "const jjV6Telemetry=" not in source or "function jjV6Emit(" not in source:
        raise RuntimeError("UX telemetry followup requires the phase4c telemetry client")
    if source.count(_ANCHOR) != 1:
        raise RuntimeError("UX telemetry followup anchor missing")

    source = _replace_once(
        source,
        "    jjV6Telemetry.hadDisconnect=true;jjV6Emit('fallback','ws_close');",
        "    jjV6Telemetry.hadDisconnect=true;jjV6Telemetry.awaitingFresh=true;jjV6Emit('fallback','ws_close');",
        "disconnect recovery marker",
    )
    source = _replace_once(
        source,
        """  function jjV2AcceptState(source,previous){
    jjV2MaybeTimeoutNotice(previous,tableState);
    jjV2Connection.lastStateAt=Date.now();
    jjV2SetConnection(source==='ws'?'ws':source==='poll'?'fallback':'http',true);
    jjV6SyncDecision(tableState?.legal||{});
  }
""",
        """  function jjV2AcceptState(source,previous){
    jjV2MaybeTimeoutNotice(previous,tableState);
    jjV2Connection.lastStateAt=Date.now();
    jjV2SetConnection(source==='ws'?'ws':source==='poll'?'fallback':'http',true);
    jjV6SyncDecision(tableState?.legal||{});
    jjV73FreshState();
  }
""",
        "fresh-state recovery",
    )
    source = _replace_once(
        source,
        """    }catch(err){
      toast(err.message);
      if(currentTableId===tableId){""",
        """    }catch(err){
      jjV73ActionFailed();
      toast(err.message);
      if(currentTableId===tableId){""",
        "betting rejection",
    )
    source = _replace_once(
        source,
        "try{await post(`/tables/${currentTableId}/start`);toast('開始準備を完了しました')}",
        "try{await post(`/tables/${currentTableId}/start`);jjV73ReadySuccess();toast('開始準備を完了しました')}",
        "ready success",
    )
    source = _replace_once(
        source,
        "try{await jjOpenHand(review.dataset.jjReviewHand)}catch(err){toast(err.message)}",
        "try{await jjOpenHand(review.dataset.jjReviewHand);jjV73Review('table_open')}catch(err){toast(err.message)}",
        "table review open",
    )
    source = _replace_once(
        source,
        "try{await jjV3BookmarkHand(bookmark.dataset.jjBookmarkHand);bookmark.textContent='保存済み'}",
        "try{await jjV3BookmarkHand(bookmark.dataset.jjBookmarkHand);jjV73Review('bookmark');bookmark.textContent='保存済み'}",
        "review bookmark",
    )
    return source.replace(_ANCHOR, _HELPERS + "\n" + _ANCHOR, 1)


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
        if index.count(base) != 1:
            raise RuntimeError("UX telemetry followup app.js asset URL not found exactly once")
        start = index.index(base)
        end = index.find('"', start)
        if end < 0:
            raise RuntimeError("UX telemetry followup app.js URL terminator missing")
        current = index[start:end]
        separator = "&" if "?" in current else "?"
        index = index[:start] + current + separator + CACHE_QUERY + index[end:]
    index_path.write_text(index, encoding="utf-8", newline="\n")

    outputs = dict(manifest.get("outputs") or {})
    outputs["static/app.js"] = _digest(app_js)
    outputs["index.html"] = _digest(index)
    manifest["outputs"] = outputs
    post = dict(manifest.get("post_transforms") or {})
    post["ux_telemetry_followup"] = MARKER
    manifest["post_transforms"] = post
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


__all__ = ["CACHE_QUERY", "MARKER", "apply_to_build", "transform_app_js"]
