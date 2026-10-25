"""The distinctive classic UI must stay accessible and out of poker gameplay."""

from __future__ import annotations

from illuminated_classic_theme import (
    ILLUMINATED_CLASSIC_CSS,
    ILLUMINATED_CLASSIC_MARKER,
    ILLUMINATED_DECK_MARKER,
    transform_index,
    transform_styles,
)
from served_assets import ASSET_VERSION, build_app_js, build_index, build_styles


def _luminance(color: str) -> float:
    channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722


def _contrast(foreground: str, background: str) -> float:
    a, b = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def main() -> None:
    assert ASSET_VERSION >= 96, "the redesign must invalidate the previous PWA cache"
    theme = ILLUMINATED_CLASSIC_CSS
    assert len(theme.encode("utf-8")) <= 16500, "CSS must stay smaller than an image asset"
    assert all(suit in theme for suit in ("♠", "♥", "♦", "♣"))
    assert all(selector in theme for selector in (
        "#homeView .hero", "#rankingView .podium-card", "#pointsView .panel", "#authView.auth-shell",
        "#appView .sidebar", "#appView .topbar", "#homeView .top-player", ".jj-analysis-hero",
        "#appView .mobile-dock", "@media(max-width:760px)",
    ))
    for forbidden in (
        ":root", "#pokerRoom", "#pokerTable", "#actionBar", "#pointForm", "#quickPointForm",
        "#mobileQuickPointCard", "#homePointShortcut", "@font-face", "@keyframes",
        "@import", "url(", "animation:", "backdrop-filter:blur(",
    ):
        assert forbidden not in theme, f"unexpected gameplay, entry structure or network styling: {forbidden}"

    assert theme.count("::before") >= 3 and theme.count("::after") >= 4
    assert "#homeView .hero {border:" in theme, "hero must change visually beyond colors"
    assert "#homeView .jj-illuminated-deck" in theme, "a drawn suit-card motif is required"
    assert "border-top:5px" in theme, "podium cards must have a rank-specific treatment"
    assert "#rankingView .table-card th" in theme, "ranking header needs a distinctive treatment"
    assert "#pointsView .primary" in theme and "#pointsView .calc" in theme
    assert "#homeView .mobile-quick-point" in theme, "mobile point input must remain visible"

    assert transform_styles(theme) == theme, "theme must be idempotent"
    compiled = build_styles()
    assert compiled.count(ILLUMINATED_CLASSIC_MARKER) == 1
    assert compiled.endswith(theme + "\n"), "theme must be last to avoid historical overrides"
    assert compiled.find("v88 mobile podium rank order") < compiled.find(ILLUMINATED_CLASSIC_MARKER)

    for foreground, background in (
        ("#FFFFFF", "#284B85"),
        ("#FFFFFF", "#284D87"),
        ("#FFF8E6", "#2A4574"),
        ("#F2F2FF", "#223C71"),
        ("#232D49", "#FFF0C5"),
        ("#203352", "#FBF6EA"),
        ("#1D477C", "#EAF0FA"),
    ):
        assert _contrast(foreground, background) >= 4.5, f"text contrast: {foreground} / {background}"

    index = build_index()
    js = build_app_js()
    assert index.count(ILLUMINATED_DECK_MARKER) == 1
    assert all(f"<span>{suit}</span>" in index for suit in ("♠", "♥", "♦", "♣"))
    assert transform_index(index) == index, "markup must be idempotent"
    assert '<button class="nav" data-view="points">＋ <span>ポイント入力</span></button>' in index
    assert 'id="pointForm"' in index
    assert 'id="quickPointForm"' in js
    assert "'#mobileQuickPointCard'" in js
    assert "if(isMobileUX()){ensureQuickPointHome();" in js

    print("JJ_ILLUMINATED_CLASSIC_THEME_OK")


if __name__ == "__main__":
    main()
