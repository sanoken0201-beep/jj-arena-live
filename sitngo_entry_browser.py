"""Dependency-free player UI transform for Sit&Go late registration/re-entry."""
from __future__ import annotations

MARKER = "jj sitngo late registration reentry ui 2026-09-18"


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise RuntimeError(f"Sit&Go entry UI drift: {label}")
    return source.replace(old, new, 1)


def install() -> None:
    import sitngo_ui as ui

    if getattr(ui, "_JJ_ENTRY_BROWSER_PATCHED", False):
        return
    source = ui._APP_PATCH
    source = _replace_once(
        source,
        "    if(status==='running'||status==='finished')action=event.table_id?`<button type=\"button\" class=\"primary jj-sng-register\" data-sng-open=\"${safe(event.table_id)}\">${status==='finished'?'結果を見る':registered?'大会テーブルへ':'観戦する'}</button>`:'<div class=\"jj-sng-note\">テーブル準備中</div>';\n",
        "    if(status==='running'&&event.entry_pending)action='<button type=\"button\" class=\"soft jj-sng-register\" disabled>次のハンドから参加</button>';\n"
        "    else if(status==='running'&&event.can_reenter)action=`<button type=\"button\" class=\"primary jj-sng-register\" data-sng-reentry=\"${safe(event.id)}\">リエントリーする</button>`;\n"
        "    else if(status==='running'&&event.can_late_register)action=`<button type=\"button\" class=\"primary jj-sng-register\" data-sng-register=\"${safe(event.id)}\">途中参加する</button>`;\n"
        "    else if(status==='running'||status==='finished')action=event.table_id?`<button type=\"button\" class=\"primary jj-sng-register\" data-sng-open=\"${safe(event.table_id)}\">${status==='finished'?'結果を見る':registered?'大会テーブルへ':'観戦する'}</button>`:'<div class=\"jj-sng-note\">テーブル準備中</div>';\n",
        "running entry actions",
    )
    source = _replace_once(
        source,
        "<div class=\"jj-sng-rules\"><span>6-max</span><span>${fmt(event.starting_stack)}点</span><span>${jjSngLevelSummary(eventLevels)}</span><span>BB Ante</span><span>無料 · 賞品なし</span><span>再参加なし</span></div>",
        "<div class=\"jj-sng-rules\"><span>6-max</span><span>${fmt(event.starting_stack)}点</span><span>${jjSngLevelSummary(eventLevels)}</span><span>BB Ante</span><span>無料 · 賞品なし</span><span>${Number(event.late_registration_minutes||0)>0?`開始後${Number(event.late_registration_minutes)}分まで受付`:'定刻締切'}</span><span>${Number(event.max_reentries||0)>0?`リエントリー最大${Number(event.max_reentries)}回`:'リエントリーなし'}</span></div>",
        "entry policy badges",
    )
    source = _replace_once(
        source,
        "<p class=\"hint\">受付は当日の開始1時間前から先着順。定刻になれば2〜6人で開始し、1人以下の場合は自動中止します。席は抽選で決定します。通信切断中もブラインドは発生します。</p>",
        "<p class=\"hint\">受付は当日の開始1時間前から先着順。${Number(event.late_registration_minutes||0)>0?`開始後${Number(event.late_registration_minutes)}分までは空き枠への途中参加が可能です。`:'定刻で受付を締め切ります。'}${Number(event.max_reentries||0)>0?`敗退後は受付時間内に最大${Number(event.max_reentries)}回リエントリーできます。`:''}途中参加・リエントリーはハンド中には着席せず、次ハンドから反映します。ブラインド時計は継続します。</p>",
        "entry policy help",
    )
    source += r'''

  // jj sitngo late registration reentry ui 2026-09-18
  document.addEventListener('click',async e=>{
    const button=e.target.closest('[data-sng-reentry]');if(!button)return;
    e.preventDefault();button.disabled=true;
    try{
      await post(`/sitngo/${button.dataset.sngReentry}/reentry`,{});
      toast('リエントリーを受け付けました。次のハンドから参加します');
      await renderSitNGo();
    }catch(err){toast(err.message);button.disabled=false}
  });
'''
    ui._APP_PATCH = source
    ui._JJ_ENTRY_BROWSER_PATCHED = True


__all__ = ["MARKER", "install"]
