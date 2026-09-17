"""Dependency-free browser transforms for configurable Sit&Go tournaments.

This module intentionally imports only ``sitngo_ui`` so the production asset
compiler remains usable in lightweight CI jobs that do not install FastAPI.
"""
from __future__ import annotations

CACHE_QUERY = "sngcfg=12-hand-levels-20260918-1"
CHIP_UI_MARKER = "jj sitngo chip unit ui 2026-09-18"
HAND_LEVEL_UI_MARKER = "jj sng 12-hand levels 2026-09-18"


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise RuntimeError(f"Sit&Go configurable UI drift: {label}")
    return source.replace(old, new, 1)


def _replace_prefixed_line(source: str, prefix: str, replacement: str, label: str) -> str:
    lines = source.splitlines(keepends=True)
    matches = [i for i, line in enumerate(lines) if line.startswith(prefix)]
    if len(matches) != 1:
        raise RuntimeError(f"Sit&Go configurable UI drift: {label}")
    newline = "\n" if lines[matches[0]].endswith("\n") else ""
    lines[matches[0]] = replacement.rstrip("\n") + newline
    return "".join(lines)


def install() -> None:
    import sitngo_ui as ui

    if not getattr(ui, "_JJ_ADMIN_STRUCTURE_PATCHED", False):
        ui._SITNGO_PANEL = _replace_once(
            ui._SITNGO_PANEL,
            "6-MAX · 10 MIN LEVELS · BB ANTE",
            "6-MAX · ADMIN STRUCTURE · BB ANTE",
            "panel rule copy",
        )
        source = ui._APP_PATCH
        old_function = """  function jjSngStructureHtml(levels){return `<details class=\"jj-sng-structure\"><summary>ブラインドストラクチャーを見る</summary><div class=\"jj-sng-levels\">${(levels||[]).map(x=>`<div class=\"jj-sng-level ${Number(x.level)===9?'target':''}\"><span>Lv.${x.level}</span><b>${fmt(x.small_blind)} / ${fmt(x.big_blind)}</b><small>BBA ${fmt(x.bb_ante)} · ${x.minutes}分${Number(x.level)===9?' · 90分':''}</small></div>`).join('')}</div></details>`}\n"""
        new_function = """  const jjSngLevelSummary=levels=>{const values=[...new Set((levels||[]).map(x=>Number(x.minutes)||0).filter(Boolean))];return values.length===1?`${values[0]}分レベル`:'可変レベル'};\n  function jjSngStructureHtml(levels,targetMinutes){let elapsed=0;return `<details class=\"jj-sng-structure\"><summary>ブラインドストラクチャーを見る</summary><div class=\"jj-sng-levels\">${(levels||[]).map(x=>{const start=elapsed;elapsed+=Number(x.minutes)||0;const target=Number(targetMinutes||0),hit=target>0&&start<target&&elapsed>=target;return `<div class=\"jj-sng-level ${hit?'target':''}\"><span>Lv.${x.level}</span><b>${fmt(x.small_blind)} / ${fmt(x.big_blind)}</b><small>BBA ${fmt(x.bb_ante)} · ${x.minutes}分 · ${start}–${elapsed}分${hit?` · ${target}分目標`:''}</small></div>`}).join('')}</div></details>`}\n"""
        source = _replace_once(source, old_function, new_function, "structure renderer")
        source = _replace_once(
            source,
            "    const status=event.status||'scheduled',registered=!!event.is_registered,full=!!event.full;\n",
            "    const status=event.status||'scheduled',registered=!!event.is_registered,full=!!event.full,eventLevels=event.structure||levels||[];\n",
            "event structure binding",
        )
        source = _replace_once(
            source,
            "<div class=\"jj-sng-rules\"><span>6-max</span><span>10,000点</span><span>10分レベル</span><span>BB Ante</span><span>無料 · 賞品なし</span><span>再参加なし</span></div>",
            "<div class=\"jj-sng-rules\"><span>6-max</span><span>${fmt(event.starting_stack)}点</span><span>${jjSngLevelSummary(eventLevels)}</span><span>BB Ante</span><span>無料 · 賞品なし</span><span>再参加なし</span></div>",
            "event rules",
        )
        source = _replace_once(
            source,
            "${jjSngStructureHtml(levels||event.structure)}",
            "${jjSngStructureHtml(eventLevels,event.target_minutes)}",
            "event structure call",
        )
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
      if(input)input.value=jjSngSnapRaiseBb(input.value);
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
    if(input){input.step=String(step);input.value=String(jjSngSnapRaiseBb(input.value))}
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
        ui._JJ_ADMIN_STRUCTURE_PATCHED = True

    # The production browser bundle is compiled before the FastAPI runtime is
    # imported, so the 12-hand labels must be applied in this dependency-free
    # build path rather than only in the runtime integration module.
    if not getattr(ui, "_JJ_HAND_LEVELS_BUILD_PATCHED", False):
        ui._SITNGO_PANEL = ui._SITNGO_PANEL.replace(
            "6-MAX · ADMIN STRUCTURE · BB ANTE",
            "6-MAX · 12 HAND LEVELS · BB ANTE",
        ).replace(
            "6-MAX · 10 MIN LEVELS · BB ANTE",
            "6-MAX · 12 HAND LEVELS · BB ANTE",
        )

        source = ui._APP_PATCH
        source = _replace_prefixed_line(
            source,
            "  const jjSngLevelSummary=",
            "  const jjSngLevelSummary=levels=>'12ハンド/レベル';",
            "12-hand level summary",
        )
        source = _replace_prefixed_line(
            source,
            "  function jjSngStructureHtml(",
            "  function jjSngStructureHtml(levels,targetMinutes){return `<details class=\"jj-sng-structure\"><summary>ブラインドストラクチャーを見る</summary><div class=\"jj-sng-levels\">${(levels||[]).map(x=>`<div class=\"jj-sng-level\"><span>Lv.${x.level}</span><b>${fmt(x.small_blind)} / ${fmt(x.big_blind)}</b><small>BBA ${fmt(x.bb_ante)} · 12ハンド</small></div>`).join('')}</div></details>`}",
            "12-hand structure renderer",
        )
        source = source.replace(
            "jjSngStructureHtml(eventLevels,event.target_minutes)",
            "jjSngStructureHtml(eventLevels)",
        )
        source += f"\n  // {HAND_LEVEL_UI_MARKER}\n"
        ui._APP_PATCH = source

        gameplay = ui._GAMEPLAY_PATCH
        old_clock = "    el.innerHTML=`<span>Lv.${Number(t.level)} · ${fmt(tableState.small_blind)}/${fmt(tableState.big_blind)} · BBA ${fmt(t.bb_ante)}</span><span>残り${Number(t.remaining)}/${Number(t.entrants)}人${t.status==='finished'?' · 終了':t.next_level_at?` · 次 ${jjSngCountdown(t.next_level_at)}`:''}</span>`;"
        new_clock = "    el.innerHTML=`<span>Lv.${Number(t.level)} · ${fmt(tableState.small_blind)}/${fmt(tableState.big_blind)} · BBA ${fmt(t.bb_ante)}</span><span>${t.status==='finished'?'終了':`${Number(t.hand_in_level||0)}/${Number(t.hands_per_level||12)}ハンド`} · 残り${Number(t.remaining)}/${Number(t.entrants)}人</span>`;"
        gameplay = _replace_once(gameplay, old_clock, new_clock, "12-hand table clock")
        ui._GAMEPLAY_PATCH = gameplay
        ui._JJ_HAND_LEVELS_BUILD_PATCHED = True

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


__all__ = ["CACHE_QUERY", "CHIP_UI_MARKER", "HAND_LEVEL_UI_MARKER", "install"]
