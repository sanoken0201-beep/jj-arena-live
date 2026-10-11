from __future__ import annotations

"""Build-time, CSS-only editorial treatment for Home and Rankings.

The canonical materialized assets stay immutable. Replacing expensive
decorative rules (rather than appending another stylesheet) keeps both the
download and the number of style rules from growing. No JS or game UI changes.
"""

import re

MARKER = "jj lightweight editorial redesign 2026-10-11"

# Each entry replaces the FIRST matching rule in the existing compiled CSS.
# The exact-selector guard fails the build if an upstream layout is reworked.
_RULES: tuple[tuple[str, str | None], ...] = (
    (".primary", "background:var(--green);color:#fff;box-shadow:none"),
    (".primary:hover", "background:var(--green-2);transform:none;box-shadow:none"),
    (".hero", "min-height:0;padding:27px;display:flex;justify-content:space-between;align-items:stretch;gap:24px;position:relative;background:var(--surface);color:var(--ink);border:1px solid var(--line);border-top:3px solid var(--green);box-shadow:none"),
    (".hero:before", None),
    (".hero .eyebrow", "color:var(--green)"),
    (".hero h3", "font-size:clamp(1.9rem,3vw,2.9rem);line-height:1.13;letter-spacing:-.04em;margin:.5rem 0 .8rem;max-width:720px"),
    (".hero p", "color:var(--muted);max-width:620px;line-height:1.65;font-size:.85rem;margin-bottom:20px"),
    (".hero .primary", "background:var(--green);color:#fff;box-shadow:none"),
    (".hero .soft", "background:#fff;color:var(--green);border:1px solid var(--line)"),
    (".leader-box", "align-self:flex-end;min-width:180px;padding:14px 18px;border:0;border-left:2px solid var(--green);border-radius:0;background:transparent"),
    (".leader-box span", "display:block;font-size:.65rem;letter-spacing:.08em;color:var(--muted);font-weight:750"),
    (".leader-box strong", "display:block;font-size:1.03rem;margin:8px 0 4px"),
    (".leader-box b", "font-size:1.3rem;color:var(--green);letter-spacing:-.02em"),
    (".kpi", "padding:24px;display:flex;flex-direction:column;justify-content:center;background:var(--surface);position:relative"),
    (".kpi:after", None),
    (".top-grid", "display:grid;grid-template-columns:1fr;gap:0"),
    (".top-player", "display:grid;grid-template-columns:45px minmax(0,1fr) max-content 100px;align-items:center;gap:12px;padding:12px 14px;position:relative;border:0;border-bottom:1px solid var(--line);border-radius:0;box-shadow:none;min-height:56px"),
    (".top-player:hover", "background:var(--surface-2)"),
    (".top-player:first-child", "border-left:3px solid var(--green);background:var(--surface)"),
    (".top-player .rank", "font-size:1rem;color:var(--green);font-weight:800"),
    (".top-player strong", "display:block;margin:0;font-size:.9rem"),
    (".toolbar", "padding:12px;display:flex;gap:10px;align-items:center;position:sticky;top:102px;z-index:10;box-shadow:none"),
    (".podium", "display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0;align-items:stretch;margin:18px 0 22px;max-width:none"),
    (".podium-card", "text-align:left;padding:17px 18px;min-height:0;display:flex;flex-direction:column;justify-content:center;border:0;border-bottom:1px solid var(--line);border-radius:0;box-shadow:none"),
    (".podium-card:first-child", "border-left:3px solid var(--green);background:var(--surface);box-shadow:none"),
    (".podium-card:nth-child(2)", None),
    (".podium-card:nth-child(3)", None),
    # Mobile rules retain their pre-existing functional grid, touch and sticky behavior.
    ("#homeView .hero", "padding:18px!important;min-height:0!important;display:grid!important;grid-template-columns:1fr!important;gap:12px!important;background:var(--surface)!important;color:var(--ink)!important"),
    ("#rankingView .toolbar", "position:sticky!important;top:calc(var(--mobile-top-h) + env(safe-area-inset-top) - 1px);z-index:38;display:grid!important;grid-template-columns:1fr!important;gap:8px!important;margin:0 -4px 11px!important;padding:10px!important;border-radius:6px!important;background:#f9faf7!important;backdrop-filter:none"),
    ("#rankingView tr", "display:grid!important;grid-template-columns:45px minmax(0,1fr) auto!important;align-items:center!important;gap:7px!important;margin-bottom:0!important;padding:13px 8px!important;background:var(--surface);border:0;border-bottom:1px solid var(--line);border-radius:0;box-shadow:none"),
)


def _replace_rule(source: str, selector: str, body: str | None) -> str:
    pattern = re.compile(re.escape(selector) + r"\{[^{}]*\}")
    match = pattern.search(source)
    if match is None:
        raise RuntimeError(f"editorial CSS selector drift: {selector}")
    replacement = "" if body is None else selector + "{" + body + "}"
    return source[: match.start()] + replacement + source[match.end() :]


def _replace_exact(source: str, old: str, new: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"editorial CSS asset drift (expected once, got {count}): {old[:70]}")
    return source.replace(old, new, 1)


def transform_styles(source: str) -> str:
    if MARKER in source:
        return source
    css = source
    # Shared low-paint primitives apply across views, but leave poker layout alone.
    for old, new in (
        ("--radius:22px;", "--radius:12px;"),
        ("--radius-sm:14px;", "--radius-sm:8px;"),
        ("--shadow-xs:0 1px 2px rgba(23,31,27,.04);", "--shadow-xs:none;"),
        ("--shadow-sm:0 10px 30px rgba(28,38,32,.06);", "--shadow-sm:none;"),
        ("--shadow-md:0 20px 60px rgba(28,38,32,.10);", "--shadow-md:none;"),
        (".card{border-radius:18px!important;box-shadow:0 8px 28px rgba(26,55,42,.055)!important;border-color:rgba(34,75,55,.09)!important}",
         ".card{border-radius:12px!important;box-shadow:none!important;border-color:var(--line)!important}"),
        ("background:rgba(247,250,248,.92)!important;border-bottom:1px solid rgba(32,67,51,.08);backdrop-filter:blur(18px) saturate(1.35);-webkit-backdrop-filter:blur(18px) saturate(1.35)",
         "background:#f7faf8!important;border-bottom:1px solid var(--line)"),
        (".top-grid{display:flex!important;gap:9px!important;overflow-x:auto!important;margin:0 -12px!important;padding:2px 12px 12px!important;scroll-snap-type:x mandatory;scrollbar-width:none}",
         ".top-grid{display:grid!important;grid-template-columns:1fr!important;gap:0!important;overflow:visible!important;margin:0!important;padding:0!important;scroll-snap-type:none}"),
        (".top-player{flex:0 0 min(72vw,280px)!important;scroll-snap-align:start;padding:15px!important;min-height:128px!important}",
         ".top-player{display:grid!important;grid-template-columns:36px minmax(0,1fr) auto!important;padding:12px 8px!important;min-height:0!important;scroll-snap-align:none}"),
    ):
        css = _replace_exact(css, old, new)
    for selector, declaration in _RULES:
        css = _replace_rule(css, selector, declaration)
    # Home leaderboard metadata is secondary on small screens; keep names and
    # point totals visible with no horizontal scrolling.
    mobile_hint = ".top-player .hint{display:none!important}"
    anchor = ".top-player{display:grid!important;grid-template-columns:36px minmax(0,1fr) auto!important;padding:12px 8px!important;min-height:0!important;scroll-snap-align:none}"
    css = _replace_exact(css, anchor, anchor + mobile_hint)
    # Non-rendered CSS marker; keeps the build transform idempotent.
    return css + "\n/* " + MARKER + " */\n"


__all__ = ["MARKER", "transform_styles"]
