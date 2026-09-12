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
        "? '<div><b>TABLE FULL</b><span>空席ができるまで観戦できます</span></div><button class=\"ghost\" disabled>満席</button>'\n      : '<div><b>JOIN TABLE</b><span>150bb · プレイマネー</span></div><button class=\"primary\" id=\"jjJoinTableBtn\">着席してプレイ</button>';",
        "? '<div><b>満席</b><span>空席ができるまで観戦できます</span></div><button class=\"ghost\" disabled>満席</button>'\n      : '<div><b>テーブルに参加</b><span>持ち点150bbで着席します</span></div><button class=\"primary\" id=\"jjJoinTableBtn\">150bbで着席</button>';",
        "observer join card",
    )

    return source.rstrip() + f"\n// {CLEAR_COPY_MARKER}\n"


CLEAR_COPY_CSS = r'''

/* v2 clear poker copy 2026-09-13
   Focus mode only changes the desktop shell, so do not show a no-op control on
   phones. The desktop label states the actual visible effect instead. */
@media(max-width:760px){
  #pokerRoom #jjFocusModeToggle{display:none!important}
}
'''


def transform_styles(source: str) -> str:
    if CLEAR_COPY_MARKER in source:
        return source
    return source.rstrip() + CLEAR_COPY_CSS + "\n"


__all__ = ["CLEAR_COPY_MARKER", "transform_app_js", "transform_styles"]
