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
    (".link-btn", "background:transparent;color:var(--green);padding-inline:5px;min-height:44px"),
    (".hero", "min-height:0;padding:27px;display:flex;justify-content:space-between;align-items:stretch;gap:24px;position:relative;background:var(--surface);color:var(--ink);border:1px solid var(--line);border-top:3px solid var(--green);box-shadow:none"),
    (".hero:before", None),
    (".hero .eyebrow", "color:var(--green)"),
    (".hero h3", "font-size:clamp(1.9rem,3vw,2.9rem);line-height:1.13;letter-spacing:-.04em;margin:.5rem 0 .8rem;max-width:720px"),
    (".hero p", "color:#536158;max-width:620px;line-height:1.65;font-size:.9rem;margin-bottom:20px"),
    (".hero .primary", "background:var(--green);color:#fff;box-shadow:none"),
    (".hero .soft", "background:#fff;color:var(--green);border:1px solid var(--line)"),
    (".leader-box", "align-self:flex-end;min-width:180px;padding:14px 18px;border:0;border-left:2px solid var(--green);border-radius:0;background:transparent"),
    (".leader-box span", "display:block;font-size:.75rem;letter-spacing:.04em;color:var(--muted);font-weight:750"),
    (".leader-box strong", "display:block;font-size:1.03rem;margin:8px 0 4px"),
    (".leader-box b", "font-size:1.3rem;color:var(--green);letter-spacing:-.02em"),
    (".kpi", "padding:24px;display:flex;flex-direction:column;justify-content:center;background:var(--surface);position:relative"),
    (".kpi:after", None),
    (".top-grid", "display:grid;grid-template-columns:1fr;gap:0"),
    (".top-player", "display:grid;grid-template-columns:45px minmax(0,1fr) max-content 96px;align-items:center;gap:12px;padding:12px 14px;position:relative;border:0;border-bottom:1px solid var(--line);border-radius:0;box-shadow:none;min-height:56px"),
    (".top-player:hover", "background:var(--surface-2)"),
    (".top-player:first-child", "border-left:3px solid var(--green);background:var(--surface)"),
    (".top-player .rank", "font-size:1rem;color:var(--green);font-weight:800"),
    (".top-player strong", "display:block;margin:0;font-size:1rem;min-width:0;overflow-wrap:anywhere"),
    (".toolbar", "padding:12px;display:flex;gap:10px;align-items:center;position:sticky;top:102px;z-index:10;box-shadow:none"),
    (".podium", "display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0;align-items:stretch;margin:18px 0 22px;max-width:none"),
    (".podium-card", "text-align:left;padding:17px 18px;min-height:0;display:flex;flex-direction:column;justify-content:center;border:0;border-bottom:1px solid var(--line);border-radius:0;box-shadow:none;overflow-wrap:anywhere"),
    (".podium-card:first-child", "border-left:3px solid var(--green);background:var(--surface);box-shadow:none"),
    (".podium-card:nth-child(2)", None),
    (".podium-card:nth-child(3)", None),
    # Mobile rules retain their pre-existing functional grid, touch and sticky behavior.
    ("#homeView .hero", "padding:18px!important;min-height:0!important;display:grid!important;grid-template-columns:1fr!important;gap:12px!important;align-content:start!important;justify-content:normal!important;background:var(--surface)!important;color:var(--ink)!important"),
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
        (".view{display:none;animation:viewIn .18s ease-out}", ".view{display:none;animation:none}"),
        ("--radius:22px;", "--radius:12px;"),
        ("--radius-sm:14px;", "--radius-sm:8px;"),
        ("--shadow-xs:0 1px 2px rgba(23,31,27,.04);", "--shadow-xs:none;"),
        ("--shadow-sm:0 10px 30px rgba(28,38,32,.06);", "--shadow-sm:none;"),
        ("--shadow-md:0 20px 60px rgba(28,38,32,.10);", "--shadow-md:none;"),
        (".eyebrow{font-size:.66rem;font-weight:850;", ".eyebrow{font-size:.75rem;font-weight:800;"),
        (".hint{color:var(--muted);font-size:.78rem;", ".hint{color:var(--muted);font-size:.875rem;"),
        ("th{font-size:.61rem;color:var(--muted);", "th{font-size:.75rem;color:#536158;"),
        ("td{font-size:.82rem}", "td{font-size:.875rem}"),
        (".segmented button,.side-tabs button{border:0;background:transparent;color:var(--muted);border-radius:9px;padding:8px 12px;font-size:.72rem;", ".segmented button,.side-tabs button{border:0;background:transparent;color:#536158;border-radius:9px;padding:8px 12px;font-size:.875rem;"),
        (".card{border-radius:18px!important;box-shadow:0 8px 28px rgba(26,55,42,.055)!important;border-color:rgba(34,75,55,.09)!important}",
         ".card{border-radius:12px!important;box-shadow:none!important;border-color:var(--line)!important}"),
        ("background:rgba(247,250,248,.92)!important;border-bottom:1px solid rgba(32,67,51,.08);backdrop-filter:blur(18px) saturate(1.35);-webkit-backdrop-filter:blur(18px) saturate(1.35)",
         "background:#f7faf8!important;border-bottom:1px solid var(--line)"),
        ("#homeView .hero p{font-size:.82rem!important;line-height:1.65!important;opacity:.88}", "#homeView .hero p{font-size:.875rem!important;line-height:1.65!important;opacity:1}"),
        (".leader-box{width:100%!important;min-height:auto!important;padding:13px 15px!important;border-radius:14px!important;display:grid!important;grid-template-columns:1fr auto!important;align-items:center!important}", ".leader-box{width:100%!important;min-height:auto!important;padding:13px 15px!important;margin-top:0!important;border-radius:0!important;display:grid!important;grid-template-columns:1fr auto!important;align-items:center!important}"),
        (".top-grid{display:flex!important;gap:9px!important;overflow-x:auto!important;margin:0 -12px!important;padding:2px 12px 12px!important;scroll-snap-type:x mandatory;scrollbar-width:none}",
         ".top-grid{display:grid!important;grid-template-columns:1fr!important;gap:0!important;overflow:visible!important;margin:0!important;padding:0!important;scroll-snap-type:none}"),
        ("#rankingView .segmented button{flex:1 0 auto;min-height:40px!important;white-space:nowrap}", "#rankingView .segmented button{flex:1 0 auto;min-height:44px!important;white-space:nowrap}"),
        (".podium-card{display:grid!important;grid-template-columns:62px 1fr auto!important;align-items:center!important;gap:8px!important;padding:13px 14px!important}", ".podium-card{display:grid!important;grid-template-columns:46px minmax(0,1fr)!important;align-items:center!important;gap:5px 9px!important;padding:13px 10px!important}"),
        (".podium-card strong{grid-column:2;font-size:1rem!important}", ".podium-card strong{grid-column:2;font-size:1rem!important;overflow-wrap:anywhere}"),
        (".podium-card>b{grid-column:3;font-size:1rem!important}", ".podium-card>b{grid-column:2;font-size:1.05rem!important}"),
        (".podium-card .hint{grid-column:2/4!important}", ".podium-card .hint{grid-column:2!important}"),
        ("#rankingView td{display:block!important;padding:0!important;border:0!important;min-width:0}", "#rankingView td{display:block!important;padding:0!important;border:0!important;min-width:0;font-size:.875rem!important;line-height:1.45}"),
        ("#rankingView td:nth-child(2){overflow:hidden;text-overflow:ellipsis;white-space:nowrap}", "#rankingView td:nth-child(2){overflow:visible;text-overflow:clip;white-space:normal!important;overflow-wrap:anywhere}"),
        ("#rankingView tr{display:grid!important;grid-template-columns:50px minmax(0,1fr) auto!important;", "#rankingView tr{display:grid!important;grid-template-columns:40px minmax(0,1fr) auto!important;"),
        (".top-player{flex:0 0 min(72vw,280px)!important;scroll-snap-align:start;padding:15px!important;min-height:128px!important}",
         ".top-player{display:grid!important;grid-template-columns:36px minmax(0,1fr) auto!important;padding:12px 8px!important;min-height:0!important;scroll-snap-align:none}"),
    ):
        css = _replace_exact(css, old, new)
    for selector, declaration in _RULES:
        css = _replace_rule(css, selector, declaration)
    # This is a NEW selector; the canonical CSS has only a global .hint rule.
    # Append it once alongside the existing Home leaderboard rule.
    current = ".top-player strong{display:block;margin:0;font-size:1rem;min-width:0;overflow-wrap:anywhere}"
    css = _replace_exact(css, current, current + ".top-player .hint{font-size:.875rem;line-height:1.4;text-align:right;white-space:nowrap}")
    # Home leaderboard metadata is secondary on small screens; keep names and
    # point totals visible with no horizontal scrolling.
    mobile_hint = ".top-player .hint{display:none!important}"
    anchor = ".top-player{display:grid!important;grid-template-columns:36px minmax(0,1fr) auto!important;padding:12px 8px!important;min-height:0!important;scroll-snap-align:none}"
    css = _replace_exact(css, anchor, anchor + mobile_hint)
    # Non-rendered CSS marker; keeps the build transform idempotent.
    return css + "\n/* " + MARKER + " */\n"


__all__ = ["MARKER", "transform_styles"]
