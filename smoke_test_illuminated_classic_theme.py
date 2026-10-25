"""The bright classic visual theme must not change gameplay or point entry."""

from __future__ import annotations

from illuminated_classic_theme import (
    ILLUMINATED_CLASSIC_CSS,
    ILLUMINATED_CLASSIC_MARKER,
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
    assert ASSET_VERSION >= 95, "the new CSS must invalidate the previous PWA cache"
    theme = ILLUMINATED_CLASSIC_CSS
    assert len(theme.encode("utf-8")) <= 4400, "keep the presentation-only CSS small"
    assert all(suit in theme for suit in ("♠", "♥", "♦", "♣"))
    assert all(selector in theme for selector in (
        "#homeView .hero", "#rankingView .podium-card", "#pointsView .panel", "#authView.auth-shell",
    ))
    for forbidden in (
        ":root", "#pokerRoom", "#pokerTable", "#actionBar", "#pointForm", "#quickPointForm",
        "#mobileQuickPointCard", "#homePointShortcut", ".sidebar", "@font-face", "@keyframes",
        "@import", "url(", "animation:", "grid-template", "min-height:", "padding:",
    ):
        assert forbidden not in theme, f"unexpected gameplay, entry, layout or network styling: {forbidden}"

    assert transform_styles(theme) == theme, "theme must be idempotent"
    compiled = build_styles()
    assert compiled.count(ILLUMINATED_CLASSIC_MARKER) == 1
    assert compiled.endswith(theme + "\n"), "theme must be last to avoid historical overrides"
    assert compiled.find("v88 mobile podium rank order") < compiled.find(ILLUMINATED_CLASSIC_MARKER)

    for foreground, background in (
        ("#FFFFFF", "#315FC5"),
        ("#FFFFFF", "#244A9E"),
        ("#FFF0C7", "#315FC5"),
        ("#EDF2FF", "#315FC5"),
        ("#28365C", "#FFF9EE"),
        ("#315FC5", "#FFFDFA"),
        ("#846012", "#FFF1DB"),
    ):
        assert _contrast(foreground, background) >= 4.5, f"text contrast: {foreground} / {background}"

    index = build_index()
    js = build_app_js()
    assert '<button class="nav" data-view="points">＋ <span>ポイント入力</span></button>' in index
    assert 'id="pointForm"' in index
    assert 'id="quickPointForm"' in js
    assert "'#mobileQuickPointCard'" in js
    assert "if(isMobileUX()){ensureQuickPointHome();" in js

    print("JJ_ILLUMINATED_CLASSIC_THEME_OK")


if __name__ == "__main__":
    main()
