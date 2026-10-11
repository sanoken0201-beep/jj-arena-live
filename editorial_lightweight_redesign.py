from __future__ import annotations

"""JJ Arena graphic-theme transform; preserve the canonical layout.

Only color, background, borders, shadow and decorative pseudo-elements change.
All grid/flex, positions, dimensions, paddings, type sizes and actions remain
owned by the original compiled CSS. No additional stylesheet/runtime assets.
"""

MARKER = "jj lightweight editorial redesign 2026-10-11"

# Dark maritime blue, warm chalk white and restrained copper. These replace
# the generic emerald/gold gradients without sacrificing AAA-like contrast.
PALETTE = {
    "--bg:#f4f2ec;": "--bg:#F3F1EC;",
    "--surface:#fffdfa;": "--surface:#FFFEFC;",
    "--surface-2:#f8f6f0;": "--surface-2:#F7F5F1;",
    "--surface-3:#eeece5;": "--surface-3:#E8ECEC;",
    "--ink:#14211b;": "--ink:#192E3A;",
    "--muted:#6d786f;": "--muted:#53636C;",
    "--muted-2:#98a097;": "--muted-2:#657680;",
    "--line:#e2dfd6;": "--line:#D9E0E1;",
    "--line-strong:#d4cfc2;": "--line-strong:#BDC9CD;",
    "--green:#0d5a3f;": "--green:#245366;",
    "--green-2:#16704f;": "--green-2:#326C80;",
    "--green-3:#dcebe4;": "--green-3:#DCECEF;",
    "--green-4:#edf5f0;": "--green-4:#EDF5F7;",
    "--gold:#b58a3a;": "--gold:#996035;",
    "--gold-2:#e5d2a6;": "--gold-2:#DEC0A0;",
    "--gold-3:#fff7e4;": "--gold-3:#FAF0E7;",
    "--accent2:#138554;": "--accent2:#15775F;",
    "--positive:#138554;": "--positive:#15775F;",
}

# Decorative background substitutions only: no layout declarations added.
GRAPHICS = {
    "background:linear-gradient(180deg,var(--green-2),var(--green));": "background:var(--green);",
    "background:linear-gradient(145deg,#0f6648,#0a4934);": "background:#244C60;",
    "background:#12221b;color:#dce8e1;": "background:#192D3B;color:#E4ECEF;",
    "background:linear-gradient(90deg,rgba(44,143,99,.24),rgba(255,255,255,.035));": "background:#2C4C60;",
    "box-shadow:inset 3px 0 #63b98f": "box-shadow:inset 3px 0 #D6A879",
    "background:rgba(244,242,236,.88);": "background:rgba(243,241,236,.93);",
    "background:linear-gradient(180deg,#fffdfa,#f6f2e7);": "background:#FFFEFC;",
    "background:linear-gradient(145deg,#fffdf8,#fff7e2);": "background:#FAEEE2;",
    "background:linear-gradient(180deg,#fffdf7,#fff8e6);": "background:#FAEEE2;",
    "background:linear-gradient(145deg,#163d31,#235944)!important": "background:#1C3545!important",
    "background:rgba(20,51,40,.96)": "background:#192D3B",
    "background:#bff0d8!important": "background:#E9C9A7!important",
    "background:linear-gradient(180deg,#f7faf8 0,#f2f6f3 48%,#edf3ef 100%)": "background:#F3F1EC",
    "background:rgba(247,250,248,.92)!important": "background:rgba(250,249,245,.97)!important",
    "background:rgba(250,252,251,.94)!important": "background:rgba(251,250,247,.97)!important",
    "background:linear-gradient(145deg,#163d31,#235944)!important": "background:#1C3545!important",
}

HERO_BEFORE = (
    '.hero:before{content:"";position:absolute;right:5%;bottom:-40%;width:360px;height:360px;'
    'border:1px solid rgba(255,255,255,.10);border-radius:50%;'
    'box-shadow:0 0 0 38px rgba(255,255,255,.025),0 0 0 78px rgba(255,255,255,.018)}'
)
HERO_WORDMARK = (
    '.hero:before{content:"JJ";position:absolute;right:5%;bottom:-40%;width:360px;height:360px;'
    'border:0;border-radius:0;box-shadow:none;color:rgba(255,255,255,.11);'
    'font-size:15rem;font-weight:900;letter-spacing:-.12em;line-height:1.2;pointer-events:none}'
)
HERO_GRADIENT = (
    "background:\n radial-gradient(circle at 76% 16%,rgba(229,210,166,.19),transparent 22%),\n"
    " linear-gradient(135deg,#17362b 0%,#0e5a40 66%,#0b4734 100%);"
)
HERO_COLOR = "background:#1C3545;"


def _once(source: str, before: str, after: str) -> str:
    count = source.count(before)
    if count != 1:
        raise RuntimeError(f"graphic-theme CSS drift ({count} matches): {before[:84]}")
    return source.replace(before, after, 1)


def transform_styles(source: str) -> str:
    if MARKER in source:
        return source
    css = source
    # Limit token swaps to :root; do not alter dark-felt poker rendering rules.
    root_end = css.find("\n}", css.index(":root{")) + 2
    if root_end < 2:
        raise RuntimeError("graphic-theme root tokens missing")
    root, tail = css[:root_end], css[root_end:]
    for old, new in PALETTE.items():
        root = _once(root, old, new)
    css = root + tail
    css = _once(css, HERO_GRADIENT, HERO_COLOR)
    css = _once(css, HERO_BEFORE, HERO_WORDMARK)

    # Change hero text and accent tones while preserving structure/sizes.
    replacements = {
        ".hero .eyebrow{color:#a9d7c1}": ".hero .eyebrow{color:#D7B996}",
        ".hero p{color:#c7d8cf;": ".hero p{color:#E3ECEE;",
        ".hero .primary{background:#f4e8c8;color:#294438;":
            ".hero .primary{background:#E7C5A1;color:#1A3140;",
        ".hero .soft{background:rgba(255,255,255,.08);":
            ".hero .soft{background:rgba(255,255,255,.11);",
        ".leader-box b{font-size:1.7rem;color:#f0dca8;":
            ".leader-box b{font-size:1.7rem;color:#EAD0AC;",
        ".leader-box span{display:block;font-size:.6rem;letter-spacing:.15em;color:#bcd2c5;":
            ".leader-box span{display:block;font-size:.6rem;letter-spacing:.15em;color:#D4E4E9;",
        ".nav{display:flex;align-items:center;gap:12px;width:100%;border:1px solid transparent;background:transparent;color:#9eb0a5;":
            ".nav{display:flex;align-items:center;gap:12px;width:100%;border:1px solid transparent;background:transparent;color:#C4D2D8;",
        ".nav.active{color:#fff;": ".nav.active{color:#fff;",
    }
    for before, after in replacements.items():
        if before != after:
            css = _once(css, before, after)
    for before, after in GRAPHICS.items():
        # CSS compiled from previous mobile transforms can contain the same
        # token multiple times; replace the entire literal, never alter layout.
        if before in css:
            css = css.replace(before, after)

    return css + "\n/* " + MARKER + " */\n"


__all__ = ["MARKER", "PALETTE", "transform_styles"]
