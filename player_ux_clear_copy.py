from __future__ import annotations

"""Replace ambiguous poker-table copy with explicit player-facing language.

This transform runs after the existing player UX phases. It intentionally
changes presentation only: no table state, betting rule, settlement, or
participation behavior is modified.
"""

CLEAR_COPY_MARKER = "v2 clear poker copy 2026-09-13"


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(
            f"clear poker copy drift at {label}: expected 1 source block, found {count}"
        )
    return source.replace(old, new, 1)


def transform_app_js(source: str) -> str:
    if CLEAR_COPY_MARKER in source:
        return source

    source = _replace_once(
        source,
        "if(btn){btn.textContent=enabled?'通常表示':'集中表示';btn.setAttribute('aria-pressed',enabled?'true':'false')}",
        "if(btn){btn.textContent=enabled?'元の表示に戻す':'卓を広く表示';btn.setAttribute('aria-pressed',enabled?'true':'false')}",
        "focus-mode button state",
    )
    source = _replace_once(
        source,
        "if(head&&!$('#jjPokerSettings',head))head.insertAdjacentHTML('beforeend','<button type=\"button\" class=\"ghost jj-v4-settings\" id=\"jjPokerSettings\" data-jj-sizing-settings aria-label=\"ポーカー設定\">⚙ 設定</button>');",
        "if(head&&!$('#jjPokerSettings',head))head.insertAdjacentHTML('beforeend','<button type=\"button\" class=\"ghost jj-v4-settings\" id=\"jjPokerSettings\" data-jj-sizing-settings aria-label=\"テーブル設定\">⚙ テーブル設定</button>');",
        "table settings label",
    )
    source = _replace_once(
        source,
        "if(head&&!$('#jjFocusModeToggle',head))head.insertAdjacentHTML('beforeend','<button type=\"button\" class=\"ghost jj-focus-toggle\" id=\"jjFocusModeToggle\" aria-pressed=\"false\">集中表示</button>');",
        "if(head&&!$('#jjFocusModeToggle',head))head.insertAdjacentHTML('beforeend','<button type=\"button\" class=\"ghost jj-focus-toggle\" id=\"jjFocusModeToggle\" aria-pressed=\"false\" aria-label=\"メニューを隠してポーカーテーブルを広く表示\">卓を広く表示</button>');",
        "focus-mode initial label",
    )
    source = _replace_once(
        source,
        "if(head&&!$('#jjV4MobileTools',head))head.insertAdjacentHTML('beforeend','<div id=\"jjV4MobileTools\" class=\"jj-v4-mobile-tools\" aria-label=\"テーブル情報\"><button type=\"button\" class=\"ghost\" data-jj-mobile-side=\"log\">履歴</button><button type=\"button\" class=\"ghost\" data-jj-mobile-side=\"chat\">チャット</button></div>');",
        "if(head&&!$('#jjV4MobileTools',head))head.insertAdjacentHTML('beforeend','<div id=\"jjV4MobileTools\" class=\"jj-v4-mobile-tools\" aria-label=\"テーブル情報\"><button type=\"button\" class=\"ghost\" data-jj-mobile-side=\"log\">ハンド履歴</button><button type=\"button\" class=\"ghost\" data-jj-mobile-side=\"chat\">チャット</button></div>');",
        "mobile history label",
    )
    source = _replace_once(
        source,
        "roomMeta.textContent=hero?`${bb(hero.stack)} · ${active}/6`:`観戦 · ${active}/6`;",
        "roomMeta.textContent=hero?`持ち点 ${bb(hero.stack)} · 着席人数 ${active}/6`:`観戦中 · 着席人数 ${active}/6`;",
        "mobile table status",
    )
    source = _replace_once(
        source,
        "el.innerHTML='<b>開始準備</b><span>全員が準備OKで開始</span>';",
        "el.innerHTML='<b>開始待ち</b><span>着席者全員が「準備OK」を押すと開始します</span>';",
        "waiting-to-start status",
    )
    source = _replace_once(
        source,
        "? '<div><b>TABLE FULL</b><span>空席ができるまで観戦できます</span></div><button class=\"ghost\" disabled>満席</button>'\n      : '<div><b>JOIN TABLE</b><span>150bb · プレイマネー</span></div><button class=\"primary\" id=\"jjJoinTableBtn\">150bbで着席</button>';",
        "? '<div><b>満席</b><span>空席ができるまで観戦できます</span></div><button class=\"ghost\" disabled>満席</button>'\n      : '<div><b>テーブルに参加</b><span>持ち点150bbで着席します</span></div><button class=\"primary\" id=\"jjJoinTableBtn\">150bbで着席</button>';",
        "observer join card",
    )

    # On phones the sound toggle previously remained as a fourth presence
    # control below the felt. Move the existing control into the table header so
    # the bottom action row can devote its full width to READY / sit-out / leave.
    source = _replace_once(
        source,
        "if(JJ_V124_DESKTOP_MQ.matches&&sound&&head&&!head.contains(sound))head.appendChild(sound);",
        "if(sound&&head&&!head.contains(sound)&&(JJ_V124_DESKTOP_MQ.matches||window.innerWidth<=760))head.appendChild(sound);",
        "mobile sound placement",
    )

    # Portrait seat coordinates are deliberately balanced around the *visible*
    # felt rather than the viewport. Lifting the hero and lower seats prevents
    # the 6-o'clock seat from competing with the persistent presence controls.
    source = _replace_once(
        source,
        """    const coords=[
      {left:50,top:82},
      {left:13,top:64},
      {left:18,top:31},
      {left:50,top:15},
      {left:82,top:31},
      {left:87,top:64},
    ];
""",
        """    const coords=[
      {left:50,top:79},
      {left:14,top:61},
      {left:17,top:30},
      {left:50,top:14},
      {left:83,top:30},
      {left:86,top:61},
    ];
""",
        "portrait seat coordinates",
    )

    return source.rstrip() + f"\n// {CLEAR_COPY_MARKER}\n"


CLEAR_COPY_CSS = r'''

/* v2 clear poker copy 2026-09-13
   Focus mode only changes the desktop shell, so do not show a no-op control on
   phones. The desktop label states the actual visible effect instead. */
@media(max-width:760px){
  #pokerRoom #jjFocusModeToggle{display:none!important}

  /* v2 mobile poker coordinate repair 2026-09-13
     The header now has two explicit rows. The second row is normal layout, not
     an overlay on the felt, so longer Japanese labels cannot cover the table. */
  body.jj-mobile-table-open #pokerRoom .room-head{
    display:grid!important;
    grid-template-columns:auto minmax(0,1fr) auto!important;
    grid-template-rows:44px 44px!important;
    align-items:center!important;
    column-gap:8px!important;
    row-gap:7px!important;
    flex:0 0 calc(103px + env(safe-area-inset-top))!important;
    height:calc(103px + env(safe-area-inset-top))!important;
    min-height:calc(103px + env(safe-area-inset-top))!important;
    margin:0!important;
    padding:env(safe-area-inset-top) 10px 8px!important;
    position:relative!important;
    top:auto!important;
    background:rgba(7,16,13,.985)!important;
    border-bottom:1px solid rgba(255,255,255,.08)!important;
    z-index:110!important;
  }
  body.jj-mobile-table-open #backLobby{
    grid-column:1!important;grid-row:1!important;
    min-width:84px!important;width:auto!important;height:42px!important;min-height:42px!important;
    padding:0 10px!important;white-space:nowrap!important;
  }
  body.jj-mobile-table-open #pokerRoom .room-head>div:nth-child(2){
    grid-column:2!important;grid-row:1!important;min-width:0!important;
  }
  body.jj-mobile-table-open #roomTitle{
    margin:0!important;font-size:.9rem!important;line-height:1.15!important;
    white-space:nowrap!important;overflow:hidden!important;text-overflow:ellipsis!important;
  }
  body.jj-mobile-table-open #roomMeta{
    grid-column:3!important;grid-row:1!important;
    min-width:0!important;margin:0!important;text-align:right!important;
    font-size:.61rem!important;line-height:1.25!important;white-space:nowrap!important;
  }
  body.jj-mobile-table-open #jjPokerSettings{
    grid-column:1!important;grid-row:2!important;
    width:100%!important;min-width:0!important;height:42px!important;min-height:42px!important;
    padding:0 8px!important;font-size:.65rem!important;white-space:nowrap!important;
  }
  body.jj-mobile-table-open #jjV4MobileTools{
    grid-column:2!important;grid-row:2!important;
    display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;
    width:100%!important;min-width:0!important;gap:6px!important;margin:0!important;
  }
  body.jj-mobile-table-open #jjV4MobileTools button{
    width:100%!important;min-width:0!important;height:42px!important;min-height:42px!important;
    padding:0 5px!important;font-size:.62rem!important;white-space:nowrap!important;
  }
  body.jj-mobile-table-open #jjSoundToggle{
    grid-column:3!important;grid-row:2!important;
    justify-self:end!important;width:58px!important;min-width:58px!important;
    height:42px!important;min-height:42px!important;padding:0 5px!important;
    font-size:.62rem!important;border-radius:10px!important;
  }

  /* A healthy connection is not actionable information and must not occupy the
     bottom thumb zone. Connection problems remain prominent near the table top. */
  body.jj-mobile-table-open .jj-connection-status:not(.is-degraded){display:none!important}
  body.jj-mobile-table-open .jj-connection-status.is-degraded{
    display:block!important;position:fixed!important;z-index:180!important;
    left:50%!important;right:auto!important;top:calc(env(safe-area-inset-top) + 108px)!important;bottom:auto!important;
    transform:translateX(-50%)!important;width:min(360px,calc(100% - 24px))!important;
    margin:0!important;padding:7px 10px!important;font-size:.64rem!important;line-height:1.3!important;
  }

  /* Presence controls form a deliberate three-column information hierarchy:
     READY on the left, temporary/permanent departure actions on the right.
     The sound control has moved to the header and no longer causes overflow. */
  body.jj-mobile-table-open #tableControls{
    display:grid!important;
    grid-template-columns:minmax(108px,.9fr) minmax(0,1.6fr)!important;
    align-items:center!important;gap:6px!important;
    width:100%!important;height:54px!important;min-height:54px!important;
    margin:0!important;padding:5px 7px!important;overflow:hidden!important;
    background:#09120f!important;border-top:1px solid rgba(255,255,255,.06)!important;
  }
  body.jj-mobile-table-open #tableControls .jj-table-control-left,
  body.jj-mobile-table-open #tableControls .jj-table-control-right{
    display:grid!important;align-items:center!important;gap:6px!important;
    min-width:0!important;width:100%!important;flex:none!important;margin:0!important;
  }
  body.jj-mobile-table-open #tableControls .jj-table-control-left{grid-template-columns:minmax(0,1fr)!important}
  body.jj-mobile-table-open #tableControls .jj-table-control-right{grid-template-columns:repeat(2,minmax(0,1fr))!important}
  body.jj-mobile-table-open #tableControls .jj-table-control-right>button:only-child{grid-column:1/-1!important}
  body.jj-mobile-table-open #tableControls .jj-table-control-left:not(:has(button)){
    display:none!important;
  }
  body.jj-mobile-table-open #tableControls:has(.jj-table-control-left:not(:has(button))){
    grid-template-columns:minmax(0,1fr)!important;
  }
  body.jj-mobile-table-open #tableControls button{
    width:100%!important;min-width:0!important;max-width:none!important;
    height:44px!important;min-height:44px!important;max-height:44px!important;
    padding:0 6px!important;border-radius:10px!important;
    font-size:.62rem!important;line-height:1.15!important;white-space:normal!important;
    overflow:hidden!important;text-overflow:ellipsis!important;
  }
  body.jj-mobile-table-open #tableControls .jj-ready-count{display:none!important}
  body.jj-mobile-table-open #tableControls .jj-leave-reservation{font-size:.58rem!important;line-height:1.15!important}
}

@media(max-width:760px) and (orientation:portrait){
  /* The old 46px header assumption made the new second row overlap the felt.
     All stage heights now reserve the real 103px two-row header. */
  body.jj-mobile-table-open #pokerTable{
    height:calc(100dvh - 103px - env(safe-area-inset-top) - 108px)!important;
    min-height:430px!important;
  }
  body.jj-mobile-table-open.jj-mobile-poker-hand #pokerTable{
    height:calc(100dvh - 103px - env(safe-area-inset-top) - 184px)!important;
    min-height:390px!important;
  }
  body.jj-mobile-table-open.jj-mobile-poker-observer #pokerTable{
    height:calc(100dvh - 103px - env(safe-area-inset-top))!important;
    min-height:445px!important;
  }
  body.jj-mobile-table-open #pokerTable .felt-center{top:40%!important}
}

@media(max-width:380px){
  body.jj-mobile-table-open #pokerRoom .room-head{
    grid-template-columns:78px minmax(0,1fr) auto!important;
    column-gap:6px!important;padding-left:7px!important;padding-right:7px!important;
  }
  body.jj-mobile-table-open #backLobby{min-width:78px!important;padding-inline:7px!important;font-size:.65rem!important}
  body.jj-mobile-table-open #roomMeta{font-size:.56rem!important}
  body.jj-mobile-table-open #jjPokerSettings,
  body.jj-mobile-table-open #jjV4MobileTools button,
  body.jj-mobile-table-open #jjSoundToggle{font-size:.58rem!important}
}
'''


def transform_styles(source: str) -> str:
    if CLEAR_COPY_MARKER in source:
        return source
    return source.rstrip() + CLEAR_COPY_CSS + "\n"


__all__ = ["CLEAR_COPY_MARKER", "transform_app_js", "transform_styles"]
