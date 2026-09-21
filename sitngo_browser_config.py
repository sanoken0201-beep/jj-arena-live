"""Dependency-free browser contracts layered onto the canonical Sit&Go UI.

`sitngo_ui.py` now contains the current 12-hand lobby/table presentation
directly. This module owns only cross-cutting browser contracts that must be
installed before the production asset compiler binds Sit&Go transforms:
tournament chip-unit behavior, action identity payloads, and the dedicated
cache token. Historical timed-level copy is not used as a transform anchor.
"""
from __future__ import annotations

CACHE_QUERY = "sngcfg=legacy-source-cleanup-20260921-1"
CHIP_UI_MARKER = "jj sitngo chip unit ui 2026-09-18"
HAND_LEVEL_UI_MARKER = "jj sng 12-hand levels 2026-09-18"
TURN_UI_MARKER = "jj sng turn safety 2026-09-18"


def install() -> None:
    import sitngo_ui as ui

    # Keep these compatibility flags for runtime delegates that still call this
    # installer. The actual 12-hand presentation is canonical in sitngo_ui.
    ui._JJ_ADMIN_STRUCTURE_PATCHED = True
    ui._JJ_HAND_LEVELS_BUILD_PATCHED = True

    if CHIP_UI_MARKER not in ui._APP_PATCH:
        source = ui._APP_PATCH
        source += r'''

  // jj sitngo chip unit ui 2026-09-18
  const jjSngBaseTableClock=jjSngTableClock;
  jjSngTableClock=function(){
    jjSngBaseTableClock();
    if(!tableState?.tournament)return;
    const el=$('#jjSngTableInfo'),first=el?.querySelector('span');
    const unit=Math.max(100,Number(tableState.chip_unit||tableState.tournament?.chip_unit||100));
    if(first&&!first.textContent.includes('最小 '))first.textContent+=` · 最小 ${fmt(unit)}`;
  };

  const jjSngBaseTotalPot=jjTotalPot;
  jjTotalPot=function(){
    const base=jjSngBaseTotalPot();
    return base+(tableState?.tournament?Number(tableState.tournament.ante_paid||0):0);
  };
  totalPot=jjTotalPot;

  function jjSngSnapRaiseBb(value){
    if(!tableState?.tournament)return Number(value||0);
    const big=Math.max(1,Number(tableState.big_blind||100));
    const unit=Math.max(100,Number(tableState.chip_unit||tableState.tournament?.chip_unit||100));
    const legal=tableState.legal||{};
    const min=Number(legal.min_raise_to||0),max=Number(legal.max_raise_to||0);
    let chips=Math.round((Number(value||0)*big)/unit)*unit;
    if(min)chips=Math.max(min,chips);
    if(max)chips=Math.min(max,chips);
    return chips/big;
  }

  const jjSngBaseSetRaiseBb=jjSetRaiseBb;
  jjSetRaiseBb=function(value){return jjSngBaseSetRaiseBb(tableState?.tournament?jjSngSnapRaiseBb(value):value)};

  const jjSngBaseDoAction=doAction;
  doAction=async function(action){
    if(action==='raise'&&tableState?.tournament){
      const input=$('#raiseTo');
      if(input&&typeof jjV124CeilRaiseBb==='function')input.value=jjV124CeilRaiseBb(input.value);
    }
    return jjSngBaseDoAction(action);
  };

  const jjSngBaseActionBar=renderActionBar;
  renderActionBar=function(){
    jjSngBaseActionBar();
    if(!tableState?.tournament)return;
    const big=Math.max(1,Number(tableState.big_blind||100));
    const unit=Math.max(100,Number(tableState.chip_unit||tableState.tournament?.chip_unit||100));
    const step=unit/big;
    const input=$('#raiseTo'),slider=$('#raiseSlider');
    if(input){
      input.step=String(step);
      const exact=jjSngSnapRaiseBb(input.value);
      input.value=String(typeof jjV124CeilRaiseBb==='function'?jjV124CeilRaiseBb(exact):exact);
    }
    if(slider){slider.step=String(step);slider.value=String(jjSngSnapRaiseBb(slider.value))}
  };

  const jjSngChipRoom=renderPokerRoom;
  renderPokerRoom=function(){
    jjSngChipRoom();
    if(!tableState?.tournament)return;
    const unit=Math.max(100,Number(tableState.chip_unit||tableState.tournament?.chip_unit||100));
    const meta=$('#roomMeta');if(meta)meta.textContent=`Sit&Go · Freezeout · ${fmt(unit)}点単位`;
  };
'''
        ui._APP_PATCH = source

    if not getattr(ui, "_JJ_TURN_PAYLOAD_PATCHED", False):
        original_transform_app_js = ui.transform_app_js

        def transform_app_js(source: str) -> str:
            output = original_transform_app_js(source)
            if TURN_UI_MARKER in output:
                return output
            needle = "const body={action};if(action==='raise')"
            replacement = (
                "const body={action};/* " + TURN_UI_MARKER + " */"
                "if(tableState?.tournament){"
                "body.action_id=(globalThis.crypto?.randomUUID?.()||`sng-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`);"
                "body.hand_id=tableState.hand?.id||null;"
                "body.turn_id=tableState.turn_id||tableState.hand?.turn_id||null}"
                "if(action==='raise')"
            )
            if output.count(needle) != 1:
                raise RuntimeError("Sit&Go turn payload drift: action body anchor changed")
            return output.replace(needle, replacement, 1)

        ui.transform_app_js = transform_app_js
        ui._JJ_TURN_PAYLOAD_PATCHED = True

    if not getattr(ui, "_JJ_SNG_CACHE_PATCHED", False):
        original_transform_index = ui.transform_index

        def transform_index(source: str) -> str:
            output = original_transform_index(source)
            if CACHE_QUERY in output:
                return output
            marker = "/static/app.js?v="
            if output.count(marker) != 1:
                raise RuntimeError("Sit&Go cache contract drift: app.js URL not found exactly once")
            start = output.index(marker)
            end = output.find('"', start)
            if end < 0:
                raise RuntimeError("Sit&Go cache contract drift: app.js URL terminator missing")
            current = output[start:end]
            separator = "&" if "?" in current else "?"
            return output[:start] + current + separator + CACHE_QUERY + output[end:]

        ui.transform_index = transform_index
        ui._JJ_SNG_CACHE_PATCHED = True


__all__ = ["CACHE_QUERY", "CHIP_UI_MARKER", "HAND_LEVEL_UI_MARKER", "TURN_UI_MARKER", "install"]
