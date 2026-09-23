from __future__ import annotations

from served_assets import ASSET_VERSION, build_app_js, build_index, build_styles
from subtractive_redesign import SUBTRACTIVE_RED282_MARKER


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    html = build_index()
    js = build_app_js()
    css = build_styles()

    require(ASSET_VERSION == 73, "asset version must be bumped for the aggregate-read UI")
    require(SUBTRACTIVE_RED282_MARKER in html, "index marker missing")
    require(SUBTRACTIVE_RED282_MARKER in js, "app marker missing")
    require(SUBTRACTIVE_RED282_MARKER in css, "style marker missing")

    require('data-view="schedule"' not in html, "schedule must leave primary navigation")
    require('data-view="discussion"' not in html, "discussion must leave primary navigation")
    require("1 TABLE · 6-MAX · 150BB" in html, "single-table lobby copy missing")
    require("6-max固定・0.5/1bb・1卓。" in html, "Home table copy must reflect one public table")
    require("お知らせ / 活動予定" in html, "announcement/calendar merged heading missing")
    require("rake 10%・5bb cap" not in html, "lobby rake explanation should not be displayed")

    require("const raw=await api('/tables')" in js, "single-table lobby renderer missing")
    require("tables[0]" in js, "single public table selection missing")
    require("bar.querySelector('.jj-size-row')?.remove()" in js, "bet preset removal missing")
    require("bar.querySelector('#raiseSlider')?.remove()" in js, "bet slider removal missing")
    require("input.step='0.01'" in js, "manual numeric bet input precision missing")
    require("renderTableChat=function(){}" in js, "in-hand chat renderer must be disabled")
    require("renderHandLog=function(){}" in js, "in-hand action log renderer must be disabled")
    require("jjSubBaseRenderPokerRoom" in js, "poker-room metadata cleanup missing")
    require("jjSubBaseRenderNews" in js, "announcement/calendar compatibility merge missing")
    require("お知らせ / 活動予定を投稿" in js, "announcement form copy must cover activity dates")

    require("#pokerRoom .table-side{display:none!important}" in css, "chat/log side panel must be hidden")
    require("#tablesView .online-overview{display:none!important}" in css, "lobby ledger/rake panels must be hidden")
    require("#scheduleView{display:none!important}" in css, "standalone calendar view must be hidden")

    print("subtractive redesign smoke test: PASS")


if __name__ == "__main__":
    main()
