from __future__ import annotations

"""Final production-asset fix for WebSocket/HTTP action freshness handoff.

The immutable materialized poker core already returns correct legal actions for
OOP checks. The bug was client-side: a successful HTTP snapshot was marked
stale again when the WebSocket merely opened, disabling every action until the
first WS state frame arrived. If that frame was delayed, the UI could say
"あなたの番です" while CHECK/BET were disabled.

This post-transform preserves an already-authoritative HTTP snapshot across the
WS handshake and starts a short authoritative HTTP resync watchdog. A genuine
disconnect still sets freshness false, so stale-state protection remains
fail-closed. No poker rule or settlement behavior changes here.
"""

import hashlib
import json
from pathlib import Path

MARKER = "v71 websocket action freshness 2026-09-15"
CACHE_QUERY = "cf=oop-check-freshness-20260915-1"

_HELPERS = r'''
  // v71 websocket action freshness 2026-09-15
  let jjV71WsSyncGeneration=0;
  function jjV71SocketOpen(id){
    const generation=++jjV71WsSyncGeneration;
    const baselineState=tableState,baselineAt=Number(jjV2Connection.lastStateAt||0);
    // Opening the socket is not evidence that the last accepted HTTP state is
    // stale. Preserve it for the brief WS handoff; reconnects are still stale
    // because onclose already set fresh=false.
    const preserveFresh=!!tableState&&!!jjV2Connection.fresh;
    jjV2SetConnection('syncing',preserveFresh);
    window.setTimeout(async()=>{
      if(generation!==jjV71WsSyncGeneration||currentTableId!==id)return;
      const acceptedAfterOpen=!!jjV2Connection.fresh&&(
        tableState!==baselineState||Number(jjV2Connection.lastStateAt||0)!==baselineAt
      );
      if(acceptedAfterOpen)return;
      const before=tableState;
      try{
        const latest=await api('/tables/'+id);
        if(generation!==jjV71WsSyncGeneration||currentTableId!==id)return;
        // Never overwrite a newer WS/poll snapshot that arrived while the HTTP
        // confirmation was in flight.
        const newerAccepted=!!jjV2Connection.fresh&&(
          tableState!==before||Number(jjV2Connection.lastStateAt||0)!==baselineAt
        );
        if(newerAccepted)return;
        tableState=latest.state;
        if(Array.isArray(latest.messages))tableMessages=latest.messages;
        jjV2AcceptState('poll',before);
        renderPokerRoom();
      }catch{
        // If neither WS nor HTTP can confirm current state, fail closed instead
        // of leaving apparently legal controls clickable indefinitely.
        if(generation===jjV71WsSyncGeneration&&currentTableId===id&&
           tableState===before&&Number(jjV2Connection.lastStateAt||0)===baselineAt){
          jjV2SetConnection('syncing',false);
          renderPokerRoom();
        }
      }
    },700);
  }
'''

_ONOPEN_OLD = """      jjV2SetConnection('syncing',false);\n      tableHeartbeat=setInterval(()=>{if(tableWS?.readyState===WebSocket.OPEN)tableWS.send('ping')},15000);"""
_ONOPEN_NEW = """      jjV71SocketOpen(id);\n      tableHeartbeat=setInterval(()=>{if(tableWS?.readyState===WebSocket.OPEN)tableWS.send('ping')},15000);"""
_ANCHOR = "  // Desktop bet markers use explicit poker-table lanes rather than the old\n"


def transform_app_js(source: str) -> str:
    if MARKER in source:
        return source
    if source.count(_ONOPEN_OLD) != 1:
        raise RuntimeError("OOP check freshness drift: WebSocket onopen block not found exactly once")
    if source.count(_ANCHOR) != 1:
        raise RuntimeError("OOP check freshness drift: helper anchor not found exactly once")
    source = source.replace(_ONOPEN_OLD, _ONOPEN_NEW, 1)
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
            raise RuntimeError("OOP check freshness drift: app.js asset URL not found exactly once")
        index = index.replace(base, f"{base}&{CACHE_QUERY}", 1)
    index_path.write_text(index, encoding="utf-8", newline="\n")

    outputs = dict(manifest.get("outputs") or {})
    outputs["static/app.js"] = _digest(app_js)
    outputs["index.html"] = _digest(index)
    manifest["outputs"] = outputs
    post = dict(manifest.get("post_transforms") or {})
    post["oop_check_freshness"] = MARKER
    manifest["post_transforms"] = post
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest


__all__ = ["CACHE_QUERY", "MARKER", "apply_to_build", "transform_app_js"]
